"""Snapshot content_hash — the RD-015 integrity identity.

Algorithm (RD-015, verbatim):
  1. SHA-256 each Parquet file over its raw bytes.
  2. Form (relative_path, file_sha256) pairs; relative_path uses forward slashes,
     relative to the snapshot root.
  3. Sort pairs lexicographically by relative_path.
  4. Serialize the sorted list together with the canonical manifest as one UTF-8
     JSON document: json.dumps(obj, sort_keys=True, separators=(",", ":")).
  5. content_hash = SHA-256 hex digest of that document.

Deterministic, order-independent, content-covering (data bytes via per-file
hashes; semantics via the manifest), and stable across environments (raw bytes,
not Parquet-reader representations).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import hashlib
import json


def sha256_file(path: Path) -> str:
    """SHA-256 hex digest of a file's raw bytes, read in chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def file_hashes(snapshot_root: Path, files: list[Path]) -> list[tuple[str, str]]:
    """(relative_path, file_sha256) pairs, sorted by relative_path.

    relative_path is POSIX-style (forward slashes) relative to snapshot_root, so
    the hash is independent of absolute location and OS path separator.
    """
    pairs = []
    for p in files:
        rel = p.relative_to(snapshot_root).as_posix()
        pairs.append((rel, sha256_file(p)))
    return sorted(pairs, key=lambda t: t[0])


def compute_content_hash(snapshot_root: Path, files: list[Path],
                         manifest: dict[str, Any]) -> str:
    """The RD-015 content_hash for a snapshot's files + canonical manifest."""
    pairs = file_hashes(snapshot_root, files)
    document = {
        "file_hashes": pairs,          # sorted list of [rel_path, sha256]
        "manifest": manifest,
    }
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()