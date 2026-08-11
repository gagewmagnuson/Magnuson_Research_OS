"""B3: git-cleanliness enforcement (RD-011).

These tests build a throwaway git repo in a temp dir so they never depend on the
state of the real repo (which may be dirty during development — exactly the case
RD-011 handles).
"""
import subprocess
from pathlib import Path
import pytest
from research_os.ledger.git_state import (
    current_sha, is_clean, require_clean_sha, DirtyWorkingTreeError,
)


def _run(*args, cwd):
    subprocess.run(args, cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def temp_repo(tmp_path):
    """A fresh git repo with one commit."""
    _run("git", "init", cwd=tmp_path)
    _run("git", "config", "user.email", "t@t.t", cwd=tmp_path)
    _run("git", "config", "user.name", "t", cwd=tmp_path)
    (tmp_path / "a.txt").write_text("hello")
    _run("git", "add", "a.txt", cwd=tmp_path)
    _run("git", "commit", "-m", "init", cwd=tmp_path)
    return tmp_path


def test_clean_repo_is_clean(temp_repo):
    assert is_clean(cwd=temp_repo) is True


def test_current_sha_is_40_hex(temp_repo):
    sha = current_sha(cwd=temp_repo)
    assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)


def test_require_clean_sha_returns_sha_when_clean(temp_repo):
    assert require_clean_sha(cwd=temp_repo) == current_sha(cwd=temp_repo)


def test_modified_tracked_file_is_dirty(temp_repo):
    (temp_repo / "a.txt").write_text("changed")
    assert is_clean(cwd=temp_repo) is False
    with pytest.raises(DirtyWorkingTreeError):
        require_clean_sha(cwd=temp_repo)


def test_untracked_file_is_dirty(temp_repo):
    (temp_repo / "b.txt").write_text("new")
    assert is_clean(cwd=temp_repo) is False
    with pytest.raises(DirtyWorkingTreeError):
        require_clean_sha(cwd=temp_repo)