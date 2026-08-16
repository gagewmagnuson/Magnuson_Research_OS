-- 015_known_no_data_security.sql
-- Magnuson Research OS — governed no-price-data exceptions.
--
-- Some securities were legitimately index members but have NO price data
-- available anywhere in the Trading OS (the data vendor, Tiingo, simply does
-- not carry them — e.g. equities delisted before Tiingo's delisted-coverage
-- window, or otherwise uncovered). Such a member correctly has zero bars.
--
-- WITHOUT governance, the completeness layer treats a member with zero bars as
-- a HARD failure (member_missing_bars) — which is exactly right for an
-- UNEXPECTED gap (e.g. a gold/bars pipeline problem). But for a KNOWN,
-- investigated data-availability limitation, hard-failing would either block
-- every snapshot forever or tempt a silent drop — and silently dropping a
-- historical member is precisely the survivorship bias the Research OS exists
-- to prevent. The member MUST remain in universe.parquet's membership history.
--
-- This table records, as IMMUTABLE APPEND-ONLY GOVERNANCE FACTS, the specific
-- securities whose absence of price data is KNOWN and ACCEPTED, with the reason
-- and source. Completeness consumes this set (passed in by orchestration, never
-- queried inside the pure check) to distinguish three states:
--   * member has bars                          -> normal
--   * member has no bars, IS in this set       -> accepted governed exception
--   * member has no bars, NOT in this set      -> HARD failure (unexpected gap)
--
-- NOT VERSIONED: these are immutable append-only facts. unique(security_id,
-- universe_code) + append-only means a decision, once recorded, is permanent.
-- There is deliberately NO status/effective-dating model — if a security ever
-- gains data and needs its exception revised, that requires a separate
-- governance-revision mechanism, intentionally not built now (RD-004 append-only
-- discipline; add complexity only when requirements demand it).
--
-- Recording rows in this table is a HUMAN governance act (recorded_by).
--
-- Depends on: bootstrap (001, research.deny_mutation).
-- Idempotent on the table; trigger creation guarded.
create table if not exists research.known_no_data_security (
    id            bigint generated always as identity primary key,
    security_id   bigint not null,
    universe_code text   not null,      -- the universe in which this member has no data
    reason        text   not null,      -- WHY there is no data (human-readable)
    source        text   not null,      -- the data source that lacks it (e.g. 'Tiingo')
    recorded_at   timestamptz not null default now(),
    recorded_by   text   not null,      -- human governance act
    unique (security_id, universe_code)
);
comment on table research.known_no_data_security is
  'Immutable append-only governance facts: securities that are legitimate members but have no available price data (accepted zero-bar exceptions). Completeness consumes this set to distinguish accepted governed exceptions from unexpected hard gaps. NOT versioned; no effective-dating. Members remain in universe.parquet (survivorship-correct).';
-- Append-only enforcement (RD-004).
drop trigger if exists known_no_data_security_no_mutate on research.known_no_data_security;
create trigger known_no_data_security_no_mutate
  before update or delete on research.known_no_data_security
  for each row execute function research.deny_mutation();