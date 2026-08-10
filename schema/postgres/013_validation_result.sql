-- 013_validation_result.sql
-- Magnuson Research OS — validation result: the gauntlet's record (SCHEMA §7.5, RD-004).
--
-- Every gate decision is a row. Columns are named for exactly what they are (no
-- ambiguous 'spec' column):
--   trial_id            = the signal (via trial) being judged
--   gate                = which gate (G1..G5)
--   gate_config_version = the versioned gate CONFIGURATION used (FK to gate_config)
--   decision            = the gate's pass/fail call
--   criteria_metrics    = the numbers behind the decision
--   decided_by          = 'gauntlet' for G1-G3/G5; 'human:<id>' for G4
--
-- A trial may hold multiple results for the SAME gate under DIFFERENT configs
-- (a legitimate re-evaluation), so uniqueness is on (trial_id, gate,
-- gate_config_version) — not (trial_id, gate). Sequential gate ORDER (G(n+1)
-- only after G(n) passes) is a PROCESS invariant enforced by the gauntlet
-- engine, NOT the database (SCHEMA §1).
--
-- Depends on: trial_ledger (011), gate_config (004).
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.validation_result (
    result_id           bigint generated always as identity primary key,
    trial_id            bigint not null references research.trial_ledger(trial_id),
    gate                text   not null check (gate in ('G1','G2','G3','G4','G5')),
    gate_config_version int    not null references research.gate_config(gate_config_version),
    decision            text   not null check (decision in ('pass','fail')),
    criteria_metrics    jsonb  not null,
    decided_by          text   not null,
    decided_at          timestamptz not null default now(),
    unique (trial_id, gate, gate_config_version)
);

comment on table research.validation_result is
  'Gauntlet gate decisions (SCHEMA §7.5, RD-004). Named precisely (no ambiguous spec column). Unique on (trial_id, gate, gate_config_version); sequential gate order is engine logic, not DB.';

-- Append-only enforcement (RD-004).
drop trigger if exists validation_result_no_mutate on research.validation_result;
create trigger validation_result_no_mutate
  before update or delete on research.validation_result
  for each row execute function research.deny_mutation();
