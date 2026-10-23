import subprocess
from pathlib import Path

import pytest

from blogpub import cli, gitops
from blogpub.blog import Blog, BlogError, split_front_matter


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def test_blog_requires_hexo_project(tmp_path):
    with pytest.raises(BlogError, match="Hexo"):
        Blog(str(tmp_path))


def test_taxonomy_and_recent_titles(blog):
    b = Blog(str(blog))
    assert b.taxonomy() == (["Dev Notes"], ["Hexo"])
    assert b.recent_titles(3) == ["Old post"]


def test_commit_only_stages_own_files(blog):
    (blog / "mine.md").write_text("mine")
    (blog / "other.txt").write_text("not mine")
    sh(blog, "git", "add", "other.txt")
    with pytest.raises(gitops.GitError, match="already staged"):
        gitops.commit_and_push(blog, ["mine.md"], "msg")
    sh(blog, "git", "restore", "--staged", "other.txt")
    short = gitops.commit_and_push(blog, ["mine.md"], "msg")
    assert short and "mine.md" in sh(blog, "git", "show", "--name-only", "--format=", "HEAD")
    assert "other.txt" not in sh(blog, "git", "show", "--name-only", "--format=", "HEAD")
    assert sh(blog, "git", "status", "-sb").splitlines()[0].endswith("main...origin/main")  # pushed


def run(argv):
    return cli.main(argv)


NOTES = ("今天把博客搭好了，用的是 Hexo 加 Redefine 主题。\n"
         "遇到的坑：node_modules 被提交了，用 git rm --cached 修复。\n"
         "截图 Shot 1.PNG 是最终效果。")


def test_end_to_end_new_preview_free_publish(blog, png, tmp_path, capsys):
    notes = tmp_path / "notes.md"
    notes.write_text(NOTES, encoding="utf-8")
    args = ["new", str(notes), "-i", str(png), "--blog", str(blog), "--provider", "mock", "-y"]
    assert run(args) == 0

    drafts = sorted(p.name for p in (blog / "source" / "_drafts").glob("*.md"))
    assert len(drafts) == 2
    slug = drafts[0][:-3] if not drafts[0].endswith("-en.md") else drafts[1][:-3]
    image_dir = blog / "source" / "images" / "posts" / slug
    assert [p.name for p in image_dir.iterdir()] == ["01-shot-1.png"]
    text = (blog / "source" / "_drafts" / f"{slug}.md").read_text(encoding="utf-8")
    assert f"(/images/posts/{slug}/01-shot-1.png)" in text and "IMG:" not in text

    assert run(["drafts", "--blog", str(blog)]) == 0
    assert run(["publish", slug, "--blog", str(blog), "-y"]) == 0

    posts = sorted(p.name for p in (blog / "source" / "_posts").glob("*.md"))
    assert len(posts) == 3 and not (blog / "source" / "_drafts").exists()
    committed = sh(blog, "git", "show", "--name-only", "--format=%s", "HEAD")
    assert committed.splitlines()[0].startswith("New post:")
    assert f"source/images/posts/{slug}/01-shot-1.png" in committed
    assert sh(blog, "git", "status", "-sb").splitlines()[0].endswith("main...origin/main")
    fm, _ = split_front_matter((blog / "source" / "_posts" / f"{slug}.md").read_text(encoding="utf-8"))
    assert fm["translation"] == f"{slug}-en" and fm["post_lang"] == "zh"


def test_new_refuses_notes_with_secrets_before_calling_the_model(blog, tmp_path, capsys):
    notes = tmp_path / "n.md"
    notes.write_text("这是一段足够长的笔记。\nexport KEY=sk-proj-" + "Zz9Yy8Xx" * 4 + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        run(["new", str(notes), "--blog", str(blog), "--provider", "mock", "-y"])
    assert "secrets found" in capsys.readouterr().err
    assert not (blog / "source" / "_drafts").exists()


def test_publish_blocks_secrets_in_draft_and_foreign_staged_files(blog, tmp_path):
    notes = tmp_path / "n.md"
    notes.write_text(NOTES, encoding="utf-8")
    assert run(["new", str(notes), "--blog", str(blog), "--provider", "mock", "-y", "--languages", "en"]) == 0
    draft = next((blog / "source" / "_drafts").glob("*.md"))
    slug = draft.stem
    draft.write_text(draft.read_text(encoding="utf-8") + "\nghp_" + "a" * 36 + "\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        run(["publish", slug, "--blog", str(blog), "-y"])
    assert draft.exists()                                     # nothing was moved
    draft.write_text(draft.read_text(encoding="utf-8").replace("ghp_" + "a" * 36, ""), encoding="utf-8")

    (blog / "stray.txt").write_text("x")
    sh(blog, "git", "add", "stray.txt")
    with pytest.raises(SystemExit):
        run(["publish", slug, "--blog", str(blog), "-y"])
    assert draft.exists()                                     # checked before moving anything


def test_slug_collision_is_reported(blog, tmp_path):
    notes = tmp_path / "n.md"
    notes.write_text(NOTES, encoding="utf-8")
    args = ["new", str(notes), "--blog", str(blog), "--provider", "mock", "-y", "--languages", "en", "--slug", "old"]
    (blog / "source" / "_posts" / "old.md").exists()
    with pytest.raises(SystemExit):
        run(args)


def test_dry_run_writes_nothing(blog, tmp_path, capsys):
    notes = tmp_path / "n.md"
    notes.write_text(NOTES, encoding="utf-8")
    assert run(["new", str(notes), "--blog", str(blog), "--provider", "mock", "-y", "--dry-run"]) == 0
    assert not (blog / "source" / "_drafts").exists()
    assert "--dry-run" in capsys.readouterr().out


def test_taxonomy_is_listed_per_language_so_english_posts_get_english_names(blog):
    post = blog / "source" / "_posts" / "old-en.md"
    post.write_text("---\ntitle: Old EN\npost_lang: en\ncategories:\n  - Dev Notes\ntags:\n  - Deep Learning\n---\n\nhi\n", encoding="utf-8")
    zh = blog / "source" / "_posts" / "old-zh.md"
    zh.write_text("---\ntitle: 旧文章\npost_lang: zh\ncategories:\n  - 开发笔记\ntags:\n  - 深度学习\n---\n\n你好\n", encoding="utf-8")
    tax = Blog(str(blog)).taxonomy_by_language("post_lang", ["zh", "en"])
    assert tax["en"] == (["Dev Notes"], ["Deep Learning"])
    # old.md has no language field: it counts for the primary language (zh)
    assert "开发笔记" in tax["zh"][0] and "Dev Notes" in tax["zh"][0] and "Dev Notes" not in tax["en"][0][1:]


def test_running_in_the_wrong_folder_explains_what_to_do(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)          # no blogpub.yml and not a blog
    with pytest.raises(SystemExit):
        run(["drafts"])
    err = capsys.readouterr().err
    assert "cd into it first" in err and "--blog" in err
