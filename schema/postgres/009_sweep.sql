-- 009_sweep.sql
-- Magnuson Research OS — sweep registry (SCHEMA §7.1, RD-004, ROADMAP R2).
--
-- A sweep is a first-class research object: it owns an enumeration of candidate
-- signals, registered in full BEFORE evaluation begins, so the true trial count
-- (the denominator of every significance calculation) is honest. trial_ledger
-- references a sweep by sweep_id (null for one-off human trials).
--
-- Depends on: research.research_cycle (007).
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.sweep (
    sweep_id          bigint generated always as identity primary key,
    cycle_id          bigint not null references research.research_cycle(cycle_id),
    grammar_version   text   not null,      -- the grammar/version that produced the enumeration
    search_params     jsonb  not null,      -- the search-space definition for this sweep
    enumeration_count int    not null,      -- how many candidates were enumerated (honest denominator)
    created_by        text   not null,      -- 'grammar_sweep:<id>' | 'research_scheduler:<id>'
    created_at        timestamptz not null default now()
);

comment on table research.sweep is
  'Sweep registry (SCHEMA §7.1, RD-004). A first-class research object owning a pre-registered enumeration of candidates; enumeration_count is the honest denominator for significance.';

-- Append-only enforcement (RD-004).
drop trigger if exists sweep_no_mutate on research.sweep;
create trigger sweep_no_mutate
  before update or delete on research.sweep
  for each row execute function research.deny_mutation();
