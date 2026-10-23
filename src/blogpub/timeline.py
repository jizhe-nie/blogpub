"""Optional: record each published post in the blog's build-timeline notes file.

The note is keyed `post:<slug>` rather than by commit hash, because the hash is only known
after the commit, and we want the note to land in the *same* commit as the post. A timeline
that understands this key (see the author's blog) matches it to the commit that added
`source/_posts/<slug>.md`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

import yaml

HEADER = (
    "# Build-timeline notes. blogpub adds one entry per published post (key: post:<slug>).\n"
    "# Entries can also be written by hand; keep them in this format.\n\n"
)

_MORE = "<!-- more -->"


def excerpt(body: str, limit: int = 220) -> str:
    """The post's intro as plain text: what comes before <!-- more -->, else the first paragraph."""
    body = re.sub(r"^\s*#+.*$", "", body, flags=re.M)  # heading lines are never part of the intro
    text = body.split(_MORE, 1)[0] if _MORE in body else next(
        (b for b in re.split(r"\n\s*\n", body.strip()) if b.strip() and not b.lstrip().startswith(("#", "```", "!", "<"))), "")
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)               # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)           # links -> their text
    text = re.sub(r"^\s*(>\s*|[-*]\s+)", "", text, flags=re.M)      # quote / bullet markers
    text = re.sub(r"<!--.*?-->|<[^>]+>", "", text, flags=re.S)     # html and comments
    text = re.sub(r"[*_]{1,3}([^*_\n]+)[*_]{1,3}", r"\1", text)    # emphasis
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip(" ,.;，。；、") + "…"
    return text


def build_entry(titles: Dict[str, str], bodies: Dict[str, str], cfg: Dict[str, Any]) -> Dict[str, Any]:
    prefixes = cfg.get("timeline_title_prefix") or {}
    entry: Dict[str, Any] = {
        "tags": list(cfg.get("timeline_tags") or ["content"]),
        "title": {lang: f"{prefixes.get(lang, '')}{title}" for lang, title in titles.items()},
    }
    notes = {lang: excerpt(body) for lang, body in bodies.items()}
    notes = {lang: n for lang, n in notes.items() if n}
    if notes:
        entry["note"] = notes
    return entry


def append_note(path: Path, slug: str, entry: Dict[str, Any]) -> bool:
    """Append `post:<slug>` to the notes file without touching what is already there
    (re-dumping the whole file would lose its comments). Returns False if it already exists."""
    key = f"post:{slug}"
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if existing:
        loaded = yaml.safe_load(existing) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{path} is not a YAML mapping")
        if key in loaded:
            return False
    block = yaml.safe_dump({key: entry}, allow_unicode=True, sort_keys=False, default_flow_style=False, width=1000)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not existing:
        existing = HEADER
    elif not existing.endswith("\n"):
        existing += "\n"
    path.write_text(f"{existing}\n{block}", encoding="utf-8")
    return True
