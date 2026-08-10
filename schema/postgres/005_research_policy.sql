-- 005_research_policy.sql
-- Magnuson Research OS — research policy registry (SCHEMA §4.1, RD-010).
--
-- The human governor's retained authority as a first-class, versioned,
-- append-only object: admissible data, permitted model families, the cost
-- model in force (real FK to research.cost_model), and research budget.
-- Placeholder values are permitted early (RD-010); populated per phase.
--
-- Depends on: research.cost_model (004).
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.research_policy (
    policy_version     int primary key,
    admissible_data    jsonb not null,
    permitted_families jsonb not null,
    cost_model_version int   not null references research.cost_model(cost_model_version),
    research_budget    jsonb not null,
    rationale          text  not null,
    effective_from     timestamptz not null,
    created_by         text  not null,     -- always 'human' for policy
    created_at         timestamptz not null default now()
);

comment on table research.research_policy is
  'Versioned append-only research policy — the laws of the laboratory (SCHEMA §4.1, RD-010, RD-004). Cost assumptions resolve through a real cost_model_version FK.';

-- Append-only enforcement (RD-004).
drop trigger if exists research_policy_no_mutate on research.research_policy;
create trigger research_policy_no_mutate
  before update or delete on research.research_policy
  for each row execute function research.deny_mutation();
