"""Reading and writing the Hexo project: drafts, posts, existing taxonomy."""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .render import DATE_FORMAT, dump_front_matter


class BlogError(Exception):
    pass


_FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)


def split_front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        data = {}
    return (data if isinstance(data, dict) else {}), m.group(2)


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        flat: List[str] = []
        for v in value:
            flat += _as_list(v)
        return flat
    return [str(value)]


class Blog:
    def __init__(self, root: str):
        self.root = Path(root)
        if not (self.root / "_config.yml").is_file() or not (self.root / "source").is_dir():
            raise BlogError(f"{self.root} does not look like a Hexo blog (no _config.yml or source/). "
                            "Set `blog_dir` in blogpub.yml.")
        self.posts_dir = self.root / "source" / "_posts"
        self.drafts_dir = self.root / "source" / "_drafts"
        self.posts_dir.mkdir(parents=True, exist_ok=True)

    # ---- reading ------------------------------------------------------
    def _front_matters(self, directory: Path) -> List[Tuple[Path, Dict[str, Any]]]:
        if not directory.is_dir():
            return []
        out = []
        for f in sorted(directory.glob("*.md")):
            fm, _ = split_front_matter(f.read_text(encoding="utf-8"))
            out.append((f, fm))
        return out

    def taxonomy(self) -> Tuple[List[str], List[str]]:
        cats: Dict[str, int] = {}
        tags: Dict[str, int] = {}
        for _, fm in self._front_matters(self.posts_dir):
            for c in _as_list(fm.get("categories")):
                cats[c] = cats.get(c, 0) + 1
            for t in _as_list(fm.get("tags")):
                tags[t] = tags.get(t, 0) + 1
        order = lambda d: [k for k, _ in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))]
        return order(cats), order(tags)

    def taxonomy_by_language(self, lang_field: str, languages: List[str]) -> Dict[str, Tuple[List[str], List[str]]]:
        """Existing categories and tags per language, so an English post is offered English names.

        Posts without a language field count for the first (primary) language."""
        cats: Dict[str, Dict[str, int]] = {l: {} for l in languages}
        tags: Dict[str, Dict[str, int]] = {l: {} for l in languages}
        for _, fm in self._front_matters(self.posts_dir):
            lang = str(fm.get(lang_field) or languages[0])
            if lang not in cats:
                continue
            for c in _as_list(fm.get("categories")):
                cats[lang][c] = cats[lang].get(c, 0) + 1
            for t in _as_list(fm.get("tags")):
                tags[lang][t] = tags[lang].get(t, 0) + 1
        order = lambda d: [k for k, _ in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))]
        return {l: (order(cats[l]), order(tags[l])) for l in languages}

    def recent_titles(self, n: int) -> List[str]:
        items = [(str(fm.get("date", "")), str(fm.get("title", ""))) for _, fm in self._front_matters(self.posts_dir)]
        return [t for _, t in sorted(items, reverse=True)[:n] if t]

    def slug_taken(self, slug: str) -> Optional[Path]:
        for d in (self.posts_dir, self.drafts_dir):
            for f in d.glob(f"{slug}*.md") if d.is_dir() else []:
                return f
        return None

    # ---- writing ------------------------------------------------------
    def write_drafts(self, files: Dict[str, str]) -> List[Path]:
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        written = []
        for name, content in files.items():
            target = self.drafts_dir / name
            if target.exists() or (self.posts_dir / name).exists():
                raise BlogError(f"{name} already exists; choose another title or remove the old one first")
            target.write_text(content, encoding="utf-8")
            written.append(target)
        return written

    def images_dir(self, images_dir_cfg: str, slug: str) -> Path:
        return self.root / "source" / str(images_dir_cfg).strip("/") / slug

    # ---- drafts and publishing ---------------------------------------
    def drafts(self) -> List[Path]:
        return sorted(self.drafts_dir.glob("*.md")) if self.drafts_dir.is_dir() else []

    def draft_group(self, slug: str, translation_field: str) -> List[Path]:
        """The draft called `slug` plus every draft connected to it by the translation field."""
        by_slug = {p.stem: p for p in self.drafts()}
        if slug not in by_slug:
            raise BlogError(f"No draft named '{slug}'. Existing drafts: {', '.join(by_slug) or '(none)'}")
        links: Dict[str, set] = {s: set() for s in by_slug}
        for s, p in by_slug.items():
            fm, _ = split_front_matter(p.read_text(encoding="utf-8"))
            other = fm.get(translation_field)
            if other in by_slug:
                links[s].add(other)
                links[other].add(s)
        seen, stack = set(), [slug]
        while stack:
            cur = stack.pop()
            if cur not in seen:
                seen.add(cur)
                stack += list(links[cur])
        return [by_slug[s] for s in sorted(seen)]

    def publish(self, drafts: List[Path], now: Optional[datetime] = None) -> List[Path]:
        """Move drafts into _posts, stamping the publish time."""
        now = now or datetime.now()
        moved = []
        for d in drafts:
            target = self.posts_dir / d.name
            if target.exists():
                raise BlogError(f"{target.name} already exists in _posts")
            fm, body = split_front_matter(d.read_text(encoding="utf-8"))
            fm["date"] = now.strftime(DATE_FORMAT)
            target.write_text(f"{dump_front_matter(fm)}{body if body.startswith(chr(10)) else chr(10) + body}", encoding="utf-8")
            d.unlink()
            moved.append(target)
        if self.drafts_dir.is_dir() and not any(self.drafts_dir.iterdir()):
            shutil.rmtree(self.drafts_dir)
        return moved
