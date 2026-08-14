"""Tests for the RD-015 content_hash: deterministic, order-independent,
content-covering. These lock the integrity guarantee the reproducibility tuple
relies on."""
from __future__ import annotations
from pathlib import Path
import pytest
from research_os.snapshot.content_hash import (
    sha256_file, file_hashes, compute_content_hash,
)


def _write(p: Path, content: bytes):
    p.write_bytes(content)
    return p


@pytest.fixture
def snap(tmp_path):
    _write(tmp_path / "bars.parquet", b"BARS-DATA")
    _write(tmp_path / "gold.parquet", b"GOLD-DATA")
    _write(tmp_path / "universe.parquet", b"UNIV-DATA")
    _write(tmp_path / "macro.parquet", b"MACRO-DATA")
    return tmp_path


def _files(root):
    return sorted(root.glob("*.parquet"))


MANIFEST = {"as_of": "2008-06-30", "universe": "SP500", "row_counts": {"bars": 6}}


def test_deterministic_same_input_same_hash(snap):
    h1 = compute_content_hash(snap, _files(snap), MANIFEST)
    h2 = compute_content_hash(snap, _files(snap), MANIFEST)
    assert h1 == h2
    assert len(h1) == 64                       # sha256 hex


def test_order_independent(snap):
    files = _files(snap)
    h1 = compute_content_hash(snap, files, MANIFEST)
    h2 = compute_content_hash(snap, list(reversed(files)), MANIFEST)
    assert h1 == h2                            # sorting makes enumeration order irrelevant


def test_data_change_changes_hash(snap):
    h1 = compute_content_hash(snap, _files(snap), MANIFEST)
    (snap / "gold.parquet").write_bytes(b"GOLD-DATA-ALTERED")   # one byte-set changed
    h2 = compute_content_hash(snap, _files(snap), MANIFEST)
    assert h1 != h2                            # data-covering


def test_manifest_change_changes_hash(snap):
    h1 = compute_content_hash(snap, _files(snap), MANIFEST)
    h2 = compute_content_hash(snap, _files(snap), {**MANIFEST, "universe": "RUSSELL2000"})
    assert h1 != h2                            # semantics-covering


def test_manifest_key_order_irrelevant(snap):
    # sort_keys=True means dict insertion order doesn't affect the hash.
    m1 = {"a": 1, "b": 2}
    m2 = {"b": 2, "a": 1}
    assert compute_content_hash(snap, _files(snap), m1) == \
           compute_content_hash(snap, _files(snap), m2)


def test_rehash_detects_tampering(snap):
    """The verification property: a stored hash re-computed later either matches
    or the artifact was altered."""
    registered = compute_content_hash(snap, _files(snap), MANIFEST)
    # ... time passes, someone edits a file ...
    (snap / "bars.parquet").write_bytes(b"TAMPERED")
    recomputed = compute_content_hash(snap, _files(snap), MANIFEST)
    assert recomputed != registered           # tampering is detectable