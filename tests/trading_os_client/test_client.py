"""Integration tests for the Trading OS client against the LIVE API.

Requires the Trading OS API running (default http://localhost:8000) and
TRADING_OS_API_KEY set. Skips cleanly if the API is unreachable or the key is
absent, so the suite still runs in environments without the Trading OS up.
"""
from __future__ import annotations
import pytest
from research_os.trading_os_client.config import TradingOsConfig, MissingApiKey
from research_os.trading_os_client.client import (
    TradingOsClient, TradingOsTransportError, TradingOsHttpError,
)


@pytest.fixture(scope="module")
def client():
    try:
        cfg = TradingOsConfig.from_env()
    except MissingApiKey:
        pytest.skip("TRADING_OS_API_KEY not set; skipping live Trading OS tests")
    c = TradingOsClient(cfg)
    # Probe reachability with a cheap call; skip if the API isn't up.
    try:
        c.bars("AAPL", as_of="2026-07-01", start="2020-01-02", end="2020-01-03")
    except TradingOsTransportError:
        pytest.skip("Trading OS API unreachable; skipping live tests")
    return c


def test_bars_shape(client):
    r = client.bars("AAPL", as_of="2026-07-01", start="2020-01-02", end="2020-01-10")
    assert r.symbol == "AAPL"
    assert r.count == len(r.bars) > 0
    assert "knowledge_time" in r.bars[0]
    assert "session_date" in r.bars[0]


def test_features_preserves_unresolved_empty(client):
    # AAPL resolves -> unresolved is empty, but the field is PRESENT.
    r = client.features(as_of="2026-07-01", symbols=["AAPL"],
                        start="2020-01-02", end="2020-01-10")
    assert r.count == len(r.rows) > 0
    assert r.unresolved == []
    assert "momentum_12_1" in r.rows[0]


def test_features_preserves_unresolved_nonempty(client):
    # A bad symbol must survive as `unresolved`, NOT be silently dropped.
    r = client.features(as_of="2026-07-01", symbols=["AAPL", "NOTATICKER"],
                        start="2020-01-02", end="2020-01-10")
    assert "NOTATICKER" in r.unresolved      # the whole point
    assert "NOTATICKER" not in (r.symbols or [])


def test_universe_shape(client):
    r = client.universe("SP500", as_of="2008-06-30")
    assert r.index == "SP500"
    assert r.count == len(r.members) > 100
    assert "security_id" in r.members[0]


def test_universe_unknown_index_raises(client):
    # 404 must raise, not return empty-as-success.
    with pytest.raises(TradingOsHttpError) as exc:
        client.universe("NOT_A_REAL_INDEX", as_of="2008-06-30")
    assert exc.value.status == 404


def test_macro_shape(client):
    r = client.macro("CPIAUCSL", as_of="2020-02-01")
    assert r.series_id == "CPIAUCSL"
    assert r.count == len(r.observations) > 0
    assert "vintage_date" in r.observations[0]