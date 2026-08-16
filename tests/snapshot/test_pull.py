"""Orchestration tests, framed around the PRODUCTION pull (population = universe
members; requested_symbols=None). Fully isolated: DB writes use a rolled-back
connection, artifacts live under tmp_path.

Production failure modes the snapshot pull must catch:
  - member missing bars            -> hard, abort
  - member gold != bars (gold-lake)-> hard, abort
  - member unresolved by features  -> hard, abort
  - requested macro series absent  -> hard, abort
  - clean full pull                -> registers, no warnings
  - registration failure           -> orphan-and-name (structured recovery)
  - gold identity enrichment       -> gold rows tagged with security_id/symbol
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import pytest
from research_os.db import connect
from research_os.trading_os_client.client import (
    BarsResult, FeaturesResult, UniverseResult, MacroResult, TradingOsHttpError,
)
from research_os.snapshot.model import SnapshotRequest
from research_os.snapshot import pull as pull_mod
from research_os.snapshot.pull import (
    pull_snapshot, SnapshotPullAborted, SnapshotRegistrationError, SnapshotResult,
)

AS_OF = date(2008, 6, 30)
SESS = ["2008-06-02", "2008-06-03"]
MEMBERS = [(1, "AAPL"), (2, "MSFT")]


class FakeClient:
    """Models the production Trading OS. Population is the member set; failures
    are injected per-member: `no_bars_for`, `bad_gold_for` (gold != bars),
    `unresolved_for` (features reports the member unresolved). `missing_macro`
    makes a requested series absent."""
    def __init__(self, members, *, no_bars_for=None, bad_gold_for=None,
                 unresolved_for=None, missing_macro=None):
        self._members = members
        self._sec_by_symbol = {y: s for s, y in members}
        self._symbol_by_sec = {s: y for s, y in members}
        self._no_bars = set(no_bars_for or [])
        self._bad_gold = set(bad_gold_for or [])
        self._unresolved = set(unresolved_for or [])
        self._missing_macro = set(missing_macro or [])

    def universe(self, index, as_of):
        return UniverseResult(index=index, as_of=str(as_of), count=len(self._members),
                              members=[{"security_id": s, "symbol": y} for s, y in self._members])

    def universe_history(self, index, as_of):
        # Each member -> one membership interval, keyed on security_id, with the
        # ticker as fetch-convenience. Mirrors the production /history contract.
        from research_os.trading_os_client.client import UniverseHistoryResult
        intervals = [{"security_id": s, "valid_from": "2000-01-01",
                      "valid_to": None, "ticker": y} for s, y in self._members]
        return UniverseHistoryResult(
            index=index, as_of=str(as_of),
            interval_count=len(intervals),
            security_count=len({iv["security_id"] for iv in intervals}),
            intervals=intervals)

    def bars(self, symbol, as_of, start=None, end=None, adjustment=None):
        sid = self._sec_by_symbol[symbol]
        return self._bars_for(sid, symbol, as_of)

    def bars_by_id(self, security_id, as_of, adjustment=None):
        symbol = self._symbol_by_sec.get(security_id)
        return self._bars_for(security_id, symbol, as_of)

    def _bars_for(self, sid, symbol, as_of):
        no_bars = symbol in self._no_bars if symbol is not None else False
        sessions = [] if no_bars else SESS
        return BarsResult(symbol=symbol, security_id=sid, as_of=str(as_of),
                          count=len(sessions),
                          bars=[{"session_date": d, "open": 1.0, "high": 2.0, "low": 0.5,
                                 "close": 1.5, "volume": 100,
                                 "knowledge_time": f"{d}T15:00:00-06:00"} for d in sessions])

    def features(self, as_of, symbols=None, start=None, end=None):
        return self._features_for(self._sec_by_symbol.get(symbols[0]), symbols[0], as_of)

    def features_by_id(self, security_id, as_of):
        return self._features_for(security_id, self._symbol_by_sec.get(security_id), as_of)

    def _features_for(self, sid, sym, as_of):
        if sym in self._unresolved:
            return FeaturesResult(as_of=str(as_of), symbols=[], unresolved=[sym], count=0, rows=[])
        # bad_gold -> gold has FEWER sessions than bars (drop one) -> gold != bars
        sessions = SESS[:-1] if sym in self._bad_gold else SESS
        rows = [{"session_date": d, "adj_close": 1.5, "adj_volume": 100, "return_1d": 0.01,
                 "log_return_1d": 0.01, "sma20": 1.4, "sma50": 1.3, "ema20": 1.45,
                 "realized_vol20": 0.2, "roc20": 0.05, "momentum_12_1": 0.1,
                 "knowledge_time": f"{d}T15:00:00-06:00"} for d in sessions]
        return FeaturesResult(as_of=str(as_of), symbols=[sym], unresolved=[],
                              count=len(rows), rows=rows)

    def macro(self, series, as_of):
        if series in self._missing_macro:
            raise TradingOsHttpError(404, f"/v1/macro/{series}", "not found")
        return MacroResult(series_id=series, as_of=str(as_of), count=1,
                           observations=[{"obs_date": "2008-05-01", "value": "218.8",
                                          "vintage_date": "2008-06-15"}])

    def health_dq(self):
        return {"status": "ok", "failing_checks": 0}


@pytest.fixture
def rolled_back_conn():
    c = connect()
    c.autocommit = False
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def _req():
    """Production shape: requested_symbols=None -> population is the universe."""
    return SnapshotRequest(as_of=AS_OF, universe_code="SP500",
                           feature_versions=[{"name": "momentum_12_1", "version": 1}],
                           macro_series=["CPIAUCSL"], requested_symbols=None)


def _snapshot_count(conn):
    with conn.cursor() as cur:
        cur.execute("select count(*) from research.snapshot")
        return cur.fetchone()[0]


def test_clean_full_pull_registers(tmp_path, rolled_back_conn):
    before = _snapshot_count(rolled_back_conn)
    result = pull_snapshot(_req(), FakeClient(MEMBERS), tmp_path,
                           code_sha="test", conn=rolled_back_conn)
    assert isinstance(result, SnapshotResult)
    # It REGISTERS (no blocking violations). The only warning is the tier-4
    # low-member-count one, an artifact of the 2-member test fixture — never a
    # blocking violation. Assert no HARD violations leaked into warnings, and that
    # any warning present is the expected empirical-sanity one.
    assert all(w.severity.value == "warning" for w in result.warnings)
    assert all(w.tier.value == "empirical_sanity" for w in result.warnings)
    assert _snapshot_count(rolled_back_conn) == before + 1   # registered inside txn
    assert Path(result.path).exists()


def test_gold_identity_enrichment(tmp_path, monkeypatch, rolled_back_conn):
    captured = {}
    real_read = pull_mod.reader.read_pulled_data
    def spy(sd, *a, **k):
        d = real_read(sd, *a, **k); captured["d"] = d; return d
    monkeypatch.setattr(pull_mod.reader, "read_pulled_data", spy)
    pull_snapshot(_req(), FakeClient(MEMBERS), tmp_path, code_sha="test", conn=rolled_back_conn)
    assert {g.security_id for g in captured["d"].gold} == {1, 2}
    assert {g.symbol for g in captured["d"].gold} == {"AAPL", "MSFT"}


def test_member_missing_bars_aborts(tmp_path, rolled_back_conn):
    before = _snapshot_count(rolled_back_conn)
    client = FakeClient(MEMBERS, no_bars_for=["MSFT"])
    with pytest.raises(SnapshotPullAborted) as exc:
        pull_snapshot(_req(), client, tmp_path, code_sha="test", conn=rolled_back_conn)
    assert any(v.issue == "member_missing_bars" for v in exc.value.violations)
    assert _snapshot_count(rolled_back_conn) == before
    assert list(tmp_path.glob("*")) == []            # no finalized dir


def test_member_gold_not_equal_bars_aborts(tmp_path, rolled_back_conn):
    before = _snapshot_count(rolled_back_conn)
    client = FakeClient(MEMBERS, bad_gold_for=["AAPL"])   # AAPL gold missing a session
    with pytest.raises(SnapshotPullAborted) as exc:
        pull_snapshot(_req(), client, tmp_path, code_sha="test", conn=rolled_back_conn)
    assert any(v.issue == "gold_missing_sessions" and v.symbol == "AAPL"
               for v in exc.value.violations)
    assert _snapshot_count(rolled_back_conn) == before


def test_member_unresolved_by_features_aborts(tmp_path, rolled_back_conn):
    """MSFT is a member but features reports it unresolved. This must produce BOTH
    violations — proving run_all_checks reports everything wrong, not just the
    first problem (the diagnostic richness the gold-lake incident motivated):
      - member_unresolved_in_features (tier 2: the member wasn't served), and
      - gold_missing_sessions (tier 3: MSFT has bars but no gold)."""
    client = FakeClient(MEMBERS, unresolved_for=["MSFT"])
    with pytest.raises(SnapshotPullAborted) as exc:
        pull_snapshot(_req(), client, tmp_path, code_sha="test", conn=rolled_back_conn)
    codes = {v.issue for v in exc.value.violations}
    assert "member_unresolved_in_features" in codes
    assert "gold_missing_sessions" in codes           # both reported, not just first


def test_missing_macro_series_aborts(tmp_path, rolled_back_conn):
    """A required macro series that 404s is an INCOMPLETENESS fact: the pull catches
    the 404, omits the series, and tier-2 flags macro_series_missing -> abort.
    (A non-404/transport failure would instead propagate as infrastructure, not a
    completeness violation — tested separately below.)"""
    before = _snapshot_count(rolled_back_conn)
    client = FakeClient(MEMBERS, missing_macro=["CPIAUCSL"])
    with pytest.raises(SnapshotPullAborted) as exc:
        pull_snapshot(_req(), client, tmp_path, code_sha="test", conn=rolled_back_conn)
    assert any(v.issue == "macro_series_missing" for v in exc.value.violations)
    assert _snapshot_count(rolled_back_conn) == before


def test_macro_infrastructure_error_propagates(tmp_path, rolled_back_conn):
    """A non-404 macro failure (e.g. 500) is INFRASTRUCTURE, not incompleteness:
    it must propagate as the transport error, NOT be relabeled as missing data.
    Proves the completeness layer is not an exception sponge."""
    from research_os.trading_os_client.client import TradingOsHttpError
    class FiveHundredMacro(FakeClient):
        def macro(self, series, as_of):
            raise TradingOsHttpError(500, f"/v1/macro/{series}", "server error")
    with pytest.raises(TradingOsHttpError) as exc:
        pull_snapshot(_req(), FiveHundredMacro(MEMBERS), tmp_path,
                      code_sha="test", conn=rolled_back_conn)
    assert exc.value.status == 500                    # propagated, not swallowed


def test_registration_failure_orphans_and_names(tmp_path, monkeypatch):
    def boom():
        raise RuntimeError("simulated DB down")
    monkeypatch.setattr(pull_mod, "connect", boom)
    with pytest.raises(SnapshotRegistrationError) as exc:
        pull_snapshot(_req(), FakeClient(MEMBERS), tmp_path, code_sha="test")
    err = exc.value
    assert err.snapshot_path and Path(err.snapshot_path).exists()
    assert err.content_hash and len(err.content_hash) == 64
    assert err.manifest["scope"]["universe_code"] == "SP500"
    assert "orphan" in str(err).lower()


def test_full_history_population_is_not_survivor_only(tmp_path, monkeypatch, rolled_back_conn):
    """The survivorship guarantee: the pull population is EVERY security in the
    membership history, including a delisted one that is NOT a current member.
    A delisted security (id 3, ticker DEAD) present in the interval history must
    be pulled and staged — proving survivor-only population is impossible."""
    members = [(1, "AAPL"), (2, "MSFT"), (3, "DEAD")]   # 3 = delisted ex-member
    captured = {}
    real_read = pull_mod.reader.read_pulled_data
    def spy(sd, *a, **k):
        d = real_read(sd, *a, **k); captured["d"] = d; return d
    monkeypatch.setattr(pull_mod.reader, "read_pulled_data", spy)

    pull_snapshot(_req(), FakeClient(members), tmp_path,
                  code_sha="test", conn=rolled_back_conn)

    # all three securities — including the delisted one — are in the pulled data
    assert {g.security_id for g in captured["d"].gold} == {1, 2, 3}
    assert {m.security_id for m in captured["d"].members} == {1, 2, 3}
    # the delisted security's data is present, keyed on its stable security_id
    assert 3 in {b.security_id for b in captured["d"].bars}


def test_delisted_security_pulls_by_id_without_current_ticker(tmp_path, monkeypatch,
                                                              rolled_back_conn):
    """The by-id fetch path makes ticker reuse structurally irrelevant and lets a
    DELISTED security pull cleanly: fetching is keyed on security_id, so a member
    whose ticker no longer resolves at the current cutoff is still retrieved by
    id. Here security 3's ticker is absent from the fetch map entirely (as if
    delisted), yet its data is pulled and staged by security_id."""
    members = [(1, "AAPL"), (2, "MSFT"), (3, "DEAD")]
    captured = {}
    real_read = pull_mod.reader.read_pulled_data
    def spy(sd, *a, **k):
        d = real_read(sd, *a, **k); captured["d"] = d; return d
    monkeypatch.setattr(pull_mod.reader, "read_pulled_data", spy)

    class DelistedClient(FakeClient):
        """security 3 has no current-ticker symbol resolution (delisted), but
        bars_by_id / features_by_id still return its data keyed on security_id."""
        def bars(self, symbol, as_of, start=None, end=None, adjustment=None):
            raise AssertionError("pull must fetch by id, not symbol")
        def features(self, as_of, symbols=None, start=None, end=None):
            raise AssertionError("pull must fetch by id, not symbol")

    pull_snapshot(_req(), DelistedClient(members), tmp_path,
                  code_sha="test", conn=rolled_back_conn)
    # the delisted security (3) is present, keyed on its stable security_id
    assert {g.security_id for g in captured["d"].gold} == {1, 2, 3}
    assert 3 in {b.security_id for b in captured["d"].bars}