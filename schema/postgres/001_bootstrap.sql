-- 001_bootstrap.sql
-- Magnuson Research OS — bootstrap infrastructure (must run FIRST).
--
-- Establishes the minimum foundation required before any domain migration and
-- before the migration runner can record anything:
--   1. the research schema
--   2. research.deny_mutation() — append-only enforcement (RD-004)
--   3. research.schema_migration — the applied-migration ledger
--   4. append-only protection on schema_migration itself
--
-- The tracking table is born already append-only (RD-004): the mechanism that
-- guarantees migration history does not itself violate the append-only rule at
-- any point, including during a fresh build. Domain migrations (002+) build on
-- this known foundation.
--
-- Idempotent: safe to re-run.

create schema if not exists research;

-- Append-only enforcement function (RD-004). Every research.* table attaches a
-- BEFORE UPDATE OR DELETE trigger that calls this. Corrections are new rows.
create or replace function research.deny_mutation() returns trigger as $$
begin
  raise exception 'research.% is append-only (RD-004); % denied',
    tg_table_name, tg_op;
end;
$$ language plpgsql;

comment on function research.deny_mutation() is
  'Append-only enforcement (RD-004). Attach as a BEFORE UPDATE OR DELETE row-level trigger to any research.* table. Raises on any mutation.';

-- Applied-migration ledger. Records which migrations have been applied, in order,
-- so a fresh database rebuilds reproducibly and the applied set is auditable.
create table if not exists research.schema_migration (
    filename    text primary key,
    applied_at  timestamptz not null default now(),
    checksum    text
);

comment on table research.schema_migration is
  'Applied migration ledger (RD-004, append-only). One row per migration file, in application order. Reversal is a new forward migration, never a delete.';

-- Append-only protection for the ledger itself, born with the table.
drop trigger if exists schema_migration_no_mutate on research.schema_migration;
create trigger schema_migration_no_mutate
  before update or delete on research.schema_migration
  for each row execute function research.deny_mutation();
