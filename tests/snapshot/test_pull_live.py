"""Live end-to-end snapshot pull against the RUNNING Trading OS (dev slice).

The ultimate proof: real HTTP -> stage real Parquet -> completeness on real data
-> hash -> register (verified inside a rolled-back transaction, so nothing
persists). Requires the Trading OS API up and TRADING_OS_API_KEY set; skips
cleanly otherwise.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import pytest
from research_os.db import connect
from research_os.trading_os_client.config import TradingOsConfig, MissingApiKey
from research_os.trading_os_client.client import TradingOsClient, TradingOsTransportError
from research_os.snapshot.model import SnapshotRequest
from research_os.snapshot.pull import pull_snapshot, SnapshotResult, SnapshotPullAborted


@pytest.fixture(scope="module")
def live_client():
    try:
        cfg = TradingOsConfig.from_env()
    except MissingApiKey:
        pytest.skip("TRADING_OS_API_KEY not set")
    c = TradingOsClient(cfg)
    try:
        c.universe("SP500", date(2020, 6, 30))
    except TradingOsTransportError:
        pytest.skip("Trading OS API unreachable")
    return c


@pytest.fixture
def rolled_back_conn():
    c = connect(); c.autocommit = False
    try:
        yield c
    finally:
        c.rollback(); c.close()


def test_live_dev_slice_pull(tmp_path, live_client, rolled_back_conn):
    """A real dev-slice pull whose population is DERIVED FROM the live PIT universe
    (not invented): fetch real SP500 membership as_of the date, take two of those
    actual members as the dev slice, and pull the full chain end-to-end."""
    as_of = date(2020, 6, 30)

    # 1-4. Derive the dev slice FROM the real PIT membership.
    universe = live_client.universe("SP500", as_of)
    member_symbols = [m["symbol"] for m in universe.members if m.get("symbol")]
    assert len(member_symbols) > 100, "expected a populated SP500 membership"
    dev_slice = sorted(member_symbols)[:2]            # two real members

    request = SnapshotRequest(
        as_of=as_of, universe_code="SP500",
        feature_versions=[{"name": "momentum_12_1", "version": 1}],
        macro_series=["CPIAUCSL"],
        requested_symbols=dev_slice,                  # RESTRICTS the PIT population
    )

    try:
        result = pull_snapshot(request, live_client, tmp_path,
                               code_sha="live-test", conn=rolled_back_conn)
    except SnapshotPullAborted as e:
        pytest.fail(f"live pull unexpectedly aborted: {e}")

    assert isinstance(result, SnapshotResult)
    assert len(result.content_hash) == 64

    d = Path(result.path)
    for fname in ("bars.parquet", "gold.parquet", "universe.parquet", "macro.parquet"):
        assert (d / fname).exists(), f"missing {fname}"

    with rolled_back_conn.cursor() as cur:
        cur.execute("""select snapshot_date, content_hash, manifest
                       from research.snapshot where snapshot_id=%s""",
                    (result.snapshot_id,))
        row = cur.fetchone()
    assert str(row[0]) == "2020-06-30"
    assert row[1] == result.content_hash
    assert row[2]["scope"]["universe_code"] == "SP500"
    # the snapshot's gold population equals the dev slice (2 real members)
    assert row[2]["row_counts"]["gold_securities"] == len(dev_slice)


@pytest.mark.slow
def test_live_full_production_pull(tmp_path, live_client, rolled_back_conn):
    """The real thing: a FULL production pull of the entire SP500 membership as_of
    a date (requested_symbols=None -> population is all members). ~480 members x2
    HTTP calls; takes a few minutes. Doubles as a comprehensive completeness audit
    of the whole universe's data as_of the date. Rolled back — nothing persists.

    If this aborts, the completeness layer has found a real data gap (bars missing,
    or gold != bars for some member) — a finding to investigate, not a test bug.
    """
    as_of = date(2020, 6, 30)
    request = SnapshotRequest(
        as_of=as_of, universe_code="SP500",
        feature_versions=[{"name": "momentum_12_1", "version": 1}],
        macro_series=["CPIAUCSL"],
        requested_symbols=None,                       # FULL universe
    )
    try:
        result = pull_snapshot(request, live_client, tmp_path,
                               code_sha="live-full-test", conn=rolled_back_conn)
    except SnapshotPullAborted as e:
        # surface how many and which kinds of gaps, for investigation
        from collections import Counter
        kinds = Counter(v.issue for v in e.violations)
        pytest.fail(f"full pull aborted with {len(e.violations)} violations "
                    f"by kind: {dict(kinds)}\nfirst 10:\n" +
                    "\n".join(f"  {v.message}" for v in e.violations[:10]))

    assert isinstance(result, SnapshotResult)
    with rolled_back_conn.cursor() as cur:
        cur.execute("select manifest from research.snapshot where snapshot_id=%s",
                    (result.snapshot_id,))
        manifest = cur.fetchone()[0]
    counts = manifest["row_counts"]
    # every member has bars and gold (equality enforced by tier 3)
    assert counts["universe_members"] == counts["bars_securities"] == counts["gold_securities"]
    print(f"\nFULL PULL OK: {counts['universe_members']} members, "
          f"{counts['bars_sessions_total']} bar-sessions, "
          f"gold=bars, hash={result.content_hash[:12]}")