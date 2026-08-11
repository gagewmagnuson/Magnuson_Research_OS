"""Git working-tree state for reproducibility (RD-011).

No ledgered trial may be created from an uncommitted code state. The ledgered
entry point calls require_clean_sha() to obtain the committed sha, refusing if
the working tree is dirty. Exploratory/dev code that never writes a trial is
unaffected — this check lives on the ledger door, not the whole system.
"""
from __future__ import annotations
import subprocess
from pathlib import Path

# Repo root = three levels up from this file: ledger/ -> research_os/ -> src/ -> repo
REPO_ROOT = Path(__file__).resolve().parents[3]


class DirtyWorkingTreeError(Exception):
    """Raised when a ledgered trial is attempted from an uncommitted code state (RD-011)."""


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def current_sha(cwd: Path | None = None) -> str:
    """The current HEAD commit sha (full)."""
    return _git("rev-parse", "HEAD", cwd=cwd)


def is_clean(cwd: Path | None = None) -> bool:
    """True iff the working tree has no uncommitted changes (tracked or staged).

    Uses `git status --porcelain`: empty output means clean. Untracked files are
    included, so a stray untracked file also counts as dirty — deliberately
    strict, because reproducibility depends on HEAD fully describing the code.
    """
    return _git("status", "--porcelain", cwd=cwd) == ""


def require_clean_sha(cwd: Path | None = None) -> str:
    """Return the committed sha, or raise if the working tree is dirty (RD-011)."""
    if not is_clean(cwd):
        raise DirtyWorkingTreeError(
            "Working tree is dirty; a ledgered trial requires a clean, committed "
            "code state (RD-011). Commit or stash changes, then retry."
        )
    return current_sha(cwd)