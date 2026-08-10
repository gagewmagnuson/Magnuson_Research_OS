-- 006_snapshot.sql
-- Magnuson Research OS — snapshot catalogue (SCHEMA §5.1, RD-002).
--
-- Catalogues immutable PIT datasets pulled monthly from the Trading OS through
-- the as_of contract. A row's existence MEANS "complete, hashed, verified":
-- failed pulls never become rows, so there is no status column.
--
-- trading_os_as_of = the exact PIT knowledge cutoff sent upstream (governs WHAT DATA).
-- snapshot_date    = the Research OS logical research-period label (human/scheduler handle);
--                    intentionally NOT unique — a re-pull for the same date is a distinct
--                    immutable artifact with its own snapshot_id (RD-002, review item on re-pull).
-- The reproducibility tuple references snapshot_id (the artifact), never the date.
--
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.snapshot (
    snapshot_id      bigint generated always as identity primary key,
    trading_os_as_of timestamptz not null,
    snapshot_date    date        not null,   -- NOT unique by design
    path             text        not null,
    manifest         jsonb       not null,
    content_hash     text        not null,   -- integrity identity; algorithm governed (RD-013)
    pulled_at        timestamptz not null default now()
);

comment on table research.snapshot is
  'Immutable PIT snapshot catalogue (SCHEMA §5.1, RD-002, RD-004). Row existence means complete/verified; failed pulls are never cataloged. snapshot_date is intentionally not unique; the tuple references snapshot_id.';

-- Append-only enforcement (RD-004).
drop trigger if exists snapshot_no_mutate on research.snapshot;
create trigger snapshot_no_mutate
  before update or delete on research.snapshot
  for each row execute function research.deny_mutation();
