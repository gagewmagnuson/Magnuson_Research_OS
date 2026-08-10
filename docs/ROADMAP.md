# ROADMAP.md — Magnuson Research OS

*Status: ACCEPTED*
*Ratified: 2026-08-07*
*Governing document. Subordinate to VISION.md and ARCHITECTURE.md. No implementation may violate this without an explicit, dated amendment.*

---

## 1. Purpose of this document

This document fixes the **delivery sequence** and the **gate** that ends each phase. It sequences the restraint that VISION §7 names: trust is proven before capability is granted, never the reverse. Gates are pass/fail conditions on the *system's trustworthiness*, not dates and not alpha targets. A phase is complete when its gate is demonstrably met; the calendar hints are expectations, not commitments.

This document does not define the schema (SCHEMA.md), the governed parameter values (DECISIONS.md), or the structure (ARCHITECTURE.md).

## 2. The one hard external rule

**The Research OS must run its first honest end-to-end evaluation (the R1 gate) within 8 weeks of starting, or the scope is wrong.** Infrastructure-as-procrastination is the primary meta-risk of this project, and it is more seductive here than in the Trading OS because this system is more interesting to build. Every phase below is subordinate to this rule: if a phase threatens the 8-week R1 gate, the phase is over-scoped and must be cut, not extended.

## 3. Governing sequencing principles

- **Prove before you generate.** No mass generation (R2) before the machine can honestly evaluate a single real strategy (R1). No autonomy (R3+) before the gauntlet demonstrably kills garbage (R2).
- **The ledger precedes the experiments.** A trial ledger retrofitted after unlogged experiments is permanently dishonest. R0 builds the ledger first, before any backtest exists.
- **Gates are trustworthiness, not profit.** Every gate asks "can I trust what this produced?" Expected carnage in results is a passing gate if the results are reproducible and honestly recorded.
- **Build the structure once; extend it thereafter.** Later phases add layers onto the ARCHITECTURE §4 stack; they do not reshape it.

## 4. Execution environment

Local execution (the developer's machine) is the **default through R2**, unless measured workload requirements demonstrate a compelling reason to migrate earlier. The trigger is empirical, not phase-bound: the first real compute-cost measurement (expected when the R2 grammar begins enumerating candidates at scale, but possible earlier) drives the local-vs-cloud decision, recorded as a dated entry in DECISIONS.md. Portability is preserved architecturally (ARCHITECTURE §5: Parquet + Postgres primitives) so this decision stays cheap to make whenever it is triggered.

Continuous unattended operation (R4) is expected to force a non-sleeping execution environment regardless of compute cost — a living system cannot ultimately run on a machine that sleeps. That is an R4 forcing function, noted here and decided then.

---

## R0 — Skeleton of honesty
*Expectation: weeks 1–3. No backtests. No alpha.*

Build the foundation that makes every later result trustworthy, before any result exists.

- Governing documents ratified (VISION, ARCHITECTURE, ROADMAP, DECISIONS, SCHEMA).
- `research.*` Postgres schemas: `signal_spec`, `trial_ledger`, `validation_result`, `lifecycle_event`, with append-only `deny_mutation` triggers mirroring the Trading OS.
- The reproducibility tuple enforced as the evaluation engine's **only** entry point — no code path evaluates an unlogged, un-pinned signal.
- Provenance (`created_by`) first-class on specs and trials (VISION §8.1).
- The monthly snapshot intake mechanism (ARCHITECTURE §3): pull one immutable dated PIT snapshot from the Trading OS through the `as_of` contract; the Research OS performs no PIT computation.
- The reproducibility canary: a job that re-runs a completed trial and diffs its artifacts.

**Gate.** A trivial signal specification runs end-to-end; its artifacts regenerate bit-for-bit from its reproducibility tuple; an attempt to evaluate outside the ledger fails structurally; a snapshot exists, is immutable, and is the sole data source read. Whatever the trivial result *is* does not matter — only that the machinery is honest.

---

## R1 — First honest evaluations
*Expectation: weeks 4–8. This is the 8-week gate of §2.*

Prove the machine can honestly evaluate real, believed-in strategies.

- Daily cross-sectional evaluation engine: walk-forward with purge/embargo around split boundaries; at least three cost scenarios (optimistic/base/stressed); IC and quantile-spread metrics.
- Re-express the legacy models (the strategies the developer would otherwise be tempted to trust) as declarative signal specs and evaluate them on snapshot PIT data.
- Every evaluation flows through the reproducibility tuple and lands in the trial ledger.

**Gate.** The legacy models have ledger entries with reproducible dossiers — whatever the results say. Expect carnage; the carnage is the deliverable. The gate is that the numbers are honest and regenerable, not that they are good.

---

## R2 — The factory switches on
*Expectation: months 3–5.*

Prove the machine can generate strategies at scale and that the gauntlet kills what it must.

- Signal grammar and sweep registration: every sweep records its full enumeration (including candidates never run) before evaluation, so the true trial count is always the denominator of significance.
- Gates 1–3 automated (statistical honesty / robustness / orthogonality).
- Adversarial self-test batteries green: planted noise, lookahead, overfit, and factor-clone candidates die at their expected rates.
- First full sweep on a chosen signal family.
- **First real compute-cost measurement** taken here; feeds the execution-environment decision (§4).

**Gate.** The gauntlet demonstrably kills noise, lookahead, overfit, and factor clones at expected rates; the first sweep completes with a defensible family-wise error rate. If garbage survives at abnormal rates, the immune system is malfunctioning and R2 is not complete.

---

## R3 — Survivors under fire, and intelligent search
*Expectation: months 5–8.*

Prove the machine can carry survivors toward production and begin to explore the research space intelligently rather than by blind enumeration.

- Gate 4 (economic sanity — the human mechanism-review choke point) process in place.
- Gate 5 (live-shadow conformance) monitoring; paper harness running on the production path.
- Meta-layer Stage 1 (risk-parity / inverse-vol combination); decay monitoring live.
- The research scheduler begins allocating search budget toward promising or sparse regions of the space, informed by the trial ledger (VISION §7 R3, §8.2) — bounded by the human-governed research policy.
- Intraday snapshot cadence reconsidered if an intraday family is in scope (deferred from ARCHITECTURE §3).

**Gate.** At least one signal reaches `paper` with a full dossier; live-shadow conformance is measured over a defined period; the scheduler demonstrably concentrates search where evidence warrants rather than enumerating blindly.

---

## R4 — Living population, minimal intervention
*Expectation: months 8–12+.*

Operate a continuously maintained population of validated signals with autonomy of research and a permanent human hand at capital.

- First `live` promotions — each a deliberate human act with recorded rationale (VISION §5).
- Execution layer (separate, thin) consumes the target portfolio: deterministic pre-trade rules and kill-switch; nightly reconciliation.
- Continuous autonomous operation: hypothesis generation, evaluation, adversarial testing, combination, decay monitoring, and automated retirement — running unattended within the research policy.
- Audit and agent (MCP) layer beside the loop.
- Non-sleeping execution environment in place (§4 forcing function).

**Gate.** Live behavior conforms to dossiers over a sustained period; the decay machinery has fired at least once in anger and reallocated correctly; the system runs a research cycle end-to-end without human intervention *except* at the permanent §5 capital-promotion boundary and at the kill-switch.

---

## 5. What this document does NOT settle

The schema of the registries and the tuple (SCHEMA.md); the values of gate thresholds, cost assumptions, purge/embargo lengths, snapshot cadence, research budget, and permitted model families (DECISIONS.md); and the internal structure (ARCHITECTURE.md). Where a phase reveals a needed structure or parameter this document did not anticipate, this document is amended explicitly and with a date.

---

*Ratified 2026-08-07. Subsequent governing documents may now proceed, one at a time, each ratified before the next.*