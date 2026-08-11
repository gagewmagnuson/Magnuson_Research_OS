"""B2: run_key structure + validation against the real registries (RD-003)."""
import pytest
from research_os.db import connect
from research_os.ledger.run_key import RunKey, validate, RunKeyValidationError


@pytest.fixture
def conn_rollback():
    """A connection whose transaction is always rolled back — tests never persist."""
    conn = connect()
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def referents(conn_rollback):
    """Insert a minimal valid set of referents inside the rolled-back txn.

    Returns the ids/versions a valid run_key should point at.
    """
    conn = conn_rollback
    with conn.cursor() as cur:
        cur.execute("""insert into research.cost_model
            (cost_model_version, commission_spec, spread_spec, impact_spec, scenarios, rationale)
            values (1,'{}','{}','{}','{}','t') returning cost_model_version""")
        cost = cur.fetchone()[0]
        cur.execute("""insert into research.evaluation_config
            (eval_config_version, scheme, purge_spec, embargo_spec, metrics_spec, fwe_thresholds, rationale)
            values (1,'expanding','{}','{}','{}','{}','t') returning eval_config_version""")
        evalc = cur.fetchone()[0]
        cur.execute("""insert into research.snapshot
            (trading_os_as_of, snapshot_date, path, manifest, content_hash)
            values ('2026-09-01 00:00:00+00','2026-09-01','/s','{}','H') returning snapshot_id""")
        snap = cur.fetchone()[0]
        cur.execute("""insert into research.signal_spec
            (name, version, family, universe_spec, features, transform, horizon, rebalance, hypothesis, created_by)
            values ('s',1,'x','{}','[]','{}','1d','daily','h','human') returning spec_id""")
        spec = cur.fetchone()[0]
    return {"spec_id": spec, "eval_config_version": evalc,
            "cost_model_version": cost, "data_as_of": snap}


def _rk(**overrides):
    base = dict(spec_id=1, feature_versions=[{"name": "momentum_12_1", "version": 1}],
                universe_spec={"membership": "SP500"}, eval_config_version=1,
                cost_model_version=1, data_as_of=1, code_sha="abc123", seed=42)
    base.update(overrides)
    return RunKey(**base)


def test_runkey_roundtrips_through_json():
    rk = _rk()
    assert RunKey.from_json(rk.to_json()) == rk


def test_valid_runkey_passes(conn_rollback, referents):
    rk = _rk(**referents)
    validate(rk, conn_rollback)  # should not raise


def test_bad_spec_id_rejected(conn_rollback, referents):
    rk = _rk(**{**referents, "spec_id": 999999})
    with pytest.raises(RunKeyValidationError, match="spec_id 999999"):
        validate(rk, conn_rollback)


def test_bad_snapshot_rejected(conn_rollback, referents):
    rk = _rk(**{**referents, "data_as_of": 999999})
    with pytest.raises(RunKeyValidationError, match="snapshot"):
        validate(rk, conn_rollback)


def test_bad_eval_config_rejected(conn_rollback, referents):
    rk = _rk(**{**referents, "eval_config_version": 999999})
    with pytest.raises(RunKeyValidationError, match="eval_config_version"):
        validate(rk, conn_rollback)


def test_malformed_feature_version_rejected(conn_rollback, referents):
    rk = _rk(**{**referents, "feature_versions": [{"name": "x"}]})  # missing version
    with pytest.raises(RunKeyValidationError, match="feature_versions"):
        validate(rk, conn_rollback)


def test_multiple_errors_all_reported(conn_rollback):
    # No referents inserted: everything should fail, all reported at once.
    rk = _rk()
    with pytest.raises(RunKeyValidationError) as exc:
        validate(rk, conn_rollback)
    msg = str(exc.value)
    assert "spec_id" in msg and "snapshot" in msg and "cost_model_version" in msg
