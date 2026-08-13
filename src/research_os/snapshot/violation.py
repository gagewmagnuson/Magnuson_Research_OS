"""Violation: a rich, diagnostic completeness failure (or warning). A failed
snapshot must say exactly what is wrong and where — not merely 'incomplete' —
because a 2am monthly pull failure needs to be diagnosable from the record alone.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any


class Tier(str, Enum):
    STRUCTURAL = "structural"                 # tier 1
    REQUEST_DERIVED = "request_derived"       # tier 2
    CROSS_DOMAIN = "cross_domain"             # tier 3
    EMPIRICAL_SANITY = "empirical_sanity"     # tier 4


class Severity(str, Enum):
    HARD = "hard"        # blocks registration (tiers 1-3, and governed tier-4)
    WARNING = "warning"  # recorded, does not block (default tier-4)


@dataclass(frozen=True)
class Violation:
    tier: Tier
    severity: Severity
    issue: str                       # short machine code, e.g. 'gold_missing_sessions'
    message: str                     # human-readable, diagnostic
    domain: str | None = None        # 'bars' | 'gold' | 'universe' | 'macro'
    security_id: int | None = None
    symbol: str | None = None
    expected: Any = None
    observed: Any = None

    def is_blocking(self) -> bool:
        return self.severity is Severity.HARD