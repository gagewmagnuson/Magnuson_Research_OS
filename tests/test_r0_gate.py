"""B5 — the R0 gate (ROADMAP R0).

Proves the skeleton of honesty holds end-to-end:
  1. a trivial spec passes through the ledger door and is recorded;
  2. the persisted run_key regenerates an identical RunKey (reproducibility spine);
  3. there is no admitted trial that skipped validation — the door is the only way in.

All work happens inside a rolled-back transaction; the database is left pristine.
"""
import pytest
from research_os.db import connect
from research_os.ledger.run_key import RunKey, validate, RunKeyValidationError
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
            values (%s,%s,'human') returning cycle_id""", (pol, snap))
        cyc = cur.fetchone()[0]
        cur.execute("""insert into research.signal_spec
            (name, version, family, universe_spec, features, transform, horizon, rebalance, hypothesis, created_by)
            values ('trivial',1,'x','{"membership":"SP500"}','[{"name":"momentum_12_1","version":1}]',
                    '{"node":"rank"}','21d','monthly','trivial R0 spec','human') returning spec_id""")
        spec = cur.fetchone()[0]
    return {"cost": cost, "eval": evalc, "snap": snap, "cycle": cyc, "spec": spec}


def _trivial_runkey(world):
    return RunKey(
        spec_id=world["spec"],
        feature_versions=[{"name": "momentum_12_1", "version": 1}],
        universe_spec={"membership": "SP500", "as_of_rule": "rebalance_date"},
        eval_config_version=world["eval"],
        cost_model_version=world["cost"],
        data_as_of=world["snap"],
        code_sha="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
        seed=42,
    )


def test_r0_gate_end_to_end(conn_rollback, world):
    rk = _trivial_runkey(world)

    # (1) End-to-end: the trivial spec passes through the door and is recorded.
    trial_id = open_trial(rk, world["cycle"], conn_rollback, enforce_clean_tree=False)
    assert trial_id is not None

    # (2) Regenerates from its tuple: the persisted run_key round-trips exactly.
    with conn_rollback.cursor() as cur:
        cur.execute("select run_key from research.trial_ledger where trial_id = %s", (trial_id,))
        stored = cur.fetchone()[0]           # psycopg returns jsonb as a dict
        import json
        regenerated = RunKey.from_json(json.dumps(stored))
        assert regenerated == rk             # bit-for-bit identical to what we submitted

        # and the opening event exists
        cur.execute("select event_type from research.trial_event where trial_id = %s", (trial_id,))
        assert cur.fetchone()[0] == "enumerated"


def test_r0_gate_out_of_ledger_fails_structurally(conn_rollback, world):
    # An "evaluation" that skips the door cannot produce a valid, admitted trial:
    # the only way to get a trial_id is through open_trial, which always validates.
    # A run_key referencing a nonexistent spec is refused; nothing is written.
    bad = RunKey(
        spec_id=999999, feature_versions=[{"name": "x", "version": 1}],
        universe_spec={}, eval_config_version=world["eval"],
        cost_model_version=world["cost"], data_as_of=world["snap"],
        code_sha="0"*40, seed=1,
    )
    with conn_rollback.cursor() as cur:
        cur.execute("select count(*) from research.trial_ledger")
        before = cur.fetchone()[0]

    with pytest.raises(TrialRejected):
        open_trial(bad, world["cycle"], conn_rollback, enforce_clean_tree=False)

    with conn_rollback.cursor() as cur:
        cur.execute("select count(*) from research.trial_ledger")
        assert cur.fetchone()[0] == before   # structurally: no trial admitted

    # And the validator itself refuses the bad tuple directly (defense in depth).
    with pytest.raises(RunKeyValidationError):
        validate(bad, conn_rollback)