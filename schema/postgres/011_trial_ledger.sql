-- 011_trial_ledger.sql
-- Magnuson Research OS — trial ledger: immutable trial identity (SCHEMA §7.3, VISION §3.1).
--
-- The conscience of the factory. Registration only — what the trial IS:
--   run_key  = the serialized reproducibility contract (SCHEMA §8); the engine
--              validates every identifier in it against its registry before accepting.
--   spec_id  = what immutable specification it tests.
--   cycle_id = what research cycle created it.
--   sweep_id = which sweep enumerated it (null for one-off human trials).
-- What HAPPENS to the trial (enumerated->started->completed/failed) lives in
-- trial_event (012). An unlogged backtest is structurally impossible: this row
-- (and its 'enumerated' event) is the only door to evaluation (RD-003).
--
-- Depends on: signal_spec (010), research_cycle (007), sweep (009).
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.trial_ledger (
    trial_id      bigint generated always as identity primary key,
    run_key       jsonb  not null,     -- serialized reproducibility contract (SCHEMA §8)
    spec_id       bigint not null references research.signal_spec(spec_id),
    cycle_id      bigint not null references research.research_cycle(cycle_id),
    sweep_id      bigint references research.sweep(sweep_id),   -- null for one-off human trials
    enumerated_at timestamptz not null default now()
);

comment on table research.trial_ledger is
  'Trial ledger — immutable trial identity (SCHEMA §7.3, VISION §3.1, RD-004). run_key is the reproducibility contract; state lives in trial_event. The only door to evaluation.';

-- Append-only enforcement (RD-004).
drop trigger if exists trial_ledger_no_mutate on research.trial_ledger;
create trigger trial_ledger_no_mutate
  before update or delete on research.trial_ledger
  for each row execute function research.deny_mutation();
