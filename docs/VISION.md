# VISION.md — Magnuson Research OS

*Status: ACCEPTED*
*Ratified: 2026-08-07*
*Governing document. No implementation may violate this without an explicit, dated amendment.*

---

## 1. What this system is

The Research OS is a **systematic alpha-search factory** built as an external,
read-only consumer of the Magnuson Trading OS. In its mature form it is a
**living research system**: it observes the data and features available to it,
generates its own hypotheses, instantiates candidate strategies across many model
families, evaluates them, attacks them adversarially, combines the survivors into
a target portfolio, monitors them in production, and retires them without
sentiment as their evidence of usefulness decays — all within a set of laws the
human defines.

It is not a model. It is the **laboratory in which models are tested and
maintained** — a machine whose output is not "a signal" but a *continuously
maintained population of validated signals*, together with an append-only record
of everything ever tried.

The human is the **governor of the laboratory, not its researcher.** The human
sets the laws — what data is admissible, what model families are permitted, what
risk and cost assumptions hold, how much research budget exists, and which
signals may advance toward real capital. Within those laws, the system does the
research itself.

## 2. What this system is for

The Trading OS makes it impossible to lie to yourself about **data**. The
Research OS makes it impossible to lie to yourself about **results**.

Its purpose is to maximize the probability that what reaches live capital is
real — that when the system says "this works," the statement is trustworthy, and
when a signal dies, the system survives it. It cannot guarantee that alpha
exists in the data. It guarantees you will not be fooled about whether it does.

This purpose is not abstract. The point-in-time stress test that preceded this
system (2004–2012, 12-1 momentum, S&P 500) showed a naive research workflow
reporting +13.8% CAGR on a strategy that a point-in-time-correct workflow showed
*losing* money (−3.4% CAGR) — a naive terminal-wealth overstatement of roughly
4.3×, with the very sign of the result inverted. That is the failure mode this
system exists to prevent, applied not just to data but to every downstream
research claim, including the ones the system will eventually generate about
itself.

## 3. Principles that override everything else

These four principles take precedence over convenience, speed, and any
individual result. Code and schema enforce them; memory and intention do not.

1. **The process is trusted; the researcher is not.**
   Every trial is logged before it runs. Every result is reproducible from a
   pinned specification. No number exists outside the ledger. This holds
   identically whether the "researcher" is a human, a grammar sweep, or an
   autonomous research scheduler — discipline is enforced structurally, the same
   philosophy as the Trading OS's `deny_mutation()` triggers applied to research
   claims instead of data rows.

2. **Signals are data, not code.**
   A signal is a declarative, versioned specification executed by a generic
   engine — never a bespoke script. This is what makes mass generation, honest
   trial counting, bit-for-bit reproducibility, and eventual autonomous
   hypothesis generation possible. A machine can manufacture a specification; it
   cannot be trusted to hand-write a trustworthy evaluation.

3. **The gauntlet is more paranoid than the generator is creative.**
   Mass search is mass hypothesis testing; at scale, many candidates will look
   brilliant by chance. The validation layer exists to kill them, and it is
   itself tested adversarially — with deliberately planted garbage (noise,
   lookahead, factor clones, overfit constructions) — the same way the Trading
   OS tests for lookahead bias. The generator may be as creative as it likes
   precisely because it does not get to declare anything successful; the gauntlet
   decides, and the gauntlet is continuously re-proven against known garbage. If
   garbage begins surviving at abnormal rates, the system must treat its own
   immune system as malfunctioning.

4. **Everything decays.**
   A promoted signal is not an asset; it is a position with a monitored
   half-life. Demotion and retirement are automated, dated, append-only events.

## 4. The boundary with the Trading OS

The Research OS is a **separate system**: its own repository, its own governing
documents, its own Postgres schemas (`research.*`). It touches the Trading OS
through exactly one surface — the read-only, point-in-time `as_of` contract
(the serving API, and sanctioned DuckDB/Arrow bulk reads over the same PIT
semantics).

- The Research OS **never writes to the Trading OS.**
- If research reveals that the Trading OS must change (as the PIT stress test
  revealed its survivor-only universe limitation), that is a deliberate,
  human-approved decision recorded in both systems — never a default, never a
  silent workaround.

## 5. The boundary with capital — the one permanent human hand

The Research OS emits exactly one kind of output to the outside world: a
versioned **target portfolio**. It does not route orders, hold broker
connections, or know that brokers exist. A separate, thin Execution layer
consumes the target portfolio and is the only system that touches markets.

Autonomy of *research* is the goal and may grow without limit: the system may
generate hypotheses, schedule experiments, run evaluations and adversarial
tests, compare candidates, combine survivors, monitor live-shadow performance,
detect decay, retire signals, and *propose* promotions — all without human
intervention.

Autonomy of *capital commitment* is permanently withheld. The transition that
promotes a signal to `live` — the point at which a signal is first permitted to
contribute real weight to the emitted target portfolio — **requires a deliberate
human act with a recorded rationale, in every version of this system, forever.**
The machine assembles the evidence dossier; a human signs the transition. This
boundary is not a temporary safeguard to be relaxed as trust grows; it is the
structural guarantee that the system can never both *discover* a signal and
*commit capital to it* in one unbroken automated loop — which is precisely the
opaque feedback loop the entire architecture exists to prevent.

Demotion, by contrast, is automated and requires no human hand. Sentiment is
structurally excluded from the retirement path: **the human hand is required to
advance a signal toward capital, never to kill one.**

## 6. The success test

The system is succeeding if and only if this statement holds:

> **Would I trust this number if someone else's factory produced it?**

Every result carries the evidence to answer yes: a pinned reproducibility tuple,
a logged trial count that is the true denominator of its significance, a
cost-aware walk-forward evaluation, and a gauntlet record. A number that cannot
meet this test is not a result; it is a defect.

## 7. Maturity progression — the destination and the discipline of reaching it

This charter names the destination; the ROADMAP sequences the restraint. The end
state is a living system, but it is reached by proving trust before granting
capability, never the reverse. The progression is deliberately staged:

- **R0 — Can I trust the machine?** The skeleton of honesty: reproducibility
  enforced as the sole entry point to evaluation, append-only registries, the
  gauntlet's self-tests. No alpha.
- **R1 — Can the machine honestly evaluate real strategies?** Real, believed-in
  strategies (the legacy models) put through the engine, whatever the results.
- **R2 — Can the machine generate strategies at scale?** Systematic grammar
  generation; the gauntlet automated and adversarially proven.
- **R3 — Can the machine explore the research space intelligently?** The system
  learns where the search space is sparse or promising and allocates its own
  research budget accordingly, rather than enumerating blindly.
- **R4 — Can the machine operate a living population with minimal intervention?**
  Continuous autonomous research, combination, decay monitoring, and retirement —
  bounded always by the human-governed research policy and the permanent
  capital-promotion boundary of §5.

Autonomy increases monotonically across this progression; the §5 boundary does
not move. Each stage is entered only when the prior stage's trustworthiness is
demonstrated — because a living system built on an unproven foundation is not an
organism, it is a way to be fooled at scale.

## 8. Foundations the skeleton must carry (even though R0 builds no autonomy)

R0 builds none of the autonomy above, but its foundations must be able to carry
it, so that the skeleton of honesty is also the skeleton the living system grows
on. Three commitments follow now, not later:

1. **Provenance is first-class.** Every signal specification and every trial
   records what originated it — `human`, `grammar_sweep:<id>`, or eventually
   `research_scheduler:<id>` — so that when the system begins generating its own
   hypotheses, the ledger already knows how to record who or what ran each
   experiment, and the human governor can always audit the origin of any claim.

2. **The trial ledger is a substrate, not just an audit log.** It records every
   candidate ever *enumerated* — including those enumerated but never run — so
   that the true trial count is always available for statistical correction, and
   so that a future research scheduler can reason over the map of what has and
   has not been explored. The ledger is the memory the living system will
   eventually search.

3. **The research policy is an explicit object.** What data is admissible, what
   model families are permitted, what cost and risk assumptions hold, and how
   much research budget exists are the human governor's retained authority. They
   are named as first-class governed parameters from the beginning — never
   scattered through code as magic constants — so the laws of the laboratory
   always have a single, dated, amendable home.

## 9. What this document does NOT cover

To prevent scope drift, this VISION deliberately does not specify the signal
grammar, the gate thresholds, the evaluation methodology, the technology choices,
or the schema. Those live in ARCHITECTURE, DECISIONS, and SCHEMA and must be
justifiable against the principles above. Where a future design decision appears
to conflict with this document, the conflict is resolved by amending this
document explicitly and with a date — not by quietly overriding it.

---

*Ratified 2026-08-07. Implementation of subsequent governing documents may now
proceed, one at a time, each ratified before the next.*