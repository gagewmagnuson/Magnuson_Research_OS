-- 008_research_cycle_event.sql
-- Magnuson Research OS — research cycle event history (SCHEMA §6.2, RD-007, RD-004).
--
-- Append-only state history for a research cycle. A cycle's current state is the
-- event_type of its event with the GREATEST event_id (SCHEMA §3 canonical
-- ordering) — NOT the latest timestamp. event_id is monotonic and is the sole
-- determinant of order; `at` is wall-clock annotation only. This guarantees
-- deterministic state reconstruction even when two events share a timestamp.
--
-- Depends on: research.research_cycle (007).
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.research_cycle_event (
    event_id   bigint generated always as identity primary key,
    cycle_id   bigint not null references research.research_cycle(cycle_id),
    event_type text   not null check (event_type in ('started','committed','failed')),
    at         timestamptz not null default now(),
    summary    jsonb                        -- durable handoff produced at commit
);

comment on table research.research_cycle_event is
  'Append-only research cycle state history (SCHEMA §6.2, RD-007, RD-004). Current state = event_type of the row with the greatest event_id for the cycle; `at` does not determine ordering.';

-- Append-only enforcement (RD-004).
drop trigger if exists research_cycle_event_no_mutate on research.research_cycle_event;
create trigger research_cycle_event_no_mutate
  before update or delete on research.research_cycle_event
  for each row execute function research.deny_mutation();
