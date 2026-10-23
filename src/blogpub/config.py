"""Configuration: defaults, blogpub.yml loading, and validation."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

CONFIG_NAMES = ("blogpub.yml", ".blogpub.yml")

DEFAULTS: Dict[str, Any] = {
    # Path to the Hexo blog (the folder that contains _config.yml and source/).
    "blog_dir": ".",
    # Languages to write. The first one is the primary language of your notes.
    # Use a single language (e.g. ["en"]) if your blog is not bilingual.
    "languages": ["zh", "en"],
    # LLM: a preset name (see `blogpub providers`). The API key is read from an
    # environment variable only, never from a file.
    "provider": "openai",
    "model": None,  # None -> preset default
    "base_url": None,  # None -> preset default
    "api_key_env": None,  # None -> preset default
    "vision": None,  # None -> preset default; whether images are sent to the model
    "images": {
        "dir": "images/posts",  # under source/
        "max_width": 1600,
        "quality": 85,
        "send_max_side": 1024,  # size of the copies sent to a vision model
    },
    # Names of the front-matter fields used to pair translations of one post.
    "front_matter": {"lang_field": "post_lang", "translation_field": "translation"},
    "slug_suffix": "-{lang}",  # added to the slug of non-primary languages
    "site_root": "/",  # Hexo `root`, used for image URLs
    "commit_message": "New post: {title}",
    "style_notes": "",  # extra writing instructions for the model
    "style_file": None,  # or a path to a file with writing instructions
    "context_posts": 5,  # how many recent post titles to show the model
    # Optional: also record every published post in the blog's build-timeline notes file
    # (path relative to the blog, e.g. source/_data/timeline-notes.yml). None = off.
    "timeline_notes": None,
    "timeline_tags": ["content"],
    "timeline_title_prefix": {"zh": "发布新文章：", "en": "New post: "},
    "timeout": 180,
}


class ConfigError(Exception):
    pass


def _merge(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def find_config(start: Path) -> Optional[Path]:
    """Look for blogpub.yml in `start` and then its parent folders (like git does), so the
    command also works from a sub-folder of the blog."""
    for folder in [start, *start.parents]:
        for name in CONFIG_NAMES:
            candidate = folder / name
            if candidate.is_file():
                return candidate
    return None


def _reject_secrets(data: Any, where: str = "") -> None:
    """A config file must never contain an API key."""
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in {"api_key", "apikey", "key", "token", "secret"}:
                raise ConfigError(
                    f"'{where}{key}' looks like a secret. Put your API key in an environment "
                    "variable (see `blogpub providers`) and never in a config file."
                )
            _reject_secrets(value, f"{where}{key}.")


def load_config(path: Optional[str] = None, cwd: Optional[Path] = None) -> Dict[str, Any]:
    cwd = cwd or Path.cwd()
    file = Path(path) if path else find_config(cwd)
    cfg = copy.deepcopy(DEFAULTS)
    if file:
        if not file.is_file():
            raise ConfigError(f"Config file not found: {file}")
        try:
            data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            raise ConfigError(f"Cannot parse {file}: {e}")
        if not isinstance(data, dict):
            raise ConfigError(f"{file} must contain a mapping at the top level")
        _reject_secrets(data)
        cfg = _merge(cfg, data)
        cfg["_config_file"] = str(file.resolve())
        base = file.resolve().parent
    else:
        base = cwd
    # A relative blog_dir is relative to the config file (or the current directory).
    blog = Path(os.path.expanduser(str(cfg["blog_dir"])))
    cfg["blog_dir"] = str(blog if blog.is_absolute() else (base / blog).resolve())

    langs = cfg["languages"]
    if not isinstance(langs, list) or not langs or not all(isinstance(x, str) and x for x in langs):
        raise ConfigError("'languages' must be a non-empty list such as [zh, en]")
    if len(set(langs)) != len(langs):
        raise ConfigError("'languages' contains duplicates")
    return cfg
