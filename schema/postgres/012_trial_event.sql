-- 012_trial_event.sql
-- Magnuson Research OS — trial event history (SCHEMA §7.4, VISION §3.1, RD-004).
--
-- Append-only history of what HAPPENED to a trial. Current trial state = the
-- event_type of the row with the GREATEST event_id (SCHEMA §3), not the latest
-- timestamp. Meaningful research-state transitions only (not function telemetry):
--   enumerated -> started -> completed | failed
-- The 'enumerated' event exists even for candidates a sweep enumerates but never
-- runs — the true trial count (the denominator of every significance calculation)
-- includes them (RD-004). Metrics and artifacts attach to the terminal
-- 'completed' event, keeping trial_ledger clean identity.
--
-- Depends on: research.trial_ledger (011).
-- Idempotent on the table; trigger creation guarded.

create table if not exists research.trial_event (
    event_id       bigint generated always as identity primary key,
    trial_id       bigint not null references research.trial_ledger(trial_id),
    event_type     text   not null check (event_type in
                       ('enumerated','started','completed','failed')),
    at             timestamptz not null default now(),
    by_whom        text,
    metrics        jsonb,              -- attached to the terminal 'completed' event
    artifacts_path text,
    artifacts_hash text                -- content hash for the reproducibility canary
);

comment on table research.trial_event is
  'Append-only trial state history (SCHEMA §7.4, VISION §3.1, RD-004). Current state = event_type of greatest event_id. enumerated events count toward the honest denominator even if never run.';

-- Append-only enforcement (RD-004).
drop trigger if exists trial_event_no_mutate on research.trial_event;
create trigger trial_event_no_mutate
  before update or delete on research.trial_event
  for each row execute function research.deny_mutation();
