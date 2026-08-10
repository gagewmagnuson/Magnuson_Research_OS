-- 014_lifecycle_event.sql
-- Magnuson Research OS — signal lifecycle events (SCHEMA §7.6, RD-006, RD-004).
--
-- Append-only history of signal lifecycle transitions. A signal's current
-- lifecycle state = the to_state of the row with the greatest event_id.
--
-- THE PERMANENT CAPITAL BOUNDARY (RD-006), enforced by the database itself:
-- a transition to 'live' MUST have a human decided_by. The machine may propose
-- promotions and may automate demotion/retirement, but promoting a signal to
-- live capital is a deliberate human act with a recorded rationale, in every
-- version of this system, forever. This is a STRUCTURAL invariant (DB CHECK).
--
-- The permitted transition GRAPH (which from_state->to_state edges are legal)
-- is a PROCESS invariant enforced by the lifecycle manager and governed in
-- DECISIONS (RD-012) — deliberately NOT encoded as CHECK constraints, to keep
-- the graph in one governed place. The one structural exception is this
-- live-promotion-is-human rule.
--
-- Depends on: signal_spec (010), research_cycle (007).
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.lifecycle_event (
    event_id   bigint generated always as identity primary key,
    spec_id    bigint not null references research.signal_spec(spec_id),
    cycle_id   bigint not null references research.research_cycle(cycle_id),
    from_state text   not null,
    to_state   text   not null check (to_state in
                   ('candidate','validating','paper','live','decaying','retired')),
    evidence   jsonb  not null,     -- validation_result ids supporting the transition
    decided_by text   not null,
    rationale  text   not null,
    decided_at timestamptz not null default now(),
    -- RD-006: promotion to live is a human act. STRUCTURAL invariant.
    constraint live_promotion_is_human check (
        to_state <> 'live' or decided_by like 'human:%'
    )
);

comment on table research.lifecycle_event is
  'Signal lifecycle history (SCHEMA §7.6, RD-006, RD-004). Current state = to_state of greatest event_id. live promotion requires human decided_by (permanent capital boundary, enforced by DB). Transition graph is governed process logic (RD-012).';

-- Append-only enforcement (RD-004).
drop trigger if exists lifecycle_event_no_mutate on research.lifecycle_event;
create trigger lifecycle_event_no_mutate
  before update or delete on research.lifecycle_event
  for each row execute function research.deny_mutation();
