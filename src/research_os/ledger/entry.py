"""The ledgered trial entry point (RD-003, RD-011, SCHEMA §7.3/§7.4).

This is the ONLY door to evaluation. To create a trial you must supply a run_key
that (a) validates against the registries and (b) is accompanied by a clean,
committed code state. On success it writes the trial_ledger row and its opening
'enumerated' trial_event atomically. There is no code path that records a trial
without passing through here.
"""
from __future__ import annotations
from pathlib import Path
import psycopg
from research_os.ledger.run_key import RunKey, validate
from research_os.ledger.git_state import require_clean_sha


class TrialRejected(Exception):
    """Raised when a trial cannot be admitted to the ledger."""


def open_trial(
    run_key: RunKey,
    cycle_id: int,
    conn: psycopg.Connection,
    *,
    sweep_id: int | None = None,
    by_whom: str = "human",
    enforce_clean_tree: bool = True,
    repo_root: Path | None = None,
) -> int:
    """Admit a trial to the ledger. Returns the new trial_id.

    Steps, all-or-nothing in one transaction:
      1. Enforce the clean-tree rule (RD-011): the run_key.code_sha must match the
         current committed HEAD, and the tree must be clean. Refuse otherwise.
      2. Validate every identifier in the run_key against the registries (RD-003).
      3. Confirm the referenced cycle exists.
      4. Insert the trial_ledger row and its 'enumerated' trial_event.

    Raises TrialRejected (leaving nothing written) if any check fails.
    enforce_clean_tree=False is for tests only; production always enforces.
    """
    # 1. Clean-tree / committed-sha rule (RD-011).
    if enforce_clean_tree:
        try:
            head = require_clean_sha(cwd=repo_root)
        except Exception as e:
            raise TrialRejected(f"code state not admissible (RD-011): {e}") from e
        if run_key.code_sha != head:
            raise TrialRejected(
                f"run_key.code_sha {run_key.code_sha!r} does not match committed "
                f"HEAD {head!r} (RD-011)"
            )

    # 2. Validate run_key identifiers (RD-003).
    try:
        validate(run_key, conn)
    except Exception as e:
        raise TrialRejected(f"run_key invalid (RD-003): {e}") from e

    # 3 + 4. Write trial + opening event atomically.
    with conn.cursor() as cur:
        cur.execute("select 1 from research.research_cycle where cycle_id = %s", (cycle_id,))
        if cur.fetchone() is None:
            raise TrialRejected(f"cycle_id {cycle_id} not in research_cycle")

        cur.execute(
            """insert into research.trial_ledger (run_key, spec_id, cycle_id, sweep_id)
               values (%s, %s, %s, %s) returning trial_id""",
            (run_key.to_json(), run_key.spec_id, cycle_id, sweep_id),
        )
        trial_id = cur.fetchone()[0]

        cur.execute(
            """insert into research.trial_event (trial_id, event_type, by_whom)
               values (%s, 'enumerated', %s)""",
            (trial_id, by_whom),
        )
    return trial_id