"""Snapshot pull orchestration — the end-to-end assembly of an immutable,
completeness-verified PIT snapshot from the Trading OS (RD-002, RD-014, RD-015).

Flow: pull universe -> per-symbol bars+features (tagged with identity, since
/v1/features is data-only) -> macro -> stage -> read staged artifact -> run the
four-tier checks -> (abort if any BLOCKING violation, nothing registered) ->
build manifest -> content_hash over the canonical form -> move to immutable path
-> insert research.snapshot. Born complete: a snapshot row exists only for a
fully-assembled, completeness-passed, hash-verified artifact.

Dev slice vs full universe is a difference in the symbol set only — same code.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import json
import shutil
import tempfile

from research_os.db import connect
from research_os.trading_os_client.client import (
    TradingOsClient, FeaturesResult, UniverseResult, TradingOsHttpError,
)
from research_os.snapshot import staging, reader
from research_os.snapshot.model import SnapshotRequest, PulledData
from research_os.snapshot.completeness import run_all_checks, blocking_violations
from research_os.snapshot.violation import Violation, Tier, Severity
from research_os.snapshot.manifest import build_manifest, canonical_manifest_for_hash
from research_os.snapshot.content_hash import compute_content_hash


class SnapshotRegistrationError(Exception):
    """Governed lifecycle state: the artifact was staged, validated, hashed, and
    moved to its immutable path, but the DB registration failed. The artifact is a
    VERIFIED ORPHAN — recoverable, but NOT a registered snapshot. The Research OS
    must never treat an orphan directory as available; only a research.snapshot row
    means available. This error carries structured recovery data so the orphan can
    be re-registered or removed without reconstructing what happened.
    """
    def __init__(self, snapshot_path: str, content_hash: str, manifest: dict,
                 cause: Exception):
        self.snapshot_path = snapshot_path
        self.content_hash = content_hash
        self.manifest = manifest
        self.cause = cause
        super().__init__(
            f"snapshot artifact assembled, validated, and hashed but registration "
            f"failed; verified orphan retained at {snapshot_path}; "
            f"content_hash={content_hash}; recover by re-registering from the "
            f"manifest or deleting the orphan. Cause: {cause}"
        )


class SnapshotPullAborted(Exception):
    """Raised when completeness fails; carries the blocking violations. Nothing
    is registered."""
    def __init__(self, violations: list[Violation]):
        self.violations = violations
        lines = "\n".join(f"  [{v.tier.value}/{v.issue}] {v.message}" for v in violations)
        super().__init__(f"snapshot pull aborted: {len(violations)} blocking "
                         f"violation(s):\n{lines}")


@dataclass(frozen=True)
class SnapshotResult:
    snapshot_id: int
    path: str
    content_hash: str
    warnings: list[Violation]


def _tag_gold_rows(result: FeaturesResult, security_id: int, symbol: str) -> FeaturesResult:
    """/v1/features rows are data-only; attach identity from the symbol we queried."""
    tagged = [{**row, "security_id": security_id, "symbol": symbol} for row in result.rows]
    return FeaturesResult(as_of=result.as_of, symbols=result.symbols,
                          unresolved=result.unresolved, count=result.count, rows=tagged)


def pull_snapshot(
    request: SnapshotRequest,
    client: TradingOsClient,
    snapshots_root: Path,
    *,
    code_sha: str,
    governed_min_members: int | None = None,
    fetch_producer_dq: bool = True,
    conn=None,                     # injectable DB connection; tests pass a rolled-back one
) -> SnapshotResult:
    pulled_at = datetime.now(timezone.utc)
    pull_warnings: list[Violation] = []

    # 1. FULL membership interval history (survivorship-free): every security ever
    #    a member of the index, including delisted ones, with its PIT ticker per
    #    interval. Identity is security_id; ticker is only the key for the
    #    symbol-based bars/features endpoints (RD-014, survivorship correctness).
    history = client.universe_history(request.universe_code, request.as_of)
    intervals = history.intervals            # each: security_id, valid_from, valid_to, ticker

    # One fetch-ticker per security_id (any valid ticker returns that security's
    # full history; identity is verified on fetch regardless). Prefer a ticker
    # from an interval that actually has one.
    ticker_by_secid: dict[int, str] = {}
    for iv in intervals:
        sid = iv["security_id"]
        if sid not in ticker_by_secid and iv.get("ticker"):
            ticker_by_secid[sid] = iv["ticker"]

    all_secids = sorted({iv["security_id"] for iv in intervals})

    # requested_symbols is a DEV-SLICE restriction only (by ticker), never an
    # independent population. Population is ALWAYS the full membership history.
    if request.requested_symbols:
        requested = set(request.requested_symbols)
        population = [sid for sid in all_secids
                      if ticker_by_secid.get(sid) in requested]
        matched_tickers = {ticker_by_secid.get(sid) for sid in population}
        for t in sorted(requested - matched_tickers):
            pull_warnings.append(Violation(
                Tier.REQUEST_DERIVED, Severity.WARNING, "requested_symbol_not_member",
                f"dev-slice requested symbol {t} is not in the membership history "
                f"of {request.universe_code}; excluded (population is the PIT "
                f"membership history, RD-014)",
                domain="universe", symbol=t))
    else:
        population = all_secids

    # 2. Per-security bars + features, fetched by ticker but KEYED and VERIFIED on
    #    security_id. If a (future) reused ticker returns a different security_id
    #    than intended, that is a HARD ticker_identity_mismatch — the snapshot must
    #    never silently ingest another security's data as the intended one.
    bars_results = []
    gold_results = []
    all_unresolved: list[str] = []
    for sid in population:
        ticker = ticker_by_secid.get(sid)
        if not ticker:
            # A member with no resolvable ticker cannot be fetched via the
            # symbol-keyed endpoints. Hard failure — do not silently drop a member.
            raise SnapshotPullAborted([Violation(
                Tier.CROSS_DOMAIN, Severity.HARD, "member_no_ticker",
                f"security_id {sid} is in the membership history but has no "
                f"resolvable ticker to fetch its data",
                domain="universe", security_id=sid)])

        b = client.bars(ticker, as_of=request.as_of, adjustment="total_return")
        # IDENTITY VERIFICATION (ticker-reuse guard): the returned security_id must
        # equal the intended one. A mismatch means the ticker now resolves to a
        # different security — fail closed, never corrupt the snapshot.
        if b.security_id != sid:
            raise SnapshotPullAborted([Violation(
                Tier.CROSS_DOMAIN, Severity.HARD, "ticker_identity_mismatch",
                f"intended security_id {sid} via ticker {ticker!r} but bars "
                f"returned security_id {b.security_id}; refusing to ingest another "
                f"security's data (possible ticker reuse)",
                domain="bars", security_id=sid, symbol=ticker,
                expected=sid, observed=b.security_id)])
        bars_results.append(b)

        f = client.features(as_of=request.as_of, symbols=[ticker])
        all_unresolved.extend(f.unresolved)
        gold_results.append(_tag_gold_rows(f, sid, ticker))

    # Merge per-security gold into one FeaturesResult for staging.
    merged_gold = FeaturesResult(
        as_of=str(request.as_of),
        symbols=[ticker_by_secid.get(sid) for sid in population],
        unresolved=all_unresolved,
        count=sum(g.count for g in gold_results),
        rows=[r for g in gold_results for r in g.rows],
    )

    # 3. Macro. A 404 (series genuinely absent) is an INCOMPLETENESS fact: we skip
    #    appending it, and the tier-2 request-derived check discovers the absence
    #    when validating the staged artifact against the request (macro_series_missing).
    #    Any other HTTP status, or a transport failure, is INFRASTRUCTURE and
    #    propagates — the completeness layer must not hide an outage as "missing data".
    macro_results = []
    for s in request.macro_series:
        try:
            macro_results.append(client.macro(s, request.as_of))
        except TradingOsHttpError as e:
            if e.status != 404:
                raise                             # infrastructure failure -> propagate
            # 404 -> series genuinely absent; leave it out, tier-2 will flag it.

    # 4. Producer DQ signal (provenance; not a rebuilt check).
    producer_dq = None
    if fetch_producer_dq:
        try:
            producer_dq = client.health_dq()
        except TradingOsHttpError:
            producer_dq = {"status": "unavailable"}

    # 5. Stage to a temp dir.
    staging_dir = Path(tempfile.mkdtemp(prefix="snapshot_staging_"))
    try:
        # universe.parquet = the full membership INTERVAL history for the pulled
        # population, keyed on security_id (survivorship-free). R1 reconstructs PIT
        # membership locally by interval containment — never calling back to the
        # Trading OS. For a dev slice, restrict intervals to the pulled securities;
        # for a full pull, that's all of them.
        pop_set = set(population)
        pulled_intervals = [iv for iv in intervals if iv["security_id"] in pop_set]
        staging.write_bars(bars_results, staging_dir)
        staging.write_gold(merged_gold, staging_dir)
        staging.write_universe_history(pulled_intervals, staging_dir)
        staging.write_macro(macro_results, staging_dir)

        # 6. Read the STAGED artifact back.
        data = reader.read_pulled_data(staging_dir, request.as_of,
                                       request.universe_code, all_unresolved)

        # 7. Completeness. Abort on any blocking violation — nothing registered.
        all_v = run_all_checks(data, request, governed_min_members)
        blocking = blocking_violations(all_v)
        if blocking:
            raise SnapshotPullAborted(blocking)
        warnings = pull_warnings + [v for v in all_v if v.severity is Severity.WARNING]

        # 8. Manifest + content_hash (hash over the message-stripped canonical form).
        trading_os_as_of = f"{request.as_of.isoformat()}T00:00:00+00:00"
        manifest = build_manifest(request, data, trading_os_as_of, warnings,
                                  code_sha=code_sha, producer_dq=producer_dq,
                                  pulled_at=pulled_at)
        files = sorted(staging_dir.glob("*.parquet"))
        content_hash = compute_content_hash(
            staging_dir, files, canonical_manifest_for_hash(manifest))

        # 9. Move staging -> immutable path (named by content_hash for uniqueness).
        final_dir = snapshots_root / f"{request.as_of.isoformat()}_{content_hash[:12]}"
        final_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staging_dir), str(final_dir))
        staging_dir = None  # moved; don't clean up

        # 10. Register (the final act; born complete). Registration is injectable:
        #     production opens+commits its own connection; tests pass a rolled-back
        #     conn so nothing persists. An insert failure raises explicitly and
        #     names the orphaned dir — it can never masquerade as success.
        def _do_insert(c):
            with c.cursor() as cur:
                cur.execute(
                    """insert into research.snapshot
                       (trading_os_as_of, snapshot_date, path, manifest, content_hash)
                       values (%s, %s, %s, %s, %s) returning snapshot_id""",
                    (trading_os_as_of, request.as_of, str(final_dir),
                     json.dumps(manifest), content_hash),
                )
                return cur.fetchone()[0]

        try:
            if conn is not None:
                snapshot_id = _do_insert(conn)        # caller owns commit/rollback
            else:
                with connect() as c:
                    snapshot_id = _do_insert(c)
                    c.commit()
        except Exception as e:
            raise SnapshotRegistrationError(
                snapshot_path=str(final_dir),
                content_hash=content_hash,
                manifest=manifest,
                cause=e,
            ) from e

        return SnapshotResult(snapshot_id=snapshot_id, path=str(final_dir),
                              content_hash=content_hash, warnings=warnings)
    finally:
        if staging_dir is not None and Path(staging_dir).exists():
            shutil.rmtree(staging_dir, ignore_errors=True)