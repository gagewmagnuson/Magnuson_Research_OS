"""B4: the ledgered entry point — the only door (RD-003, RD-011)."""
import pytest
from research_os.db import connect
from research_os.ledger.run_key import RunKey
from research_os.ledger.entry import open_trial, TrialRejected


@pytest.fixture
def conn_rollback():
    conn = connect()
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


@pytest.fixture
def world(conn_rollback):
    """A minimal valid world (referents + a cycle) inside the rolled-back txn."""
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
        cur.execute("""insert into research.research_policy
            (policy_version, admissible_data, permitted_families, cost_model_version,
             research_budget, rationale, effective_from, created_by)
            values (1,'{}','{}',1,'{}','p',now(),'human') returning policy_version""")
        pol = cur.fetchone()[0]
        cur.execute("""insert into research.snapshot
            (trading_os_as_of, snapshot_date, path, manifest, content_hash)
            values ('2026-09-01 00:00:00+00','2026-09-01','/s','{}','H') returning snapshot_id""")
        snap = cur.fetchone()[0]
        cur.execute("""insert into research.research_cycle
            (policy_version, snapshot_id, created_by)
            values (%s, %s, 'human') returning cycle_id""", (pol, snap))
        cyc = cur.fetchone()[0]
        cur.execute("""insert into research.signal_spec
            (name, version, family, universe_spec, features, transform, horizon, rebalance, hypothesis, created_by)
            values ('s',1,'x','{}','[]','{}','1d','daily','h','human') returning spec_id""")
        spec = cur.fetchone()[0]
    return {"cost": cost, "eval": evalc, "snap": snap, "cycle": cyc, "spec": spec}


def _rk(world, **overrides):
    base = dict(spec_id=world["spec"],
                feature_versions=[{"name": "momentum_12_1", "version": 1}],
                universe_spec={"membership": "SP500"},
                eval_config_version=world["eval"], cost_model_version=world["cost"],
                data_as_of=world["snap"], code_sha="deadbeef", seed=42)
    base.update(overrides)
    return RunKey(**base)


def _trial_count(conn):
    with conn.cursor() as cur:
        cur.execute("select count(*) from research.trial_ledger")
        return cur.fetchone()[0]


def test_valid_trial_is_written(conn_rollback, world):
    # enforce_clean_tree=False: this test isn't about git state (that's B3).
    tid = open_trial(_rk(world), world["cycle"], conn_rollback, enforce_clean_tree=False)
    with conn_rollback.cursor() as cur:
        cur.execute("select spec_id, cycle_id from research.trial_ledger where trial_id = %s", (tid,))
        assert cur.fetchone() == (world["spec"], world["cycle"])
        cur.execute("""select event_type from research.trial_event where trial_id = %s""", (tid,))
        assert cur.fetchone()[0] == "enumerated"


def test_invalid_runkey_writes_nothing(conn_rollback, world):
    before = _trial_count(conn_rollback)
    bad = _rk(world, spec_id=999999)
    with pytest.raises(TrialRejected, match="RD-003"):
        open_trial(bad, world["cycle"], conn_rollback, enforce_clean_tree=False)
    assert _trial_count(conn_rollback) == before   # structural refusal: nothing written


def test_bad_cycle_writes_nothing(conn_rollback, world):
    before = _trial_count(conn_rollback)
    with pytest.raises(TrialRejected, match="cycle_id"):
        open_trial(_rk(world), 999999, conn_rollback, enforce_clean_tree=False)
    assert _trial_count(conn_rollback) == before


def test_sha_mismatch_rejected(conn_rollback, world):
    # enforce_clean_tree=True: the run_key sha won't match real HEAD (and/or tree
    # is dirty during dev), so this must be rejected under RD-011.
    with pytest.raises(TrialRejected, match="RD-011"):
        open_trial(_rk(world, code_sha="0"*40), world["cycle"], conn_rollback,
                   enforce_clean_tree=True)