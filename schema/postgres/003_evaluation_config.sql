-- 003_evaluation_config.sql
-- Magnuson Research OS — evaluation config registry (SCHEMA §4.2).
--
-- Versioned, append-only walk-forward methodology: scheme, purge/embargo specs,
-- metrics, and family-wise error thresholds (Gate 1 governance). Pinned by
-- eval_config_version in the reproducibility tuple.
--
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.evaluation_config (
    eval_config_version int primary key,
    scheme          text  not null,     -- 'expanding' | 'rolling'
    purge_spec      jsonb not null,     -- purge length as a function of horizon
    embargo_spec    jsonb not null,     -- embargo length as a function of horizon
    metrics_spec    jsonb not null,     -- which metrics are computed
    fwe_thresholds  jsonb not null,     -- family-wise error thresholds (Gate 1)
    rationale       text  not null,
    created_at      timestamptz not null default now()
);

comment on table research.evaluation_config is
  'Versioned append-only walk-forward methodology (SCHEMA §4.2, RD-004). Pinned by eval_config_version in the reproducibility tuple.';

-- Append-only enforcement (RD-004).
drop trigger if exists evaluation_config_no_mutate on research.evaluation_config;
create trigger evaluation_config_no_mutate
  before update or delete on research.evaluation_config
  for each row execute function research.deny_mutation();
