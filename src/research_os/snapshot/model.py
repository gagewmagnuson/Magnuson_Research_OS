"""Normalized, storage-agnostic representation of pulled snapshot data, plus the
request spec that defines what was asked for. The completeness checks consume
these and nothing else — they do not know whether the data came from HTTP,
Parquet, or a test fixture. This is what keeps the four checks pure and unit-
testable while still (via the increment-3 reader) validating the real staged
artifact.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date


# --- what was requested (the tier-2 "expected" baseline) ---------------------

@dataclass(frozen=True)
class SnapshotRequest:
    """The spec that defines what this snapshot was supposed to contain.

    A snapshot is ALL HISTORY as knowable at a single knowledge cutoff (`as_of`),
    per ARCHITECTURE §3: "Every read composing a snapshot uses the same
    as_of = snapshot_date, including the full history of bars." There is NO
    session-date window — windowing is a read-time research concern, not a pull
    parameter. The only temporal bound is the knowledge cutoff `as_of`.
    """
    as_of: date                        # the ONE knowledge cutoff = snapshot_date
    universe_code: str                 # e.g. 'SP500'
    feature_versions: list[dict]       # [{"name": "momentum_12_1", "version": 1}, ...]
    macro_series: list[str]            # e.g. ['CPIAUCSL', ...]
    # Dev-slice restriction ONLY: restricts the PIT-membership population to a
    # subset for development. Never an independent population definition (RD-014).
    # None -> full universe membership as_of.
    requested_symbols: list[str] | None = None


# --- normalized pulled data (what the checks validate) -----------------------

@dataclass(frozen=True)
class BarsSeries:
    security_id: int
    symbol: str | None
    session_dates: list[date]          # sessions present in bars for this security

@dataclass(frozen=True)
class GoldSeries:
    security_id: int
    symbol: str | None
    session_dates: list[date]          # sessions present in gold for this security

@dataclass(frozen=True)
class UniverseMember:
    security_id: int
    symbol: str | None

@dataclass(frozen=True)
class MacroSeries:
    series_id: str
    observation_count: int

@dataclass(frozen=True)
class PulledData:
    """The full normalized snapshot content the checks operate on."""
    as_of: date
    universe_code: str
    members: list[UniverseMember]
    bars: list[BarsSeries]
    gold: list[GoldSeries]
    macro: list[MacroSeries]
    # The unresolved symbol list carried through from /v1/features (RD: producer
    # transparency). Tier 2 requires this be empty or fully explained.
    features_unresolved: list[str] = field(default_factory=list)