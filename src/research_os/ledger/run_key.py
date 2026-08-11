"""The reproducibility contract (SCHEMA §8, RD-003).

A run_key is a serialized set of identifiers that fully determines a research
result. Every identifier must resolve to a real row in the registries before the
engine accepts a trial. This module defines the structure and the validation;
it does not write anything.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any
import json
import psycopg


@dataclass(frozen=True)
class RunKey:
    """SCHEMA §8 reproducibility contract. Immutable once constructed."""
    spec_id: int
    feature_versions: list[dict[str, Any]]   # [{"name": ..., "version": ...}, ...]
    universe_spec: dict[str, Any]            # membership rule + as_of rule (RD-014)
    eval_config_version: int
    cost_model_version: int
    data_as_of: int                          # snapshot_id (the immutable artifact)
    code_sha: str                            # committed git sha (RD-011)
    seed: int

    def to_json(self) -> str:
        """Canonical JSON serialization for storage in trial_ledger.run_key."""
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @staticmethod
    def from_json(s: str) -> "RunKey":
        return RunKey(**json.loads(s))


class RunKeyValidationError(Exception):
    """Raised when a run_key references something that does not exist (RD-003)."""


def validate(run_key: RunKey, conn: psycopg.Connection) -> None:
    """Confirm every identifier in the run_key resolves to a real registry row.

    Raises RunKeyValidationError listing every unresolved reference. This is the
    RD-003 guarantee: the engine validates every identifier before accepting a
    trial. Read-only; does not write.
    """
    errors: list[str] = []

    def exists(sql: str, params: tuple) -> bool:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone() is not None

    if not exists("select 1 from research.signal_spec where spec_id = %s",
                  (run_key.spec_id,)):
        errors.append(f"spec_id {run_key.spec_id} not in signal_spec")

    if not exists("select 1 from research.evaluation_config where eval_config_version = %s",
                  (run_key.eval_config_version,)):
        errors.append(f"eval_config_version {run_key.eval_config_version} not in evaluation_config")

    if not exists("select 1 from research.cost_model where cost_model_version = %s",
                  (run_key.cost_model_version,)):
        errors.append(f"cost_model_version {run_key.cost_model_version} not in cost_model")

    if not exists("select 1 from research.snapshot where snapshot_id = %s",
                  (run_key.data_as_of,)):
        errors.append(f"data_as_of (snapshot_id) {run_key.data_as_of} not in snapshot")

    # Feature versions pin Trading OS features by (name, version). At R0 these are
    # validated structurally (well-formed entries); cross-checking against the
    # Trading OS feature registry happens when the snapshot pull lands (R1).
    for i, fv in enumerate(run_key.feature_versions):
        if not (isinstance(fv, dict) and "name" in fv and "version" in fv):
            errors.append(f"feature_versions[{i}] must have 'name' and 'version': {fv!r}")

    if errors:
        raise RunKeyValidationError("; ".join(errors))
