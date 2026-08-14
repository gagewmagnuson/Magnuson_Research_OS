"""Round-trip test: client results -> staged Parquet -> PulledData -> checks.

Proves the chain of custody: the completeness checks run on what was actually
persisted, and a clean pull round-trips to zero blocking violations. Uses
synthetic client-result objects (no live API) written to a tmp staging dir.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import pytest
from research_os.trading_os_client.client import (
    BarsResult, FeaturesResult, UniverseResult, MacroResult,
)
from research_os.snapshot import staging, reader
from research_os.snapshot.model import SnapshotRequest
from research_os.snapshot.completeness import run_all_checks, blocking_violations

AS_OF = date(2008, 6, 30)
SESS = ["2008-06-02", "2008-06-03", "2008-06-04"]


def _bars_result(sid, sym):
    return BarsResult(symbol=sym, security_id=sid, as_of=str(AS_OF), count=len(SESS),
                      bars=[{"session_date": d, "open": 1.0, "high": 2.0, "low": 0.5,
                             "close": 1.5, "volume": 100,
                             "knowledge_time": f"{d}T15:00:00-06:00"} for d in SESS])


def _features_result(secs):
    rows = []
    for sid, sym in secs:
        for d in SESS:
            rows.append({"security_id": sid, "symbol": sym, "session_date": d,
                         "adj_close": 1.5, "adj_volume": 100, "return_1d": 0.01,
                         "log_return_1d": 0.01, "sma20": 1.4, "sma50": 1.3,
                         "ema20": 1.45, "realized_vol20": 0.2, "roc20": 0.05,
                         "momentum_12_1": 0.1, "knowledge_time": f"{d}T15:00:00-06:00"})
    return FeaturesResult(as_of=str(AS_OF), symbols=[s for _, s in secs],
                          unresolved=[], count=len(rows), rows=rows)


def _universe_result(secs):
    return UniverseResult(index="SP500", as_of=str(AS_OF), count=len(secs),
                          members=[{"security_id": sid, "symbol": sym} for sid, sym in secs])


def _macro_result():
    return MacroResult(series_id="CPIAUCSL", as_of=str(AS_OF), count=2,
                       observations=[{"obs_date": "2008-05-01", "value": "218.8",
                                      "vintage_date": "2008-06-15"},
                                     {"obs_date": "2008-06-01", "value": "219.0",
                                      "vintage_date": "2008-07-15"}])


def test_round_trip_clean_snapshot(tmp_path):
    secs = [(1, "AAPL"), (2, "MSFT")]
    staging.write_bars([_bars_result(s, y) for s, y in secs], tmp_path)
    staging.write_gold(_features_result(secs), tmp_path)
    staging.write_universe(_universe_result(secs), tmp_path)
    staging.write_macro([_macro_result()], tmp_path)

    # read the STAGED artifact back
    data = reader.read_pulled_data(tmp_path, AS_OF, "SP500", features_unresolved=[])

    # reconstruction sanity
    assert {b.security_id for b in data.bars} == {1, 2}
    assert {g.security_id for g in data.gold} == {1, 2}
    assert {m.security_id for m in data.members} == {1, 2}
    assert data.bars[0].session_dates == [date(2008, 6, 2), date(2008, 6, 3), date(2008, 6, 4)]
    assert data.macro[0].series_id == "CPIAUCSL" and data.macro[0].observation_count == 2

    # checks pass on the round-tripped artifact
    req = SnapshotRequest(as_of=AS_OF, universe_code="SP500",
                          start=date(2008, 6, 2), end=date(2008, 6, 4),
                          feature_versions=[{"name": "momentum_12_1", "version": 1}],
                          macro_series=["CPIAUCSL"], requested_symbols=["AAPL", "MSFT"])
    assert blocking_violations(run_all_checks(data, req)) == []


def test_round_trip_detects_gold_gap(tmp_path):
    """The gold-lake failure survives the round trip: if gold is written missing a
    security, the reader+checks catch it on the STAGED artifact."""
    secs = [(1, "AAPL"), (2, "MSFT")]
    staging.write_bars([_bars_result(s, y) for s, y in secs], tmp_path)
    staging.write_gold(_features_result([(1, "AAPL")]), tmp_path)  # MSFT gold missing
    staging.write_universe(_universe_result(secs), tmp_path)
    staging.write_macro([_macro_result()], tmp_path)

    data = reader.read_pulled_data(tmp_path, AS_OF, "SP500", features_unresolved=[])
    req = SnapshotRequest(as_of=AS_OF, universe_code="SP500",
                          start=date(2008, 6, 2), end=date(2008, 6, 4),
                          feature_versions=[{"name": "momentum_12_1", "version": 1}],
                          macro_series=["CPIAUCSL"], requested_symbols=None)
    blocking = blocking_violations(run_all_checks(data, req))
    assert any(v.issue == "gold_missing_sessions" and v.security_id == 2 for v in blocking)