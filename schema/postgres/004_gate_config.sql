-- 004_gate_config.sql
-- Magnuson Research OS — gate config registry (SCHEMA §4.4).
--
-- Versioned, append-only gate configuration: thresholds, sample-size floors,
-- orthogonality limits. "How significant is significant" is itself governed
-- data (VISION §3.3), never a constant hidden in code. Referenced by
-- validation_result.gate_config_version.
--
-- gate_config_version is GLOBALLY unique across all gates; the `gate` column
-- names which gate a given version configures (SCHEMA §4.4).
--
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.gate_config (
    gate_config_version int primary key,   -- globally unique across all gates
    gate            text  not null check (gate in ('G1','G2','G3','G4','G5')),
    thresholds      jsonb not null,        -- e.g. min effective N, deflated-Sharpe cutoff, |rho| limit
    rationale       text  not null,
    created_at      timestamptz not null default now()
);

comment on table research.gate_config is
  'Versioned append-only gate configuration (SCHEMA §4.4, RD-004, VISION §3.3). Version numbers are global; the gate column names which gate each version configures.';

-- Append-only enforcement (RD-004).
drop trigger if exists gate_config_no_mutate on research.gate_config;
create trigger gate_config_no_mutate
  before update or delete on research.gate_config
  for each row execute function research.deny_mutation();
