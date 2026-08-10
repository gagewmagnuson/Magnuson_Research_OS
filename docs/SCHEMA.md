# SCHEMA.md — Magnuson Research OS

*Status: ACCEPTED*
*Ratified: 2026-08-07 (rev. 2 — structural integrity fixes; see change log §11)*
*Governing document. Subordinate to VISION.md, ARCHITECTURE.md, and DECISIONS.md. No implementation may violate this without an explicit, dated amendment.*

---

## 1. Purpose and scope

This document defines the concrete `research.*` Postgres schema: the identity registries, their append-only event histories, the research cycle, the research policy, the snapshot catalogue, sweeps, and the exact fields of the reproducibility tuple.

Principles it enforces, all traceable to prior documents:
- **Append-only everywhere** (RD-004): every table carries a `deny_mutation` trigger. State that changes over time is an **append-only event history**, never a mutable status column.
- **The tuple is the only entry point** (RD-003): the ledgered evaluation engine accepts a `run_key` and nothing else; every identifier in that tuple resolves to a real, versioned, append-only row.
- **Identity vs. events** (rev. 2): a thing's immutable identity lives in a registry table; what *happens* to it lives in an append-only event table; its current state is *derived from its latest event by `event_id`* (not by timestamp — see §3). This one pattern governs signals, cycles, and trials.
- **Structural vs. process invariants** (rev. 2): the database enforces *structural* invariants (things that must be impossible — e.g. live promotion by a non-human); the engine enforces *process* invariants (things that must follow an order — e.g. the gauntlet sequence, the lifecycle transition graph). The schema does not encode the full state machines; those are governed in DECISIONS and enforced in code.
- **The research cycle is the operational unit** (RD-007); **provenance is first-class** (RD-005); **governed parameters have a home** (RD-008, RD-010).

Types are PostgreSQL; all timestamps are `timestamptz` (UTC).

## 2. The append-only guarantee

```sql
create or replace function research.deny_mutation() returns trigger as $$
begin
  raise exception 'research.% is append-only (RD-004); mutation denied', tg_table_name;
end;
$$ language plpgsql;

-- applied per table:
--   create trigger <t>_no_mutate before update or delete on research.<t>
--     for each row execute function research.deny_mutation();
```

Every `create table` below carries this trigger. No table has a mutable `status` column; transitions are event rows.

## 3. The identity / event pattern and canonical ordering

Signals, research cycles, and trials each have: an **identity table** (immutable facts, written once), an **event table** (append-only meaningful state transitions), and **derived state**.

**Canonical ordering (rev. 2, RD-004).** Current state is the `event_type` of the event with the **greatest `event_id`** for that object. `event_id` is a monotonic identity column and is the sole determinant of order. The `at` timestamp records wall-clock occurrence for audit but **does not** determine ordering — two events may share an `at` value; they can never share an `event_id`. This guarantees deterministic state reconstruction.

Events represent research-meaningful transitions only — never function-level telemetry.

## 4. Governed-parameter registries

Versioned, append-only. The tuple pins a *version*; the version dereferences here.

### 4.1 `research.research_policy` (RD-010)

```sql
create table research.research_policy (
    policy_version     int primary key,
    admissible_data    jsonb not null,
    permitted_families jsonb not null,
    cost_model_version int not null references research.cost_model(cost_model_version), -- rev.2: real FK, not a jsonb blob
    research_budget    jsonb not null,
    rationale          text not null,
    effective_from     timestamptz not null,
    created_by         text not null,    -- always 'human' for policy
    created_at         timestamptz not null default now()
);
```

Rev. 2: cost assumptions now resolve through a real `cost_model_version` FK rather than a free-form jsonb description, so the policy's cost reference is unambiguous (review item 8 / RD-013). Placeholder values still permitted early (RD-010).

### 4.2 `research.evaluation_config`

```sql
create table research.evaluation_config (
    eval_config_version int primary key,
    scheme          text not null,     -- 'expanding' | 'rolling'
    purge_spec      jsonb not null,
    embargo_spec    jsonb not null,
    metrics_spec    jsonb not null,
    fwe_thresholds  jsonb not null,
    rationale       text not null,
    created_at      timestamptz not null default now()
);
```

### 4.3 `research.cost_model`

```sql
create table research.cost_model (
    cost_model_version int primary key,
    commission_spec jsonb not null,
    spread_spec     jsonb not null,
    impact_spec     jsonb not null,
    scenarios       jsonb not null,     -- optimistic / base / stressed
    rationale       text not null,
    created_at      timestamptz not null default now()
);
```

### 4.4 `research.gate_config`

```sql
create table research.gate_config (
    gate_config_version int primary key,   -- globally unique across all gates
    gate            text not null check (gate in ('G1','G2','G3','G4','G5')),
    thresholds      jsonb not null,
    rationale       text not null,
    created_at      timestamptz not null default now()
);
```

Version numbers are global (not per-gate); `gate` names which gate a version configures. (Clarifies review item 7.)

## 5. The snapshot catalogue

### 5.1 `research.snapshot` (RD-002)

Catalogues snapshots that exist and are trustworthy — never attempts. A row's existence means "complete"; a failed pull never becomes a row (no status column).

```sql
create table research.snapshot (
    snapshot_id      bigint generated always as identity primary key,
    trading_os_as_of timestamptz not null,  -- exact PIT knowledge cutoff SENT upstream; governs WHAT DATA.
    snapshot_date    date not null,          -- Research OS logical period label; a human/scheduler handle.
                                             --   NOT unique: a re-pull for the same date is a distinct artifact.
    path             text not null,
    manifest         jsonb not null,
    content_hash     text not null,          -- integrity identity of the artifact; definition governed (RD-013)
    pulled_at        timestamptz not null default now()
);
```

`trading_os_as_of` (what data) and `snapshot_date` (which period) are different kinds of thing and are never collapsed. The tuple points at `snapshot_id`, the artifact itself. The precise, stable definition of `content_hash` is a governed deferred item (RD-013).

## 6. The research cycle (RD-007)

### 6.1 `research.research_cycle` — immutable identity

```sql
create table research.research_cycle (
    cycle_id        bigint generated always as identity primary key,
    policy_version  int not null references research.research_policy(policy_version),
    snapshot_id     bigint not null references research.snapshot(snapshot_id),
    intent          text,                    -- rev.2: optional machine-readable reason the cycle exists
                                             --   (e.g. 'grammar_expansion','sparse_region_exploration',
                                             --    'decay_monitoring','portfolio_rebalance'); nullable at R0.
    created_by      text not null,           -- 'human' | 'research_scheduler:<id>'
    started_at      timestamptz not null default now()
);
```

`intent` is a cheap forward-investment (review item 14): nullable now, it lets a future scheduler answer "why did the system spend budget on this?" without a retrofit. Not required at R0; its controlled vocabulary is governed when the scheduler is built.

### 6.2 `research.research_cycle_event` — append-only state

```sql
create table research.research_cycle_event (
    event_id    bigint generated always as identity primary key,
    cycle_id    bigint not null references research.research_cycle(cycle_id),
    event_type  text not null check (event_type in ('started','committed','failed')),
    at          timestamptz not null default now(),
    summary     jsonb                        -- durable handoff produced at commit
);
```

State derived by greatest `event_id` (§3).

## 7. Sweeps and the registries

### 7.1 `research.sweep` — immutable sweep identity (rev. 2; RD-004, ROADMAP R2)

A sweep is a first-class research object: it owns an enumeration of candidates, registered in full **before** evaluation so the true trial count is honest. `trial_ledger.sweep_id` references it.

```sql
create table research.sweep (
    sweep_id         bigint generated always as identity primary key,
    cycle_id         bigint not null references research.research_cycle(cycle_id),
    grammar_version  text not null,          -- the grammar/version that produced the enumeration
    search_params    jsonb not null,         -- the search-space definition for this sweep
    enumeration_count int not null,          -- how many candidates were enumerated (the honest denominator)
    created_by       text not null,          -- 'grammar_sweep:<id>' | 'research_scheduler:<id>'
    created_at       timestamptz not null default now()
);
```

### 7.2 `research.signal_spec` (VISION §3.2 — signals as data)

```sql
create table research.signal_spec (
    spec_id     bigint generated always as identity primary key,
    name        text not null,
    version     int  not null,
    family      text not null,
    universe_spec jsonb not null,    -- PIT membership rule + as_of rule (not a ticker list); see §8 note
    features    jsonb not null,      -- [{"name":"realized_vol20","version":1},...] pins by (name,version)
    transform   jsonb not null,      -- grammar AST
    horizon     text not null,
    rebalance   text not null,
    hypothesis  text not null,       -- REQUIRED: why the edge exists; who is on the other side
    created_by  text not null,       -- 'human' | 'grammar_sweep:<id>' | 'research_scheduler:<id>'
    created_at  timestamptz not null default now(),
    unique (name, version)
);
```

### 7.3 `research.trial_ledger` — immutable trial identity (VISION §3.1)

Registration only. What the trial IS.

```sql
create table research.trial_ledger (
    trial_id      bigint generated always as identity primary key,
    run_key       jsonb  not null,   -- serialized reproducibility contract (§8)
    spec_id       bigint not null references research.signal_spec(spec_id),
    cycle_id      bigint not null references research.research_cycle(cycle_id),
    sweep_id      bigint references research.sweep(sweep_id),   -- rev.2: real FK; null for one-off human trials
    enumerated_at timestamptz not null default now()
);
```

### 7.4 `research.trial_event` — append-only trial history

```sql
create table research.trial_event (
    event_id    bigint generated always as identity primary key,
    trial_id    bigint not null references research.trial_ledger(trial_id),
    event_type  text not null check (event_type in ('enumerated','started','completed','failed')),
    at          timestamptz not null default now(),
    by_whom     text,
    metrics     jsonb,               -- attached to the terminal 'completed' event
    artifacts_path text,
    artifacts_hash text               -- content hash for the reproducibility canary
);
```

Current trial state = latest event by `event_id` (§3). The `enumerated` event exists even for candidates a sweep never runs (RD-004): the true trial count includes them.

### 7.5 `research.validation_result` — the gauntlet's record

No column named `spec`. A trial may hold multiple results for the same gate **under different gate configurations** (a legitimate re-evaluation), so uniqueness is on the triple, not the pair.

```sql
create table research.validation_result (
    result_id           bigint generated always as identity primary key,
    trial_id            bigint not null references research.trial_ledger(trial_id),
    gate                text not null check (gate in ('G1','G2','G3','G4','G5')),
    gate_config_version int not null references research.gate_config(gate_config_version),
    decision            text not null check (decision in ('pass','fail')),
    criteria_metrics    jsonb not null,
    decided_by          text not null,    -- 'gauntlet' for G1-G3/G5; 'human:<id>' for G4
    decided_at          timestamptz not null default now(),
    unique (trial_id, gate, gate_config_version)   -- rev.2: structural. Sequential gate ORDER is engine logic.
);
```

Sequential enforcement ("a trial reaches G(n+1) only after G(n) passes") is a **process invariant** enforced by the gauntlet engine, not the database (§1). The database prevents duplicate results for the same (trial, gate, config); it does not encode gate order.

### 7.6 `research.lifecycle_event` (RD-006 — governance)

```sql
create table research.lifecycle_event (
    event_id    bigint generated always as identity primary key,
    spec_id     bigint not null references research.signal_spec(spec_id),
    cycle_id    bigint not null references research.research_cycle(cycle_id),
    from_state  text not null,
    to_state    text not null check (to_state in
                    ('candidate','validating','paper','live','decaying','retired')),
    evidence    jsonb not null,     -- validation_result ids supporting the transition
    decided_by  text not null,
    rationale   text not null,
    decided_at  timestamptz not null default now(),
    constraint live_promotion_is_human check (   -- RD-006: STRUCTURAL invariant, enforced by the DB
        to_state <> 'live' or decided_by like 'human:%'
    )
);
```

The **permitted transition graph** (which `from_state → to_state` edges are legal) is a **process invariant** enforced by the lifecycle manager and governed in DECISIONS (RD-012), not encoded as CHECK constraints — keeping the graph in one governed place rather than split between DB and engine. The one exception is the live-promotion-is-human rule, which is genuinely structural and stays in the schema.

## 8. The reproducibility tuple (`run_key`)

Stored on every trial (§7.3). It is a **serialized reproducibility contract** whose identifiers resolve to immutable governed registries — not literally database foreign keys, but IDs the engine MUST validate against those registries before accepting the trial.

```
run_key = {
    "spec_id":             <resolves to signal_spec.spec_id — uniquely identifies the immutable spec+version>,
    "feature_versions":    [ {"name": ..., "version": ...}, ... ],   -- Trading OS (name, version)
    "universe_spec":       { membership rule + as_of rule },         -- must resolve deterministically; see note
    "eval_config_version": <resolves to evaluation_config.eval_config_version>,
    "cost_model_version":  <resolves to cost_model.cost_model_version>,
    "data_as_of":          <resolves to snapshot.snapshot_id — the immutable artifact, by identity>,
    "code_sha":            <Research OS git commit — always a COMMITTED sha (RD-011)>,
    "seed":                <int>
}
```

Rev. 2 changes:
- **`spec_version` removed** (review item 4/6, Option A): `spec_id` already uniquely identifies an immutable row that contains its own version; carrying a separate `spec_version` in jsonb created a value that could disagree with no way to enforce agreement. `spec_id` alone is unambiguous.
- **`universe_spec` determinism requirement** (review item 5; RD-014): a universe specification MUST resolve deterministically from the pinned snapshot's `as_of` semantics — the eligible universe as knowable at the relevant historical knowledge cutoff, never today's membership. This is the PIT lesson of the stress test carried into research. Stated here; enforced by the R1 engine.

**Reproducibility claim (rev. 2, honest form; RD-013).** At R0–R2, where evaluation is deterministic vectorized computation (Polars/DuckDB) over fixed Parquet, artifacts regenerate **bit-for-bit** from the tuple. This guarantee is conditional on a fixed computational environment. Before nondeterministic model families (ML/RL/GPU) are introduced, the reproducibility contract MUST additionally pin the execution environment (image / dependency lock) sufficiently to reproduce artifacts deterministically. Until then, `code_sha` + deterministic engine suffices; the environment-pinning requirement is a governed deferred item (RD-013).

**The rule (RD-003).** The ledgered engine accepts a `run_key` and nothing else, and validates every identifier against its registry before accepting the trial. A number that cannot be regenerated from its tuple (under the environment condition above) is a P0 defect.

## 9. Relationships (one view)

```
research_policy ─┐                              cost_model ─┘ (policy → cost_model_version)
                 ├─< research_cycle >─< research_cycle_event
snapshot ────────┘        │
                          ├─< sweep >─┐
                          │           │
                          ├─< trial_ledger >─< trial_event
                          │        │   (sweep_id → sweep)
                          │        └─< validation_result >─ gate_config
                          │              unique(trial_id, gate, gate_config_version)
signal_spec ─< lifecycle_event >   (to_state='live' ⇒ decided_by human: STRUCTURAL;
                                    transition graph: PROCESS, governed RD-012)

Identity: research_cycle, sweep, trial_ledger, signal_spec, snapshot, *_config, policy
Events:   research_cycle_event, trial_event, lifecycle_event, validation_result
State is DERIVED from the latest event by event_id, never stored mutably.
```

## 10. What this document does NOT settle

The grammar AST node types in `signal_spec.transform` (R2); exact metric names in `trial_event.metrics` / `criteria_metrics` (R1–R3); the values inside governed-parameter rows (per phase via DECISIONS); the `research_cycle.intent` controlled vocabulary (when the scheduler is built); the precise `content_hash` algorithm (RD-013); the permitted lifecycle transition graph edges (RD-012, governed there); the execution-environment pinning mechanism (RD-013); and the Execution layer's schema (separate system). Amendments are explicit and dated, each with a matching DECISIONS entry.

## 11. Change log

- **rev. 2 (2026-08-07)** — structural integrity fixes following full-schema review: deterministic event ordering by `event_id` (§3); added `research.sweep` registry and made `trial_ledger.sweep_id` a real FK (§7.1); `validation_result` uniqueness on (trial_id, gate, gate_config_version) with sequential order left to the engine (§7.5); lifecycle transition graph declared a governed process invariant, not CHECK constraints (§7.6, RD-012); removed redundant `spec_version` from the tuple (§8); softened the reproducibility claim to its honest conditional form and added the deferred environment-pinning requirement (§8, RD-013); `research_policy.cost_assumptions` replaced by a real `cost_model_version` FK (§4.1); added optional `research_cycle.intent` (§6.1); universe-determinism requirement stated (§8, RD-014); `run_key` terminology corrected to "serialized reproducibility contract" (§8). No new architecture; no new tables beyond `research.sweep`.
- **rev. 1 (2026-08-07)** — identity/event pattern applied to snapshot, cycle, trial; removed mutable status columns; tuple references snapshot_id.

---

*Ratified 2026-08-07 (rev. 2). R0 schema implementation (migrations) may now begin.*