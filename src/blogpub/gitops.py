"""Git operations. Only the files blogpub created are staged, nothing else is touched."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import List, Optional


class GitError(Exception):
    pass


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed:\n{(proc.stderr or proc.stdout).strip()}")
    return proc.stdout.strip()


def is_repo(root: Path) -> bool:
    try:
        _git(root, "rev-parse", "--is-inside-work-tree")
        return True
    except (GitError, FileNotFoundError):
        return False


def other_staged_files(root: Path, mine: List[str]) -> List[str]:
    """Files already staged that are not ours; committing would silently include them."""
    staged = [x for x in _git(root, "diff", "--cached", "--name-only").splitlines() if x]
    mine_set = {m.rstrip("/") for m in mine}
    return [s for s in staged if not any(s == m or s.startswith(m + "/") for m in mine_set)]


def commit_and_push(root: Path, paths: List[str], message: str, push: bool = True) -> str:
    """`paths` are relative to the repo root (files or folders). Returns the short commit hash."""
    if not is_repo(root):
        raise GitError(f"{root} is not a git repository")
    foreign = other_staged_files(root, paths)
    if foreign:
        raise GitError("These files are already staged and would be included in the commit:\n  "
                       + "\n  ".join(foreign) + "\nCommit or unstage them first (git restore --staged <file>).")
    _git(root, "add", "--", *paths)
    if not _git(root, "diff", "--cached", "--name-only"):
        raise GitError("Nothing to commit")
    _git(root, "commit", "-q", "-m", message)
    short = _git(root, "rev-parse", "--short", "HEAD")
    if push:
        _git(root, "push")
    return short


def actions_url(root: Path) -> Optional[str]:
    try:
        remote = _git(root, "remote", "get-url", "origin")
    except GitError:
        return None
    m = re.search(r"github\.com[:/]+([^/]+)/([^/]+?)(?:\.git)?$", remote)
    return f"https://github.com/{m.group(1)}/{m.group(2)}/actions" if m else None
