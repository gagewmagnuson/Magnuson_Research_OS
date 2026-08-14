"""Tests for the canonical manifest builder — determinism and content."""
from __future__ import annotations
from datetime import date, datetime, timezone
import pytest
from research_os.snapshot.model import (
    SnapshotRequest, PulledData, BarsSeries, GoldSeries, UniverseMember, MacroSeries,
)
from research_os.snapshot.violation import Violation, Tier, Severity
from research_os.snapshot.manifest import build_manifest

AS_OF = date(2008, 6, 30)
SESS = [date(2008, 6, 2), date(2008, 6, 3)]
FIXED_TS = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)


def _req():
    return SnapshotRequest(as_of=AS_OF, universe_code="SP500",
                           feature_versions=[{"name": "momentum_12_1", "version": 1}],
                           macro_series=["CPIAUCSL"], requested_symbols=["AAPL"])


def _data():
    return PulledData(as_of=AS_OF, universe_code="SP500",
                      members=[UniverseMember(1, "AAPL")],
                      bars=[BarsSeries(1, "AAPL", list(SESS))],
                      gold=[GoldSeries(1, "AAPL", list(SESS))],
                      macro=[MacroSeries("CPIAUCSL", 5)],
                      features_unresolved=[])


def test_manifest_scope_and_counts():
    m = build_manifest(_req(), _data(), "2026-07-01T00:00:00+00:00",
                       warnings=[], code_sha="abc123", pulled_at=FIXED_TS)
    assert m["scope"]["trading_os_as_of"] == "2026-07-01T00:00:00+00:00"
    assert m["scope"]["snapshot_date"] == "2008-06-30"
    assert m["scope"]["universe_code"] == "SP500"
    assert m["row_counts"]["bars_securities"] == 1
    assert m["row_counts"]["bars_sessions_total"] == 2
    assert m["pull"]["research_os_code_sha"] == "abc123"


def test_manifest_records_warnings():
    w = Violation(Tier.REQUEST_DERIVED, Severity.WARNING, "nonmember_unresolved",
                  "FAKE not a member", domain="gold", symbol="FAKE")
    m = build_manifest(_req(), _data(), "t", warnings=[w], code_sha="x", pulled_at=FIXED_TS)
    assert len(m["accepted_warnings"]) == 1
    assert m["accepted_warnings"][0]["issue"] == "nonmember_unresolved"


def test_manifest_deterministic():
    a = build_manifest(_req(), _data(), "t", [], "sha", pulled_at=FIXED_TS)
    b = build_manifest(_req(), _data(), "t", [], "sha", pulled_at=FIXED_TS)
    assert a == b


def test_manifest_includes_producer_dq():
    m = build_manifest(_req(), _data(), "t", [], "sha",
                       producer_dq={"status": "ok", "failing_checks": 0}, pulled_at=FIXED_TS)
    assert m["producer_dq"]["status"] == "ok"


def test_canonical_hash_form_strips_message():
    from research_os.snapshot.manifest import canonical_manifest_for_hash
    w = Violation(Tier.REQUEST_DERIVED, Severity.WARNING, "nonmember_unresolved",
                  "some wording", domain="gold", symbol="FAKE")
    m = build_manifest(_req(), _data(), "t", warnings=[w], code_sha="x", pulled_at=FIXED_TS)
    canon = canonical_manifest_for_hash(m)
    # structured fields survive; message is gone from the hashed form.
    assert canon["accepted_warnings"][0]["issue"] == "nonmember_unresolved"
    assert canon["accepted_warnings"][0]["symbol"] == "FAKE"
    assert "message" not in canon["accepted_warnings"][0]
    # but the STORED manifest still has the message for humans.
    assert m["accepted_warnings"][0]["message"] == "some wording"


def test_message_wording_does_not_affect_hash_form():
    from research_os.snapshot.manifest import canonical_manifest_for_hash
    w1 = Violation(Tier.REQUEST_DERIVED, Severity.WARNING, "nonmember_unresolved",
                   "wording A", domain="gold", symbol="FAKE")
    w2 = Violation(Tier.REQUEST_DERIVED, Severity.WARNING, "nonmember_unresolved",
                   "completely different wording B", domain="gold", symbol="FAKE")
    m1 = build_manifest(_req(), _data(), "t", [w1], "x", pulled_at=FIXED_TS)
    m2 = build_manifest(_req(), _data(), "t", [w2], "x", pulled_at=FIXED_TS)
    # same structured facts, different wording -> identical hashed form.
    assert canonical_manifest_for_hash(m1) == canonical_manifest_for_hash(m2)