"""The four-tier snapshot completeness checks (ratified design; reviewer-refined).

Pure functions over the normalized PulledData + SnapshotRequest. No I/O, no API,
no Parquet — the increment-3 reader populates PulledData from the staged artifact,
so these validate the real thing while staying unit-testable with synthetic input.

Tiers:
  1 structural        — required identity/shape present and well-formed. HARD.
  2 request_derived   — everything requested actually appears (symbols resolved,
                        range covered, feature versions, macro series). HARD.
  3 cross_domain      — domains agree, BARS AS REFERENCE: every bars session has a
                        gold session; every universe member has bars. HARD.
                        (Calendar-completeness of bars is the Trading OS's job via
                        its DQ layer, not re-checked here — RD-001 boundary.)
  4 empirical_sanity  — magnitude plausibility. WARNING by default; HARD only for
                        explicitly governed thresholds (never arbitrary bands).

Each function returns list[Violation]; empty means that tier passed.
"""
from __future__ import annotations

from research_os.snapshot.model import (
    PulledData, SnapshotRequest, BarsSeries, GoldSeries,
)
from research_os.snapshot.violation import Violation, Tier, Severity


def _sym(security_id: int, symbol: str | None) -> str:
    """Identity label for diagnostics: 'AAPL (security_id=1)' or 'security_id=1'."""
    return f"{symbol} (security_id={security_id})" if symbol else f"security_id={security_id}"


# --- Tier 1: structural -------------------------------------------------------

def check_structural(data: PulledData, request: SnapshotRequest) -> list[Violation]:
    """Required identity and shape present and well-formed. Catches a malformed
    or empty artifact before any semantic check runs."""
    v: list[Violation] = []

    if data.as_of != request.as_of:
        v.append(Violation(
            Tier.STRUCTURAL, Severity.HARD, "as_of_mismatch",
            f"pulled as_of {data.as_of} != requested {request.as_of}",
            expected=str(request.as_of), observed=str(data.as_of)))

    if data.universe_code != request.universe_code:
        v.append(Violation(
            Tier.STRUCTURAL, Severity.HARD, "universe_mismatch",
            f"pulled universe {data.universe_code!r} != requested {request.universe_code!r}",
            expected=request.universe_code, observed=data.universe_code))

    # A snapshot with no members / no bars is structurally empty — fail loudly.
    if not data.members:
        v.append(Violation(
            Tier.STRUCTURAL, Severity.HARD, "empty_universe",
            f"universe {request.universe_code} resolved to zero members as_of {request.as_of}",
            domain="universe", expected=">0 members", observed=0))
    if not data.bars:
        v.append(Violation(
            Tier.STRUCTURAL, Severity.HARD, "empty_bars",
            "no bars in the pulled snapshot", domain="bars",
            expected=">0 securities with bars", observed=0))

    # Every series must carry a security_id; session lists must be sorted & unique.
    for b in data.bars:
        if b.security_id is None:
            v.append(Violation(Tier.STRUCTURAL, Severity.HARD, "missing_security_id",
                               "a bars series has no security_id", domain="bars"))
        if list(b.session_dates) != sorted(set(b.session_dates)):
            v.append(Violation(
                Tier.STRUCTURAL, Severity.HARD, "bars_sessions_not_unique_sorted",
                f"{_sym(b.security_id, b.symbol)} bars session_dates not sorted/unique",
                domain="bars", security_id=b.security_id, symbol=b.symbol))
    for g in data.gold:
        if list(g.session_dates) != sorted(set(g.session_dates)):
            v.append(Violation(
                Tier.STRUCTURAL, Severity.HARD, "gold_sessions_not_unique_sorted",
                f"{_sym(g.security_id, g.symbol)} gold session_dates not sorted/unique",
                domain="gold", security_id=g.security_id, symbol=g.symbol))
    return v


# --- Tier 2: request-derived --------------------------------------------------

def check_request_derived(data: PulledData, request: SnapshotRequest) -> list[Violation]:
    """Everything requested actually appears. The producer-transparency signal
    (`features_unresolved`) is enforced here: any unresolved requested symbol is a
    hard failure unless it is explained (a symbol not in the universe as_of)."""
    v: list[Violation] = []

    member_symbols = {m.symbol for m in data.members if m.symbol}

    # (a) Unresolved features symbols: must be empty, OR each unresolved symbol
    #     must be explainable (not a member of the universe as_of, so its absence
    #     is expected). An unresolved symbol that WAS a member is a real gap.
    for sym in data.features_unresolved:
        if sym in member_symbols:
            v.append(Violation(
                Tier.REQUEST_DERIVED, Severity.HARD, "member_unresolved_in_features",
                f"symbol {sym} is a universe member as_of {request.as_of} but was "
                f"unresolved by the features endpoint",
                domain="gold", symbol=sym))
        else:
            # Unresolved but not a member — record as a warning (explained absence).
            v.append(Violation(
                Tier.REQUEST_DERIVED, Severity.WARNING, "nonmember_unresolved",
                f"symbol {sym} was unresolved by features but is not a universe "
                f"member as_of {request.as_of}; treated as explained absence",
                domain="gold", symbol=sym))

    # (b) If explicit symbols were requested (dev slice), each must appear in bars.
    if request.requested_symbols:
        bars_symbols = {b.symbol for b in data.bars if b.symbol}
        for sym in request.requested_symbols:
            if sym not in bars_symbols:
                v.append(Violation(
                    Tier.REQUEST_DERIVED, Severity.HARD, "requested_symbol_missing_bars",
                    f"requested symbol {sym} has no bars in the snapshot",
                    domain="bars", symbol=sym))

    # (c) Macro: every requested series must be present.
    pulled_series = {m.series_id for m in data.macro}
    for s in request.macro_series:
        if s not in pulled_series:
            v.append(Violation(
                Tier.REQUEST_DERIVED, Severity.HARD, "macro_series_missing",
                f"requested macro series {s} is absent from the snapshot",
                domain="macro", expected=s, observed=None))
    return v


# --- Tier 3: cross-domain (bars as reference) --------------------------------

def check_cross_domain(data: PulledData, request: SnapshotRequest) -> list[Violation]:
    """Domains agree, with BARS AS THE REFERENCE. Every session present in bars
    for a security must have a corresponding gold session; every universe member
    must have bars. This is the check that catches the gold-lake failure class."""
    v: list[Violation] = []

    gold_by_sec = {g.security_id: set(g.session_dates) for g in data.gold}
    bars_by_sec = {b.security_id: b for b in data.bars}

    # (a) universe members must have bars.
    bars_sec_ids = set(bars_by_sec)
    for m in data.members:
        if m.security_id not in bars_sec_ids:
            v.append(Violation(
                Tier.CROSS_DOMAIN, Severity.HARD, "member_missing_bars",
                f"{_sym(m.security_id, m.symbol)} is a universe member as_of "
                f"{request.as_of} but has no bars in the snapshot",
                domain="bars", security_id=m.security_id, symbol=m.symbol,
                expected=">0 bar sessions", observed=0))

    # (b) gold must EQUAL bars per security (gold is a pure derivation of bars,
    #     so the invariant is equality, not mere containment — matches the
    #     Trading-OS-side 'gold rows exactly match bar rows' guarantee).
    #     bars - gold  -> gold_missing_sessions (the gold-lake failure class)
    #     gold - bars  -> gold_orphan_sessions  (should be impossible; a real defect)
    all_sec_ids = set(bars_by_sec) | set(gold_by_sec)
    for sid in all_sec_ids:
        b = bars_by_sec.get(sid)
        bars_sessions = set(b.session_dates) if b else set()
        gold_sessions = gold_by_sec.get(sid, set())
        # identity label: prefer bars' symbol, else gold's.
        symbol = (b.symbol if b else None) or next(
            (g.symbol for g in data.gold if g.security_id == sid), None)

        missing = bars_sessions - gold_sessions
        if missing:
            v.append(Violation(
                Tier.CROSS_DOMAIN, Severity.HARD, "gold_missing_sessions",
                f"{_sym(sid, symbol)} has {len(bars_sessions)} bar sessions in the "
                f"window but gold is missing {len(missing)} of them "
                f"(e.g. {sorted(missing)[:3]})",
                domain="gold", security_id=sid, symbol=symbol,
                expected=len(bars_sessions), observed=len(gold_sessions)))

        orphan = gold_sessions - bars_sessions
        if orphan:
            v.append(Violation(
                Tier.CROSS_DOMAIN, Severity.HARD, "gold_orphan_sessions",
                f"{_sym(sid, symbol)} has {len(orphan)} gold sessions with no "
                f"corresponding bars (e.g. {sorted(orphan)[:3]}); gold is derived "
                f"from bars, so this signals a stale or corrupt gold partition",
                domain="gold", security_id=sid, symbol=symbol,
                expected=len(bars_sessions), observed=len(gold_sessions)))
    return v


# --- Tier 4: empirical sanity (warnings; governed thresholds only) -----------

def check_empirical_sanity(data: PulledData, request: SnapshotRequest,
                           governed_min_members: int | None = None) -> list[Violation]:
    """Magnitude plausibility. WARNINGS by default — never an arbitrary hard band.
    A hard failure here requires an explicitly governed threshold passed in by the
    caller (e.g. from research policy), honoring the reviewer's rule that we do not
    reject legitimate data for failing a remembered empirical range."""
    v: list[Violation] = []
    n_members = len(data.members)

    # Governed hard threshold (only if the caller supplies one).
    if governed_min_members is not None and n_members < governed_min_members:
        v.append(Violation(
            Tier.EMPIRICAL_SANITY, Severity.HARD, "members_below_governed_min",
            f"universe has {n_members} members, below governed minimum "
            f"{governed_min_members}",
            domain="universe", expected=f">={governed_min_members}", observed=n_members))

    # Ungoverned plausibility -> WARNING only.
    if governed_min_members is None and n_members < 50:
        v.append(Violation(
            Tier.EMPIRICAL_SANITY, Severity.WARNING, "members_low",
            f"universe has only {n_members} members as_of {request.as_of}; unusually "
            f"low for a broad index (warning only — not a governed threshold)",
            domain="universe", observed=n_members))
    return v


# --- aggregate ----------------------------------------------------------------

def run_all_checks(data: PulledData, request: SnapshotRequest,
                   governed_min_members: int | None = None) -> list[Violation]:
    """Run all four tiers, return all violations (hard + warning)."""
    return (
        check_structural(data, request)
        + check_request_derived(data, request)
        + check_cross_domain(data, request)
        + check_empirical_sanity(data, request, governed_min_members)
    )


def blocking_violations(violations: list[Violation]) -> list[Violation]:
    """The subset that must block snapshot registration."""
    return [x for x in violations if x.is_blocking()]