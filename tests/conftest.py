import subprocess
from pathlib import Path

import pytest
from PIL import Image


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def blog(tmp_path):
    """A minimal Hexo project that is also a git repo with a bare remote to push to."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(remote)], check=True)
    root = tmp_path / "blog"
    (root / "source" / "_posts").mkdir(parents=True)
    (root / "_config.yml").write_text("title: Test\nurl: https://example.com\n", encoding="utf-8")
    (root / "source" / "_posts" / "old.md").write_text(
        "---\ntitle: Old post\ndate: 2026-01-01 10:00:00\ncategories:\n  - Dev Notes\ntags:\n  - Hexo\n---\n\nhello\n",
        encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "Tester")
    git(root, "remote", "add", "origin", str(remote))
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "init")
    git(root, "push", "-q", "-u", "origin", "main")
    return root


@pytest.fixture
def png(tmp_path):
    p = tmp_path / "Shot 1.PNG"
    Image.new("RGB", (2400, 1200), (10, 120, 200)).save(p)
    return p
