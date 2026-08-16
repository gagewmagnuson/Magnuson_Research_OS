"""Governance-fact loaders for the snapshot pull.

Reads immutable append-only governance facts (e.g. known no-price-data
securities) from the DB and hands them to the pure completeness checks. Keeping
this in orchestration — not inside completeness — preserves the boundary: the
checks are pure functions of (PulledData, request, governance inputs)."""
from __future__ import annotations

from research_os.db import connect


def load_known_no_data(universe_code: str, conn=None) -> frozenset[int]:
    """Security_ids explicitly recorded as having no available price data for the
    given universe (research.known_no_data_security). A member with zero bars that
    is in this set is an accepted governed exception; otherwise it is a hard gap."""
    own = conn is None
    if own:
        conn = connect()
    try:
        rows = conn.execute(
            "select security_id from research.known_no_data_security "
            "where universe_code = %s",
            [universe_code],
        ).fetchall()
        return frozenset(r[0] for r in rows)
    finally:
        if own:
            conn.close()