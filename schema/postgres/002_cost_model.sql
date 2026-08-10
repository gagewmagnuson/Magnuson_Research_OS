-- 002_cost_model.sql
-- Magnuson Research OS — cost model registry (SCHEMA §4.3).
--
-- Versioned, append-only cost assumptions (commission, spread, impact, scenarios).
-- Every trial evaluates under a pinned cost_model_version; an edge that exists
-- only at zero cost is a failure, not a caveat. research_policy references this
-- table by FK (SCHEMA §4.1), so it must exist first.
--
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.cost_model (
    cost_model_version int primary key,
    commission_spec jsonb not null,
    spread_spec     jsonb not null,
    impact_spec     jsonb not null,
    scenarios       jsonb not null,     -- optimistic / base / stressed
    rationale       text not null,
    created_at      timestamptz not null default now()
);

comment on table research.cost_model is
  'Versioned append-only cost assumptions (SCHEMA §4.3, RD-004). Pinned by cost_model_version in the reproducibility tuple and referenced by research_policy.';

-- Append-only enforcement (RD-004).
drop trigger if exists cost_model_no_mutate on research.cost_model;
create trigger cost_model_no_mutate
  before update or delete on research.cost_model
  for each row execute function research.deny_mutation();
