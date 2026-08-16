"""Canonical snapshot manifest — the self-describing provenance record.

Goes into research.snapshot.manifest (jsonb) AND into the content_hash (RD-015),
so the snapshot's declared semantics are hash-covered. Records scope (as_of,
universe, range, feature versions, macro series), per-domain row counts, the
accepted completeness warnings (a snapshot only registers with no BLOCKING
violations; warnings are recorded as provenance), the producer DQ signal, and
pull metadata.

Deterministic: same code + same pulled data -> same manifest -> same hash.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from research_os.snapshot.model import SnapshotRequest, PulledData
from research_os.snapshot.violation import Violation


def _violation_dict(v: Violation) -> dict[str, Any]:
    return {
        "tier": v.tier.value, "severity": v.severity.value, "issue": v.issue,
        "message": v.message, "domain": v.domain,
        "security_id": v.security_id, "symbol": v.symbol,
        "expected": v.expected, "observed": v.observed,
    }


def build_manifest(
    request: SnapshotRequest,
    data: PulledData,
    trading_os_as_of: str,
    warnings: list[Violation],
    code_sha: str,
    producer_dq: dict[str, Any] | None = None,
    pulled_at: datetime | None = None,
) -> dict[str, Any]:
    """Assemble the canonical manifest. `warnings` are the non-blocking violations
    accepted at registration (blocking ones abort the pull before this is built)."""
    pulled_at = pulled_at or datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "scope": {
            "trading_os_as_of": trading_os_as_of,
            "snapshot_date": request.as_of.isoformat(),
            "universe_code": request.universe_code,
            "feature_versions": request.feature_versions,
            "macro_series": sorted(request.macro_series),
            "requested_symbols": (sorted(request.requested_symbols)
                                  if request.requested_symbols else None),
        },
        "row_counts": {
            "bars_securities": len(data.bars),
            "gold_securities": len(data.gold),
            "universe_members": len(data.members),
            "macro_series": len(data.macro),
            "bars_sessions_total": sum(len(b.session_dates) for b in data.bars),
            "gold_sessions_total": sum(len(g.session_dates) for g in data.gold),
        },
        # Governed exceptions (e.g. member_no_data_governed) are semantically
        # distinct from empirical warnings: they are known, investigated, human-
        # governed data-availability facts, not "this looks unusual" flags. They
        # get their own manifest field so an auditor can tell "known and accepted"
        # from "flagged as odd" at a glance.
        "governed_exceptions": [_violation_dict(w) for w in warnings
                                if w.issue == "member_no_data_governed"],
        "accepted_warnings": [_violation_dict(w) for w in warnings
                              if w.issue != "member_no_data_governed"],
        "producer_dq": producer_dq,
        "pull": {
            "pulled_at": pulled_at.isoformat(),
            "research_os_code_sha": code_sha,
        },
    }


def canonical_manifest_for_hash(manifest: dict[str, Any]) -> dict[str, Any]:
    """The manifest form fed to content_hash (RD-015): identical to the stored
    manifest but with free-form warning `message` fields removed, so the snapshot's
    cryptographic identity depends only on the STRUCTURED violation facts (tier,
    severity, issue, domain, context, expected, observed) — never on human-readable
    wording. Changing a message's phrasing must not change a snapshot's identity.
    """
    import copy
    m = copy.deepcopy(manifest)
    for field in ("accepted_warnings", "governed_exceptions"):
        for w in m.get(field, []):
            w.pop("message", None)
    return m