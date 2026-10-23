import json

import pytest

from blogpub.config import load_config
from blogpub.generate import GenerationError, PostSpec, _extract_json, build_user_prompt, generate, validate
from blogpub.providers import make_provider
from blogpub.render import ensure_more, render_files, replace_images


def good(body_zh="第一段介绍文字，足够长。\n\n## 小节\n\n正文内容在这里。", body_en="Intro paragraph long enough.\n\n## Section\n\nBody here."):
    return {"slug": "my-post", "categories": {"zh": ["开发笔记"], "en": ["Dev Notes"]},
            "tags": {"zh": ["Hexo"], "en": ["Hexo"]},
            "posts": {"zh": {"title": "标题", "body": body_zh}, "en": {"title": "Title", "body": body_en}}}


def test_extract_json_handles_fences_and_chatter():
    raw = 'Sure! Here it is:\n```json\n{"a": 1}\n```\nHope that helps.'
    assert _extract_json(raw) == {"a": 1}
    with pytest.raises(GenerationError):
        _extract_json("no json here")


def test_validate_ok_and_appends_missing_images():
    spec = validate(good(), ["zh", "en"], ["01-a.png"])
    assert spec.slug == "my-post"
    assert "![01-a.png](IMG:01-a.png)" in spec.posts["zh"]["body"]
    assert any("did not place" in w for w in spec.warnings)


def test_validate_rejects_unknown_image_and_missing_language():
    data = good(body_zh="段落足够长的内容。\n\n![x](IMG:ghost.png)")
    with pytest.raises(GenerationError, match="ghost.png"):
        validate(data, ["zh", "en"], [])
    del data["posts"]["en"]
    with pytest.raises(GenerationError, match="posts.en"):
        validate(data, ["zh", "en"], [])


def test_validate_fixes_bad_slug_and_accepts_plain_list_taxonomy():
    data = good()
    data["slug"] = "My Post!!"
    data["tags"] = ["a", "b"]
    spec = validate(data, ["zh", "en"], [])
    assert spec.slug == "my-post"
    assert spec.tags == {"zh": ["a", "b"], "en": ["a", "b"]}


class Flaky:
    """Fails once with junk, then answers properly."""
    def __init__(self):
        self.calls = []

    def complete(self, system, user, images=None):
        self.calls.append(user)
        return "oops" if len(self.calls) == 1 else json.dumps(good())


def test_generate_retries_once_with_feedback():
    p = Flaky()
    spec = generate(p, "prompt", ["zh", "en"], [])
    assert spec.slug == "my-post" and len(p.calls) == 2
    assert "rejected" in p.calls[1]


def test_generate_gives_up_after_retry():
    class Bad:
        def complete(self, *a, **k):
            return "nope"
    with pytest.raises(GenerationError, match="unusable"):
        generate(Bad(), "p", ["en"], [])


def test_prompt_contains_all_sections():
    prompt = build_user_prompt("my notes here", ["zh", "en"], ["01-a.png"],
                               {"zh": (["开发笔记"], ["Hexo"]), "en": (["Dev Notes"], [])}, ["Old"],
                               "be casual", "Hint", "Dev", ["x"])
    for needle in ("LANGUAGES: zh, en", "<<<IMAGES", "- 01-a.png", "<<<NOTES", "my notes here",
                   "EXISTING CATEGORIES [zh]: 开发笔记", "EXISTING CATEGORIES [en]: Dev Notes",
                   "EXISTING TAGS [zh]: Hexo", "EXISTING TAGS [en]: (none yet)", "be casual"):
        assert needle in prompt


def test_replace_images_and_more_marker():
    assert replace_images("![a](IMG:x.png)", "/images/posts/s") == "![a](/images/posts/s/x.png)"
    body = "Intro line.\n\n## Heading\n\nText."
    assert ensure_more(body).splitlines()[2] == "<!-- more -->"
    assert ensure_more("one\n\ntwo") == "one\n\ntwo"           # too short to split
    assert ensure_more("a\n\n<!-- more -->\n\nb") == "a\n\n<!-- more -->\n\nb"


def test_render_pairs_translations(tmp_path):
    cfg = load_config(cwd=tmp_path)
    spec = validate(good(), ["zh", "en"], [])
    files = render_files(spec, ["zh", "en"], cfg)
    assert set(files) == {"my-post.md", "my-post-en.md"}
    zh, en = files["my-post.md"], files["my-post-en.md"]
    assert "post_lang: zh" in zh and "translation: my-post-en" in zh
    assert "post_lang: en" in en and "translation: my-post" in en
    assert "title: 标题" in zh and "- 开发笔记" in zh


def test_render_single_language_has_no_pairing(tmp_path):
    cfg = load_config(cwd=tmp_path)
    data = good()
    data["posts"] = {"en": data["posts"]["en"]}
    spec = validate(data, ["en"], [])
    files = render_files(spec, ["en"], cfg)
    assert list(files) == ["my-post.md"] and "post_lang" not in files["my-post.md"]


def test_make_provider_requires_model_for_custom(tmp_path):
    from blogpub.providers import ProviderError
    cfg = load_config(cwd=tmp_path)
    cfg["provider"] = "custom"
    with pytest.raises(ProviderError, match="model"):
        make_provider(cfg)


def test_date_is_written_unquoted_like_hexo_templates(tmp_path):
    from datetime import datetime
    cfg = load_config(cwd=tmp_path)
    spec = validate(good(), ["zh", "en"], [])
    text = render_files(spec, ["zh", "en"], cfg, now=datetime(2026, 10, 23, 9, 5, 7))["my-post.md"]
    assert "\ndate: 2026-10-23 09:05:07\n" in text and "'" not in text.split("---")[1]
