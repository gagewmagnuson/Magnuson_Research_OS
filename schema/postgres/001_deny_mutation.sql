-- 001_deny_mutation.sql
-- Magnuson Research OS — append-only enforcement foundation (RD-004).
--
-- Creates the research schema and the deny_mutation() trigger function that
-- every fact/registry/event table attaches to. UPDATE and DELETE on any such
-- table raise an exception; corrections are new rows, never edits.
--
-- Idempotent: safe to re-run. Mirrors the Trading OS deny_mutation pattern.

create schema if not exists research;

create or replace function research.deny_mutation() returns trigger as $$
begin
  raise exception 'research.% is append-only (RD-004); % denied',
    tg_table_name, tg_op;
end;
$$ language plpgsql;

comment on function research.deny_mutation() is
  'Append-only enforcement (RD-004). Attach as a BEFORE UPDATE OR DELETE row-level trigger to any research.* table. Raises on any mutation.';
