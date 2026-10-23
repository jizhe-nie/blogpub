import subprocess

import pytest
import yaml

from blogpub import cli, timeline
from blogpub.config import load_config


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def test_excerpt_uses_the_intro_and_strips_markdown():
    body = "This is **the intro** with a [link](https://x.y) and `code`.\n\n<!-- more -->\n\n## Later\n\nnot included"
    assert timeline.excerpt(body) == "This is the intro with a link and `code`."


def test_excerpt_without_marker_takes_first_paragraph_and_truncates():
    body = "# Title\n\n" + ("word " * 100) + "\n\nsecond"
    out = timeline.excerpt(body, limit=50)
    assert out.endswith("…") and len(out) <= 51 and "second" not in out and "Title" not in out


def test_build_entry_applies_prefixes_and_languages(tmp_path):
    cfg = load_config(cwd=tmp_path)
    e = timeline.build_entry({"zh": "标题", "en": "Title"}, {"zh": "简介内容。", "en": "Intro text."}, cfg)
    assert e["tags"] == ["content"]
    assert e["title"] == {"zh": "发布新文章：标题", "en": "New post: Title"}
    assert e["note"] == {"zh": "简介内容。", "en": "Intro text."}


def test_append_note_keeps_existing_comments_and_is_idempotent(tmp_path):
    f = tmp_path / "notes.yml"
    f.write_text('# my comment\n"abc1234":\n  tags: [fix]\n', encoding="utf-8")
    entry = {"tags": ["content"], "title": {"zh": "发布：含冒号: 的标题", "en": "It's: fine"}}
    assert timeline.append_note(f, "my-post", entry) is True
    text = f.read_text(encoding="utf-8")
    assert text.startswith("# my comment")                      # existing content untouched
    data = yaml.safe_load(text)
    assert data["abc1234"] == {"tags": ["fix"]}
    assert data["post:my-post"]["title"]["zh"] == "发布：含冒号: 的标题"   # tricky characters survive
    assert timeline.append_note(f, "my-post", entry) is False   # second time: no change
    assert f.read_text(encoding="utf-8") == text


def test_append_note_creates_the_file(tmp_path):
    f = tmp_path / "deep" / "notes.yml"
    assert timeline.append_note(f, "p", {"tags": ["content"], "title": {"en": "T"}})
    assert yaml.safe_load(f.read_text(encoding="utf-8"))["post:p"]["title"] == {"en": "T"}


NOTES = ("今天把博客搭好了，用的是 Hexo 加 Redefine 主题。\n"
         "遇到的坑：node_modules 被提交了，用 git rm --cached 修复。\n")


def make_blog_with_timeline(blog, tmp_path):
    (blog / "blogpub.yml").write_text("timeline_notes: source/_data/timeline-notes.yml\nprovider: mock\n", encoding="utf-8")
    sh(blog, "git", "add", "blogpub.yml")
    sh(blog, "git", "commit", "-q", "-m", "config")
    notes = tmp_path / "n.md"
    notes.write_text(NOTES, encoding="utf-8")
    return notes


def test_publish_writes_the_timeline_note_in_the_same_commit(blog, tmp_path):
    notes = make_blog_with_timeline(blog, tmp_path)
    cfgfile = str(blog / "blogpub.yml")
    assert cli.main(["new", str(notes), "--blog", str(blog), "--config", cfgfile, "-y"]) == 0
    slug = next((blog / "source" / "_drafts").glob("*.md")).stem
    slug = slug[:-3] if slug.endswith("-en") else slug
    assert cli.main(["publish", slug, "--blog", str(blog), "--config", cfgfile, "-y"]) == 0

    changed = sh(blog, "git", "show", "--name-only", "--format=", "HEAD").splitlines()
    assert "source/_data/timeline-notes.yml" in changed and f"source/_posts/{slug}.md" in changed
    note = yaml.safe_load((blog / "source" / "_data" / "timeline-notes.yml").read_text(encoding="utf-8"))[f"post:{slug}"]
    assert note["tags"] == ["content"] and "Hexo" in note["note"]["zh"]
    assert sh(blog, "git", "status", "-sb").splitlines()[0].endswith("main...origin/main")


def test_publish_without_the_option_leaves_no_timeline_file(blog, tmp_path):
    notes = tmp_path / "n.md"
    notes.write_text(NOTES, encoding="utf-8")
    assert cli.main(["new", str(notes), "--blog", str(blog), "--provider", "mock", "-y", "--languages", "en"]) == 0
    slug = next((blog / "source" / "_drafts").glob("*.md")).stem
    assert cli.main(["publish", slug, "--blog", str(blog), "-y"]) == 0
    assert not (blog / "source" / "_data").exists()


def test_foreign_staged_notes_file_blocks_publish(blog, tmp_path):
    notes = make_blog_with_timeline(blog, tmp_path)
    cfgfile = str(blog / "blogpub.yml")
    cli.main(["new", str(notes), "--blog", str(blog), "--config", cfgfile, "-y", "--languages", "en"])
    slug = next((blog / "source" / "_drafts").glob("*.md")).stem
    (blog / "stray.txt").write_text("x")
    sh(blog, "git", "add", "stray.txt")
    with pytest.raises(SystemExit):
        cli.main(["publish", slug, "--blog", str(blog), "--config", cfgfile, "-y"])
    assert (blog / "source" / "_drafts" / f"{slug}.md").exists()      # nothing moved


def test_excerpt_drops_heading_lines_even_without_a_blank_line_after_them():
    assert timeline.excerpt("# My Title\nThe real intro sentence here.\n\n## Part\n\nmore") == "The real intro sentence here."
