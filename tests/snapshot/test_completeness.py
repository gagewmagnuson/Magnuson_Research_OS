"""Adversarial tests for the four-tier completeness checks.

Synthetic normalized data only — no API, no Parquet. Covers the reviewer's 11
cases plus the gold==bars equality invariant (both directions). Each broken
input asserts the SPECIFIC violation code, so a regression that stops catching a
failure class is caught here.
"""
from __future__ import annotations
from datetime import date
import pytest
from research_os.snapshot.model import (
    PulledData, SnapshotRequest, BarsSeries, GoldSeries, UniverseMember, MacroSeries,
)
from research_os.snapshot.violation import Tier, Severity
from research_os.snapshot.completeness import (
    check_structural, check_request_derived, check_cross_domain,
    check_empirical_sanity, run_all_checks, blocking_violations,
)

AS_OF = date(2008, 6, 30)
START = date(2008, 6, 2)
END = date(2008, 6, 4)
SESSIONS = [date(2008, 6, 2), date(2008, 6, 3), date(2008, 6, 4)]


def _request(**over):
    base = dict(
        as_of=AS_OF, universe_code="SP500", start=START, end=END,
        feature_versions=[{"name": "momentum_12_1", "version": 1}],
        macro_series=["CPIAUCSL"], requested_symbols=None,
    )
    base.update(over)
    return SnapshotRequest(**base)


def _good_data(**over):
    """A clean, complete snapshot: 2 members, both with matching bars & gold,
    macro present, nothing unresolved."""
    base = dict(
        as_of=AS_OF, universe_code="SP500",
        members=[UniverseMember(1, "AAPL"), UniverseMember(2, "MSFT")],
        bars=[BarsSeries(1, "AAPL", list(SESSIONS)), BarsSeries(2, "MSFT", list(SESSIONS))],
        gold=[GoldSeries(1, "AAPL", list(SESSIONS)), GoldSeries(2, "MSFT", list(SESSIONS))],
        macro=[MacroSeries("CPIAUCSL", 700)],
        features_unresolved=[],
    )
    base.update(over)
    return PulledData(**base)


def _codes(violations):
    return {v.issue for v in violations}


# --- 1 & 11: clean data passes; nothing blocks -------------------------------

def test_clean_data_no_violations():
    data, req = _good_data(), _request()
    all_v = run_all_checks(data, req)
    assert blocking_violations(all_v) == []          # registration can proceed
    # (may have zero warnings too here)
    assert all(v.severity is Severity.WARNING for v in all_v)


# --- 2: unresolved member -> hard failure ------------------------------------

def test_unresolved_member_is_hard():
    data = _good_data(features_unresolved=["AAPL"])   # AAPL IS a member
    v = check_request_derived(data, _request())
    hard = [x for x in v if x.issue == "member_unresolved_in_features"]
    assert hard and hard[0].severity is Severity.HARD
    assert hard[0].symbol == "AAPL"


# --- 3: unresolved nonmember -> warning --------------------------------------

def test_unresolved_nonmember_is_warning():
    data = _good_data(features_unresolved=["FAKE"])   # FAKE is NOT a member
    v = check_request_derived(data, _request())
    warn = [x for x in v if x.issue == "nonmember_unresolved"]
    assert warn and warn[0].severity is Severity.WARNING


# --- 4: former member at historical as_of with full data -> passes -----------

def test_historical_member_with_data_passes():
    """A security that is a member as_of the historical date and has its bars &
    gold for that window passes cleanly. (The checks consume the pull's historical
    membership; historical correctness of membership itself is guaranteed upstream
    by the universe endpoint's event-time rule + RD-014, not re-verified here.)"""
    # security 3 is a 2008 member (later delisted in reality) with full 2008 data.
    data = _good_data(
        members=[UniverseMember(3, "OLDCO")],
        bars=[BarsSeries(3, "OLDCO", list(SESSIONS))],
        gold=[GoldSeries(3, "OLDCO", list(SESSIONS))],
    )
    assert blocking_violations(run_all_checks(data, _request())) == []


# --- 5: member with bars but missing gold -> hard (the gold-lake case) -------

def test_member_bars_missing_gold_is_hard():
    data = _good_data(
        gold=[GoldSeries(1, "AAPL", list(SESSIONS)),
              GoldSeries(2, "MSFT", [])],           # MSFT gold empty
    )
    v = check_cross_domain(data, _request())
    miss = [x for x in v if x.issue == "gold_missing_sessions"]
    assert miss and miss[0].severity is Severity.HARD
    assert miss[0].symbol == "MSFT"
    assert miss[0].expected == 3 and miss[0].observed == 0


# --- 6: member with gold but no bars -> member_missing_bars + orphan gold -----

def test_member_gold_no_bars():
    data = _good_data(
        members=[UniverseMember(1, "AAPL")],
        bars=[],                                     # no bars at all
        gold=[GoldSeries(1, "AAPL", list(SESSIONS))],
    )
    codes = _codes(run_all_checks(data, _request()))
    assert "member_missing_bars" in codes            # member has no bars
    assert "gold_orphan_sessions" in codes           # its gold has no bars to match
    assert "empty_bars" in codes                     # structural: no bars


# --- 7: gold has sessions bars lack -> gold_orphan_sessions ------------------

def test_gold_orphan_sessions_is_hard():
    extra = SESSIONS + [date(2008, 6, 5)]            # gold has an extra session
    data = _good_data(
        gold=[GoldSeries(1, "AAPL", extra), GoldSeries(2, "MSFT", list(SESSIONS))],
    )
    v = check_cross_domain(data, _request())
    orph = [x for x in v if x.issue == "gold_orphan_sessions"]
    assert orph and orph[0].severity is Severity.HARD
    assert orph[0].symbol == "AAPL"


# --- 8: multiple simultaneous violations all returned ------------------------

def test_multiple_violations_all_returned():
    data = _good_data(
        members=[UniverseMember(1, "AAPL"), UniverseMember(2, "MSFT"),
                 UniverseMember(9, "GHOST")],        # GHOST has no bars
        gold=[GoldSeries(1, "AAPL", []),             # AAPL gold missing
              GoldSeries(2, "MSFT", list(SESSIONS))],
        macro=[],                                     # macro series missing
        features_unresolved=["MSFT"],                 # MSFT (member) unresolved
    )
    codes = _codes(run_all_checks(data, _request()))
    assert {"member_missing_bars", "gold_missing_sessions",
            "macro_series_missing", "member_unresolved_in_features"} <= codes


# --- 9 & 10: severity routing into blocking_violations -----------------------

def test_warning_not_blocking_hard_is_blocking():
    # nonmember unresolved -> warning; member missing bars -> hard.
    data = _good_data(
        members=[UniverseMember(1, "AAPL"), UniverseMember(9, "GHOST")],
        features_unresolved=["FAKE"],                 # warning
    )
    all_v = run_all_checks(data, _request())
    blocking = blocking_violations(all_v)
    assert any(v.issue == "nonmember_unresolved" for v in all_v)          # present
    assert all(v.issue != "nonmember_unresolved" for v in blocking)      # not blocking
    assert any(v.issue == "member_missing_bars" for v in blocking)       # hard blocks


# --- structural & request-derived extras -------------------------------------

def test_empty_universe_is_structural_hard():
    data = _good_data(members=[])
    v = check_structural(data, _request())
    assert "empty_universe" in _codes(v)


def test_macro_series_missing_is_hard():
    data = _good_data(macro=[])
    v = check_request_derived(data, _request())
    m = [x for x in v if x.issue == "macro_series_missing"]
    assert m and m[0].severity is Severity.HARD


def test_as_of_mismatch_structural():
    data = _good_data(as_of=date(2020, 1, 1))         # != request as_of
    assert "as_of_mismatch" in _codes(check_structural(data, _request()))


# --- tier 4: governed vs ungoverned ------------------------------------------

def test_tier4_low_members_warning_when_ungoverned():
    data = _good_data()                               # 2 members, < 50
    v = check_empirical_sanity(data, _request())      # no governed min
    low = [x for x in v if x.issue == "members_low"]
    assert low and low[0].severity is Severity.WARNING

def test_tier4_governed_min_makes_it_hard():
    data = _good_data()                               # 2 members
    v = check_empirical_sanity(data, _request(), governed_min_members=100)
    hard = [x for x in v if x.issue == "members_below_governed_min"]
    assert hard and hard[0].severity is Severity.HARD