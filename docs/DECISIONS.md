# DECISIONS.md — Magnuson Research OS

*Status: ACCEPTED (living log)*
*Last updated: 2026-08-07*
*Governing document. Subordinate to VISION.md and ARCHITECTURE.md. Append-only: decisions are never edited or deleted, only superseded by a later dated entry that references them. Changing a governed parameter without a dated entry here is the research equivalent of mutating a fact row.*

---

## How to read this log

Each entry is dated, states the decision, the reasoning, and the alternative rejected. An entry stands until a later entry explicitly supersedes it (and says so). Entries are the single source of truth for governed parameters and foundational choices; code and schema must conform to them, not the reverse.

---

## RD-001 — The Research OS is a separate system consuming the Trading OS through one read-only surface
*2026-08-07*

**Decision.** The Research OS is a distinct system with its own repository (`~/Magnuson_Research_OS`), its own governing documents, and its own Postgres schemas (`research.*`). It reads the Trading OS only through the point-in-time `as_of` contract, never writes to it, and shares no writable store with it.

**Reasoning.** Preserves the Trading OS's neutrality as system-of-record for data; lets the two systems version and fail independently; ensures a research-code bug can never corrupt the data moat. (VISION §4, ARCHITECTURE §2.)

**Rejected.** A single combined system, or a Research OS that imports Trading OS internals — both couple the systems and violate the one-surface boundary.

---

## RD-002 — Data intake is a monthly immutable point-in-time snapshot; the Research OS performs no PIT computation
*2026-08-07*

**Decision.** Once per research period (default cadence: monthly — see RD-008), the Research OS pulls the full dataset it needs from the Trading OS through the `as_of` contract at a single fixed `as_of = snapshot_date`. The Trading OS performs all knowledge-time filtering and adjustment; the Research OS receives finished, point-in-time-correct data and writes it as a new, dated, immutable snapshot. All research for the period reads that local snapshot in-process. Snapshots are never overwritten and never deleted.

**Reasoning.** Gives in-process read speed without live coupling or code coupling; the Trading OS owns PIT correctness so the Research OS never reimplements or drifts from it; a fixed-`as_of` snapshot is a point-in-time dataset by construction, making `data_as_of` in the reproducibility tuple point at a real, retained artifact so any past result regenerates. (ARCHITECTURE §3, §6.)

**Rejected.** (a) Per-read REST calls to the API — too slow for universe-wide walk-forward. (b) A synchronized/appending copy of the Trading OS lake — reintroduces the bitemporal-consistency problem the Trading OS solved once, invisibly corrupting research if replication drifts. (c) Reimplementing PIT adjustment in the Research OS — duplicates correctness-critical logic and risks silent divergence.

---

## RD-003 — Reproducibility is enforced structurally: the tuple is the evaluation engine's only entry point
*2026-08-07*

**Decision.** Every research result is fully determined by a pinned reproducibility tuple. The evaluation engine accepts only a tuple; there is no code path that evaluates an unlogged, un-pinned signal. A result that cannot be regenerated bit-for-bit from its tuple is a P0 defect.

**Reasoning.** This is the research analog of the Trading OS's bitemporal spine — the single discipline from which every other guarantee follows. Discipline enforced by code and schema, not memory. (VISION §3.1, §6; ARCHITECTURE §6.)

**Rejected.** Convention-based reproducibility (researchers expected to log their own runs) — the exact failure mode that silently corrupts institutional research.

---

## RD-004 — Registries are append-only, enforced by deny_mutation triggers
*2026-08-07*

**Decision.** The four registries (`signal_spec`, `trial_ledger`, `validation_result`, `lifecycle_event`) are append-only. Corrections and changes are new rows, never edits or deletes, enforced by a Postgres `deny_mutation` trigger pattern mirroring the Trading OS. Retired signals, dead trials, and failed candidates are retained forever — negative knowledge is a compounding asset.

**Reasoning.** The count of everything ever tried is the denominator of every significance calculation; an unlogged dead end silently corrupts all subsequent statistics. Append-only enforcement makes an unlogged or rewritten trial structurally impossible, not merely discouraged. (VISION §3.1, §3.3.)

**Rejected.** Mutable tables with application-level discipline — unenforceable and self-deceiving at scale.

---

## RD-005 — Provenance is first-class: every spec and trial records what originated it
*2026-08-07*

**Decision.** Every signal specification and every trial records a `created_by` provenance value distinguishing `human`, `grammar_sweep:<id>`, and (eventually) `research_scheduler:<id>` / `agent:<id>`.

**Reasoning.** So that when the system begins generating its own hypotheses, the ledger already knows how to record who or what ran each experiment, and the human governor can always audit the origin of any claim. The autonomy-carrying foundation must exist from R0 even though R0 builds no autonomy. (VISION §8.1.)

**Rejected.** Adding provenance later when autonomy arrives — a retrofit onto an already-populated ledger, permanently ambiguous for early trials.

---

## RD-006 — Autonomy of research grows without limit; autonomy of capital commitment is permanently withheld
*2026-08-07*

**Decision.** The system may autonomously generate hypotheses, schedule experiments, evaluate, run adversarial tests, combine survivors, monitor decay, retire signals, and *propose* promotions — without human intervention. The transition that promotes a signal to `live` (the point at which it first contributes real weight to the emitted target portfolio) requires a deliberate human act with a recorded rationale, in every version of the system, forever. Demotion and retirement are automated; the human hand is required to advance a signal, never to kill one.

**Reasoning.** A system that both discovers a signal and commits capital to it in one unbroken automated loop is precisely the opaque feedback loop the architecture exists to prevent. This boundary is structural and permanent, not a temporary safeguard relaxed as trust grows. (VISION §5.)

**Rejected.** Full sovereignty (AI discovers → AI judges → AI allocates) — rebuilds the black box; removes the one place a human can catch a corrupted gauntlet before it costs real money.

---

## RD-007 — Research proceeds in discrete, auditable, committed cycles — never a single long-running process
*2026-08-07*

**Decision.** The research loop is structured as discrete **research cycles**, not an infinite in-memory process (`while True: research()`). Each cycle reads committed research state and a pinned snapshot at its start, performs its steps (in mature form: allocate budget → generate/enumerate → evaluate → gauntlet → update population → monitor decay → retire/demote → commit new state), and commits durable new state at its end. Nothing that decides a later cycle lives only in memory between cycles. "Continuous" operation (R4) means cycles dispatched back-to-back, not one unbroken thread. The research cycle is a first-class concept referenced by trials and lifecycle events from R0 onward, even though early cycles have only one or two steps.

**Reasoning.** The cycle is the unit of auditability (each cycle is a dated, inspectable transaction), reproducibility (a cycle reads committed state and commits new state, so it is re-runnable and canary-checkable), crash recovery (resume from last committed state, not a corrupted in-memory blob), and scheduling (a cycle is a job, which maps cleanly onto Dagster/cron/cloud workers — a long-running daemon does not). Naming the cycle now means every phase is the same shape with more steps, honoring "build the structure once, extend it thereafter." An in-memory infinite loop is fundamentally at odds with "no number exists outside the ledger" (VISION §3.1). (Amends ARCHITECTURE §4; realized in SCHEMA.)

**Rejected.** A single continuous process with in-memory research state — unauditable, unreproducible, crash-fragile, and hard to deploy to the cloud.

---

## RD-008 — Snapshot cadence is a governed parameter, defaulting to monthly
*2026-08-07*

**Decision.** The data-snapshot cadence (RD-002) is a governed parameter, not a hard-coded constant. Its default value is **monthly**. Changing it (e.g. to fortnightly, or to a more frequent cadence for intraday families at R3) is a dated amendment to this entry, not a code or architecture change.

**Reasoning.** Keeps cadence flexible without reopening the architecture; a more frequent cadence for intraday families is a foreseeable R3 need (ARCHITECTURE §3 defers it explicitly). Governed-parameter-not-structure matches how research budget and gate thresholds are treated.

**Rejected.** Hard-coding "monthly" into the architecture — would require an architecture amendment to change cadence.

---

## RD-009 — Execution environment is local by default through R2; migration is measurement-triggered
*2026-08-07*

**Decision.** Local execution (the developer's machine) is the default through R2, **unless measured workload requirements demonstrate a compelling reason to migrate earlier.** The trigger is empirical, not phase-bound: the first real compute-cost measurement (expected when the R2 grammar begins enumerating at scale, but possible earlier) drives the local-vs-cloud decision, to be recorded as a later dated entry here. Continuous unattended operation (R4) is expected to force a non-sleeping execution environment regardless of compute cost.

**Reasoning.** No real compute-cost data exists yet; deciding cloud now would be premature optimization and the "infrastructure-as-procrastination" meta-risk in its purest form. Portability is preserved architecturally (ARCHITECTURE §5: Parquet + Postgres primitives) so the decision stays cheap whenever triggered. A living system (R4) cannot ultimately run on a machine that sleeps. (ROADMAP §4.)

**Rejected.** (a) Committing to cloud now — premature, based on no measurement, and a procrastination vector. (b) Declaring R0–R2 rigidly local — removes the ability to migrate earlier if a measured workload justifies it.

---

## RD-010 — The research policy is an explicit, governed object
*2026-08-07*

**Decision.** The human governor's retained authority — what data is admissible, what model families are permitted, what cost and risk assumptions hold, and how much research budget exists — is a first-class, governed object, named and dated here and in schema, never scattered through code as magic constants. Specific values are set in later dated entries as the relevant phases arrive.

**Reasoning.** These are the laws of the laboratory (VISION §8.3); they must have a single, dated, amendable home so the human governor's authority is always explicit and auditable. Placeholder now; populated per-phase (permitted model families at R2, cost assumptions at R1, research budget at R3).

**Rejected.** Encoding policy as constants in evaluation/generation code — invisible, ungoverned, and prone to silent drift.

---

## RD-011 — No ledgered research trial may be created from an uncommitted code state
*2026-08-07*

**Decision.** The Research OS as a whole does *not* refuse to run when the git working tree is dirty. The restriction is narrower and lives on the **ledgered evaluation entry point** only: the engine refuses to create a trial (write to `trial_ledger` / `trial_event`) unless the Research OS working tree is clean, so that every trial's `run_key.code_sha` is always a real, committed sha. Exploratory analysis, notebooks, and development run freely against a dirty tree; they simply cannot produce a ledgered result.

**Reasoning.** Reproducibility is pinned to `code_sha` (SCHEMA §8). A trial run from uncommitted code has an ambiguous or unrecoverable code state, so it cannot satisfy "regenerable bit-for-bit from its tuple" (RD-003) and would be a P0 defect by construction. Placing the check on the ledgered entry point — the sole door to evaluation (RD-003) — enforces the guarantee exactly where it matters without obstructing development. This mirrors the Trading OS discipline of pinning the code that produced any fact.

**Rejected.** (a) Refusing all execution on a dirty tree — too broad; blocks legitimate exploration and development. (b) Merely warning and recording the sha anyway — leaves ambiguous-provenance rows in the ledger, defeating the reproducibility guarantee the ledger exists to provide.

## RD-012 — The signal lifecycle transition graph is governed process logic, not schema constraints
*2026-08-07*

**Decision.** The permitted signal lifecycle transitions are defined here and enforced by the lifecycle manager (engine), not by database CHECK constraints. The one exception is the live-promotion-is-human rule (RD-006), which is genuinely structural and remains a database constraint. Permitted transitions:

- candidate → validating
- validating → paper
- validating → candidate (sent back)
- paper → live        (human-signed, RD-006)
- paper → candidate   (sent back)
- paper → decaying
- live → decaying
- decaying → live     (recovery; requires recorded rationale)
- decaying → retired

Any transition not listed is illegal. `retired` is terminal. Changes to this graph are dated amendments to this entry.

**Reasoning.** Encoding the full state machine as CHECK constraints would make the schema rigid and split the lifecycle logic between database and engine. Keeping the graph in one governed place (here) with engine enforcement follows the structural-vs-process-invariant distinction (SCHEMA §1): the database makes impossible only what must be *impossible* (non-human live promotion); the engine enforces what must follow an *order* (the transition graph). The autonomous lifecycle manager will operate this graph without human intervention except at the live boundary, so it must be explicit and governed.

**Rejected.** (a) Encoding every edge as a database constraint — rigid, and duplicates lifecycle logic across two layers. (b) Leaving the graph undefined and implicit in code — ungoverned, drift-prone, and unauditable.

---

## RD-013 — Reproducibility is conditional on a pinned execution environment; environment pinning is a deferred requirement
*2026-08-07*

**Decision.** The "artifacts regenerate bit-for-bit from the reproducibility tuple" guarantee (RD-003) is conditional on a fixed computational environment. At R0–R2, where evaluation is deterministic vectorized computation (Polars/DuckDB) over fixed Parquet, `code_sha` plus the deterministic engine is sufficient and the guarantee holds in practice. **Before any nondeterministic model family (ML/RL/GPU-backed) is introduced, the reproducibility contract must additionally pin the execution environment** (container image and/or dependency lockfile) sufficiently to reproduce artifacts deterministically. Separately, the precise algorithm defining `research.snapshot.content_hash` (e.g. a canonical manifest of per-file hashes) must be governed and fixed before it is relied upon as an integrity guarantee across environments.

**Reasoning.** `code_sha` pins the source but not the numerical environment (BLAS implementation, CPU architecture, library versions), which can produce small numerical differences for some model families. Claiming unconditional bit-for-bit reproducibility would promise more than the tuple guarantees. Deferring the mechanism is correct: environment pinning has no payoff until nondeterministic families exist (R3+), and building it at R0 would be over-engineering against the ROADMAP §2 anti-procrastination rule. The requirement is recorded now so it is honored before it is needed, not discovered after.

**Rejected.** (a) Claiming unconditional bit-for-bit reproducibility from `code_sha` alone — over-promises. (b) Building full environment pinning at R0 — premature; no deterministic-family payoff yet.

---

## RD-014 — Universe specifications must resolve deterministically from the pinned snapshot's point-in-time semantics
*2026-08-07*

**Decision.** A `universe_spec` (in a signal spec and in the reproducibility tuple) must resolve to a concrete eligible universe **deterministically from the pinned snapshot's `as_of` semantics** — the membership as knowable at the relevant historical knowledge cutoff, according to the specified rule — never from today's membership. "Trade the S&P 500" means "S&P 500 membership as knowable at the historical point being evaluated," resolved through the snapshot, not a present-day constituent list. The R1 evaluation engine enforces this; a universe that resolves to present-day membership is a lookahead defect.

**Reasoning.** This is the exact point-in-time lesson of the pre-Research-OS stress test (2004–2012 momentum), where a today's-constituents universe inverted the sign of the result. A research system whose purpose is preventing self-deception cannot let a universe definition silently import survivorship or hindsight membership. Because universe membership is pulled into the immutable snapshot at a fixed `as_of` (RD-002), deterministic historical resolution is available; the requirement is that specs and the engine actually use it.

**Rejected.** Allowing `universe_spec` to name a universe without binding it to the snapshot's PIT semantics — reintroduces exactly the survivorship/hindsight bias the whole system exists to prevent.

*This log is append-only. New decisions are added as RD-011 onward; superseding entries reference the entry they replace and state why.*