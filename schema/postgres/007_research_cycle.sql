-- 007_research_cycle.sql
-- Magnuson Research OS — research cycle identity (SCHEMA §6.1, RD-007).
--
-- The operational unit of the loop. Immutable identity only: what governs the
-- cycle (policy_version), what data it reads (snapshot_id), optionally why it
-- exists (intent), who/what started it, and when. The cycle's STATE lives in
-- research_cycle_event (008) and is derived from the latest event by event_id;
-- there is no status column here.
--
-- Depends on: research.research_policy (005), research.snapshot (006).
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.research_cycle (
    cycle_id       bigint generated always as identity primary key,
    policy_version int    not null references research.research_policy(policy_version),
    snapshot_id    bigint not null references research.snapshot(snapshot_id),
    intent         text,                    -- optional machine-readable reason (nullable at R0);
                                            --   vocabulary governed when the scheduler is built
    created_by     text   not null,         -- 'human' | 'research_scheduler:<id>'
    started_at     timestamptz not null default now()
);

comment on table research.research_cycle is
  'Research cycle immutable identity (SCHEMA §6.1, RD-007, RD-004). State is derived from research_cycle_event by greatest event_id; no status column here.';

-- Append-only enforcement (RD-004).
drop trigger if exists research_cycle_no_mutate on research.research_cycle;
create trigger research_cycle_no_mutate
  before update or delete on research.research_cycle
  for each row execute function research.deny_mutation();
