-- 010_signal_spec.sql
-- Magnuson Research OS — signal specification registry (SCHEMA §7.2, VISION §3.2).
--
-- Signals as DATA, not code: a declarative, versioned specification executed by
-- a generic engine. Immutable identity — a signal's lifecycle lives in
-- lifecycle_event; a new version is a new row (unique on name, version), never
-- a mutation. hypothesis is mandatory (Gate 4's raw material; keeps the factory
-- from degenerating into pure pattern-mining). created_by tags provenance
-- (RD-005): 'human' | 'grammar_sweep:<id>' | 'research_scheduler:<id>'.
--
-- features pins Trading OS features by (name, version) — matching meta.feature_definition.
-- universe_spec must resolve deterministically from the pinned snapshot's PIT
-- semantics, never today's membership (RD-014; enforced by the R1 engine).
--
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.signal_spec (
    spec_id       bigint generated always as identity primary key,
    name          text  not null,
    version       int   not null,
    family        text  not null,
    universe_spec jsonb not null,     -- PIT membership rule + as_of rule (not a ticker list); RD-014
    features      jsonb not null,     -- [{"name":"realized_vol20","version":1},...] pins by (name,version)
    transform     jsonb not null,     -- grammar AST
    horizon       text  not null,
    rebalance     text  not null,
    hypothesis    text  not null,     -- REQUIRED: why the edge exists; who is on the other side
    created_by    text  not null,     -- provenance (RD-005)
    created_at    timestamptz not null default now(),
    unique (name, version)
);

comment on table research.signal_spec is
  'Signal specification registry — signals as data (SCHEMA §7.2, VISION §3.2, RD-004). Immutable; a new version is a new row (unique name,version). hypothesis mandatory; provenance in created_by.';

-- Append-only enforcement (RD-004).
drop trigger if exists signal_spec_no_mutate on research.signal_spec;
create trigger signal_spec_no_mutate
  before update or delete on research.signal_spec
  for each row execute function research.deny_mutation();
