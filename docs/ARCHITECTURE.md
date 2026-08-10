# ARCHITECTURE.md — Magnuson Research OS

*Status: ACCEPTED*
*Ratified: 2026-08-07*
*Governing document. Subordinate to VISION.md. No implementation may violate this without an explicit, dated amendment. Where this document and VISION.md appear to conflict, VISION.md wins and this document is amended.*

---

## 1. Purpose of this document

VISION.md states what the system is for and the laws it obeys. This document states the system's *structure*: its layers, the direction of every dependency, how it consumes the Trading OS, and where the boundaries sit. It does not specify the schema (SCHEMA.md), the governed parameters and their values (DECISIONS.md), or the delivery sequence (ROADMAP.md).

## 2. System context — three systems, one direction of flow

```
   ┌─────────────────────────────────────────────────────────────┐
   │  TRADING OS  (separate system, system of record for DATA)   │
   │  bitemporal PIT data · adjustment · as_of serving API        │
   └───────────────────────────▲─────────────────────────────────┘
                               │  read-only, once per month,
                               │  through the as_of contract ONLY
   ┌───────────────────────────┴─────────────────────────────────┐
   │  RESEARCH OS  (this system, system of record for RESEARCH)  │
   │  snapshots · registries · generation · evaluation ·          │
   │  gauntlet · lifecycle · meta-layer → target portfolio        │
   └───────────────────────────▲─────────────────────────────────┘
                               │  one artifact: a versioned
                               │  target portfolio (append-only)
   ┌───────────────────────────┴─────────────────────────────────┐
   │  EXECUTION LAYER  (separate, thin, future)                   │
   │  broker adapters · deterministic pre-trade rules · order log │
   └─────────────────────────────────────────────────────────────┘
```

All dependencies point in one direction. The Research OS depends on the Trading OS; nothing depends on the Research OS except the Execution layer, and only through a single versioned artifact. The Research OS never writes upstream and never learns that brokers exist downstream (VISION §4, §5).

## 3. Data-access spine — the monthly immutable snapshot

This is the load-bearing architectural decision. The Research OS performs **no point-in-time computation of its own.** The Trading OS owns PIT correctness; the Research OS consumes finished, point-in-time-correct data.

**Intake.** Once per research period (default: monthly), the Research OS pulls the full dataset it needs from the Trading OS **through the `as_of` contract** (the serving API and/or sanctioned DuckDB/Arrow bulk export), at a single fixed snapshot knowledge cutoff `as_of = snapshot_date`. Because the pull goes through the Trading OS's own read path, all knowledge-time filtering and corporate-action adjustment are performed *by the Trading OS*. The Research OS receives data that is already point-in-time-correct and, where applicable, already adjusted.

**One snapshot = one knowledge cutoff.** Every read composing a snapshot uses the same `as_of = snapshot_date`, including the full history of bars (so adjustment reflects only actions known by the snapshot date). A snapshot is a coherent "what was knowable as of `snapshot_date`" dataset — a point-in-time dataset by construction, not merely a recent one.

**Immutability and retention.** Each pull writes a **new, dated, immutable snapshot** (e.g. `snapshots/2026_09_01/`) in the Research OS's own storage. A snapshot is never overwritten and never deleted. This mirrors the Trading OS's "never delete" spine (VISION §3.1) applied to research intake, and it is what makes a trial reproducible after the next pull: a result computed against the September snapshot regenerates in December because that snapshot still exists, byte-for-byte.

**Runtime reads.** For the entire research period, all evaluation reads the **local snapshot** in-process (DuckDB/Polars over the Research OS's own Parquet). Research throughput never pays REST cost and never depends on the Trading OS being reachable. The Trading OS may be offline, refactored, or mid-ingest for the whole period without affecting research.

**Consequences, stated plainly.**
- The freshest data available to research is the last snapshot; intra-period data newer than the snapshot is not visible until the next pull. For EOD daily and event-anchored research (all of R0–R2) this is correct and sufficient.
- A more frequent snapshot cadence for intraday families is a **deferred R3 decision**, explicitly out of scope here. It changes cadence, not architecture.
- The snapshot cadence is a governed parameter (its value lives in DECISIONS.md), not a constant buried in code.

**The dependency this creates.** The only coupling between the two systems is the monthly read through the one sanctioned surface. There is **no shared code dependency, no synchronized replication, and no live runtime dependency.** The Research OS does not import Trading OS Python, does not maintain a continuously synced copy, and does not reimplement PIT logic — the three failure modes the snapshot design deliberately avoids.

## 4. Internal layers

The Research OS is layered bottom-to-top. Each layer consumes only the layers below it. Higher layers are built in later roadmap phases; the structure is fixed now so later phases extend it rather than reshape it.

```
   TARGET PORTFOLIO   one versioned artifact per rebalance (append-only)
        ▲
   META-LAYER         combination · allocation · decay monitor · retirement
        ▲
   LIFECYCLE          candidate→validating→paper→live→decaying→retired
        ▲
   VALIDATION GAUNTLET  sequential gates + adversarial self-test
        ▲
   EVALUATION ENGINE  walk-forward · cost-aware · reads snapshot via tuple only
        ▲
   GENERATION         declarative specs (hand-written now; grammar later;
        ▲             autonomous scheduler eventually) — provenance-tagged
   REGISTRIES         signal_spec · trial_ledger · validation_result ·
                      lifecycle_event   (append-only, deny_mutation)
        ▲
   SNAPSHOT STORE     immutable dated PIT datasets pulled from the Trading OS
   ───────────────────────────────────────────────────────────────────────
   AUDIT & AGENT LAYER (beside the loop, not in it): narratives, anomaly
   flags, research-state queries, MCP interface — reads only, never decides.

   The loop layers above (generation through meta-layer) execute within a
   discrete RESEARCH CYCLE — the operational unit of the system (RD-007).
```

**Registries** are the spine (SCHEMA.md defines them): the append-only record of every signal specification, every trial, every gate result, every lifecycle transition. Enforced by `deny_mutation` triggers mirroring the Trading OS.

**Generation** produces signal specifications as *data*, never scripts (VISION §3.2). In R1 specs are hand-written; in R2 a grammar enumerates them; eventually a scheduler generates them autonomously. Every spec is provenance-tagged (`created_by`) so origin is always auditable (VISION §8.1).

**The evaluation engine** has exactly one entry point: a reproducibility tuple (SCHEMA.md). There is no code path that evaluates an unlogged, un-pinned signal. It reads the snapshot store; it never reads the Trading OS directly at runtime.

**The validation gauntlet** is sequential gates, each decision a row in the registries, continuously re-proven against planted garbage (VISION §3.3). Gates are code, not meetings.

**Lifecycle and meta-layer** govern promotion, combination, decay, and retirement. The `→ live` transition is the permanent human boundary (VISION §5); demotion is automated.

**The audit & agent layer sits beside the loop, never inside it.** It observes and reports; it has no authority to advance a signal or commit capital. This placement is architectural, not policy — the decision loop has no LLM in it.

**The research cycle is the operational unit of the loop (RD-007).** The system
does not run as a single long-lived process. Work proceeds in discrete,
auditable research cycles: each cycle reads committed research state and a pinned
snapshot at its start, executes its steps (in mature form: allocate budget →
generate → evaluate → gauntlet → update population → monitor decay →
retire/demote), and commits durable new state at its end. Nothing that decides a
later cycle lives only in memory between cycles. "Continuous" operation (R4)
means cycles dispatched back-to-back, not one unbroken thread. Early phases run
trivial one- or two-step cycles; later phases add steps without changing the
shape. The cycle is the unit of auditability, reproducibility, crash recovery,
and scheduling, and is referenced by trials and lifecycle events from R0 onward.

## 5. Storage architecture

- **Research state → PostgreSQL, `research.*` schemas.** Registries, ledger, lifecycle, validation results, research policy. Append-only via triggers. Separate schemas from any Trading OS database; the Research OS owns its Postgres namespace (VISION §4).
- **Snapshots and trial artifacts → Parquet, content-addressable.** Immutable dated PIT snapshots (§3); per-trial returns/positions/diagnostics, content-hashed for the reproducibility canary. Local disk now; S3/R2 later without redesign, since both are just Parquet.
- **No shared database with the Trading OS.** The systems share no writable store. The only data crossing the boundary crosses through the monthly `as_of` read.

## 6. The reproducibility spine

Every research result is fully determined by a pinned tuple (SCHEMA.md gives its fields), one of which is `data_as_of` — the snapshot the result ran against. Because snapshots are immutable and retained (§3), `data_as_of` always points at a still-existing artifact, so any result regenerates bit-for-bit. The evaluation engine accepts only a tuple; a result that cannot be regenerated from its tuple is a P0 defect (VISION §6). This is the research analog of the Trading OS's bitemporal spine, and the snapshot design is what makes the `data_as_of` field meaningful rather than aspirational.

## 7. Technology posture

Python + Polars/DuckDB for evaluation; PostgreSQL for research state; Parquet for snapshots and artifacts; Dagster for orchestration (monthly pulls, sweeps, decay jobs, the reproducibility canary) when scheduling is needed; FastMCP for the audit/agent read interface when built. This deliberately reuses the Trading OS's operational patterns so one person can operate both systems. Specific versions, new dependencies, and any deviation are governed decisions (DECISIONS.md), not made ad hoc — the anti-drift discipline from VISION §9. No new infrastructure classes (no Kafka/Kubernetes/Redis-cluster) are introduced without a dated decision justifying them against this posture.

## 8. What this document does NOT settle

The concrete schema of the registries and the reproducibility tuple's exact fields (SCHEMA.md); the values of governed parameters — snapshot cadence, gate thresholds, cost assumptions, research budget, permitted model families (DECISIONS.md); the evaluation methodology's specifics — walk-forward scheme, purge/embargo lengths (SCHEMA.md / DECISIONS.md); and the delivery sequence (ROADMAP.md). Where those documents need a structure this document did not anticipate, this document is amended explicitly and with a date.

---

*Ratified 2026-08-07. Subsequent governing documents may now proceed, one at a time, each ratified before the next.*