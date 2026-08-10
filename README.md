# Magnuson Research OS

A systematic alpha-search factory built as an external, read-only consumer of the
Magnuson Trading OS. It generates candidate signals, subjects them to an
adversarial validation gauntlet, combines survivors into a target portfolio, and
retires them as they decay — within laws the human governs.

The Trading OS makes it impossible to lie to yourself about **data**.
The Research OS makes it impossible to lie to yourself about **results**.

## Governing documents (read in this order)

- `docs/VISION.md` — the charter; what the system is for and the laws it obeys
- `docs/ARCHITECTURE.md` — structure, layers, the one-way dependency, snapshot intake
- `docs/ROADMAP.md` — R0→R4 sequence and gates
- `docs/DECISIONS.md` — dated, append-only decision log (RD-001 …)
- `docs/SCHEMA.md` — the research.* Postgres schema and reproducibility tuple

No implementation may violate the governing documents without an explicit, dated
amendment. Decisions first, implementation second.

## Layout

- `schema/postgres/` — ordered SQL migrations (NNN_name.sql)
- `src/research_os/` — the Python package (its git SHA is the code_sha in every reproducibility tuple)
- `tests/` — verification scripts

## Databases

- Trading OS: tradingos (separate system; read-only via snapshot/as_of intake)
- Research OS: researchos (this system; owns the research.* namespace)

There is no shared writable database and no runtime SQL access from the Research
OS into the Trading OS (RD-001, RD-002).
