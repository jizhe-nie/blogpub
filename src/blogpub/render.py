"""Turn a PostSpec into Hexo post files."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import yaml

from .generate import PostSpec

_IMG_REF = re.compile(r"!\[([^\]]*)\]\(IMG:([^)\s]+)\)")
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def replace_images(body: str, base_url: str) -> str:
    """`![alt](IMG:file.png)` -> `![alt](/images/posts/<slug>/file.png)`."""
    return _IMG_REF.sub(lambda m: f"![{m.group(1)}]({base_url}/{m.group(2)})", body)


def ensure_more(body: str) -> str:
    """Insert Hexo's excerpt marker after the first paragraph so lists show a short intro."""
    if "<!-- more -->" in body:
        return body
    blocks = re.split(r"\n\s*\n", body.strip())
    if len(blocks) < 3:
        return body
    for i, block in enumerate(blocks[:3]):
        if not block.lstrip().startswith(("#", "```", "!", "<", ">", "-", "*", "|")):
            blocks.insert(i + 1, "<!-- more -->")
            return "\n\n".join(blocks)
    return body


def file_slug(spec_slug: str, lang: str, languages: List[str], suffix: str) -> str:
    return spec_slug if lang == languages[0] else spec_slug + suffix.format(lang=lang)


def dump_front_matter(data: Dict[str, Any]) -> str:
    """YAML front matter. The date is written unquoted (`date: 2026-10-23 09:00:00`) like Hexo's own templates."""
    data = dict(data)
    date = data.pop("date", None)
    lines = []
    if "title" in data:
        lines.append(yaml.safe_dump({"title": data.pop("title")}, allow_unicode=True, width=1000).rstrip())
    if date is not None:
        lines.append(f"date: {date}")
    if data:
        lines.append(yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000).rstrip())
    return "---\n" + "\n".join(lines) + "\n---\n"


def front_matter(title: str, date: datetime, categories: List[str], tags: List[str],
                 pairing: Optional[Dict[str, str]]) -> str:
    data: Dict[str, Any] = {"title": title, "date": date.strftime(DATE_FORMAT)}
    if pairing:
        data.update(pairing)
    if categories:
        data["categories"] = categories
    if tags:
        data["tags"] = tags
    return dump_front_matter(data)


def render_files(spec: PostSpec, languages: List[str], cfg: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, str]:
    """Return {file name: file content}, e.g. {'my-post.md': ..., 'my-post-en.md': ...}."""
    now = now or datetime.now()
    images_dir = str(cfg["images"]["dir"]).strip("/")
    root = str(cfg["site_root"]).rstrip("/")
    base_url = f"{root}/{images_dir}/{spec.slug}"
    fm_cfg = cfg["front_matter"]
    slugs = {lang: file_slug(spec.slug, lang, languages, cfg["slug_suffix"]) for lang in languages}

    files: Dict[str, str] = {}
    for lang in languages:
        post = spec.posts[lang]
        pairing: Optional[Dict[str, str]] = None
        if len(languages) > 1:
            other = languages[1] if lang == languages[0] else languages[0]
            pairing = {fm_cfg["lang_field"]: lang, fm_cfg["translation_field"]: slugs[other]}
        body = ensure_more(replace_images(post["body"], base_url))
        head = front_matter(post["title"], now, spec.categories.get(lang, []), spec.tags.get(lang, []), pairing)
        files[f"{slugs[lang]}.md"] = f"{head}\n{body.strip()}\n"
    return files
