"""Prompt building, calling the model, and validating what comes back."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .providers import Image, Provider

SYSTEM_PROMPT = """You are an editor for a personal technical blog. The author gives you rough notes \
(and sometimes images). Turn them into a clear, well-structured blog post that sounds like the author.

Rules:
- Stay faithful to the notes. Never invent facts, numbers, commands, versions, results, reasons, opinions or experiences. \
If something important is missing, leave it out or add an HTML comment such as <!-- TODO: add the exact version -->.
- Length must be proportional to the notes. If the notes are only a sentence or two, write one or two short paragraphs. \
Do NOT pad the post with tutorial steps, commands, motivations, background or conclusions that the notes do not contain, \
even if they seem obvious or typical. A short, accurate post is better than a long, partly invented one.
- Keep code, commands, file paths and config snippets exactly as given, inside fenced code blocks with a language tag.
- Never output secrets. If the notes contain a key, token, password, private IP or personal address, \
replace it with a clear placeholder such as <your-api-key> and mention nothing else about it.
- Structure: a short introduction paragraph (it becomes the excerpt), then sections with `##` headings \
(`###` for subsections). Do NOT write a top-level `#` title or front matter inside the body.
- Explain the "why" where the notes do, and keep pitfalls and fixes. Prefer concrete, practical wording over filler.
- Images: every provided image must appear in the body exactly once, written as `![alt text](IMG:filename)` \
using the exact file name from the IMAGES list, placed where it fits the story. Write alt text in the language of that version. \
Never reference any image that is not in the list.
- Categories: at most one, reuse an existing category of the SAME language version when it fits (names are listed per language). Tags: 2 to 6, reuse existing tags of the same language when they fit.
- If several languages are requested, write each version natively (not word-for-word) but keep the same facts, \
structure and code. All versions must be complete.
- `slug` is a short lowercase ASCII, hyphen-separated identifier for the URL.

Reply with ONE JSON object and nothing else, in exactly this shape:
{
  "slug": "short-ascii-slug",
  "categories": {"<lang>": ["Category"]},
  "tags": {"<lang>": ["tag1", "tag2"]},
  "posts": {"<lang>": {"title": "...", "body": "markdown body"}}
}
Use the language codes given in LANGUAGES as the keys, for every one of them."""


class GenerationError(Exception):
    pass


@dataclass
class PostSpec:
    slug: str
    categories: Dict[str, List[str]]
    tags: Dict[str, List[str]]
    posts: Dict[str, Dict[str, str]]  # lang -> {"title", "body"}
    warnings: List[str] = field(default_factory=list)


_IMG_REF = re.compile(r"!\[[^\]]*\]\(IMG:([^)\s]+)\)")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s[:60].strip("-")


def build_user_prompt(notes: str, languages: List[str], image_names: List[str],
                      taxonomy: Dict[str, Tuple[List[str], List[str]]], recent_titles: List[str], style_notes: str,
                      title_hint: Optional[str], category_hint: Optional[str],
                      tags_hint: Optional[List[str]]) -> str:
    lines = [f"LANGUAGES: {', '.join(languages)}",
             f"PRIMARY LANGUAGE: {languages[0]} (the notes are written in this language unless they clearly are not)"]
    for lang in languages:
        cats, tags = taxonomy.get(lang, ([], []))
        lines.append(f"EXISTING CATEGORIES [{lang}]: {', '.join(cats) or '(none yet)'}")
        lines.append(f"EXISTING TAGS [{lang}]: {', '.join(tags) or '(none yet)'}")
    if recent_titles:
        lines.append("RECENT POSTS (for tone, and to avoid repeating them):")
        lines += [f"- {t}" for t in recent_titles]
    if style_notes.strip():
        lines.append(f"STYLE NOTES FROM THE AUTHOR:\n{style_notes.strip()}")
    if title_hint:
        lines.append(f"TITLE HINT (use or improve it): {title_hint}")
    if category_hint:
        lines.append(f"CATEGORY (use this): {category_hint}")
    if tags_hint:
        lines.append(f"TAGS (include these): {', '.join(tags_hint)}")
    if image_names:
        lines.append("<<<IMAGES\n" + "\n".join(f"- {n}" for n in image_names) + "\nIMAGES>>>")
    else:
        lines.append("There are no images.")
    lines.append(f"<<<NOTES\n{notes.strip()}\nNOTES>>>")
    lines.append("Reply with the JSON object only.")
    return "\n".join(lines)


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise GenerationError("the reply contains no JSON object")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise GenerationError(f"the reply is not valid JSON ({e})")
    if not isinstance(data, dict):
        raise GenerationError("the JSON reply is not an object")
    return data


def _per_language(value: Any, languages: List[str]) -> Dict[str, List[str]]:
    """Accept {lang: [..]} or a plain list that applies to every language."""
    def clean(items: Any) -> List[str]:
        if isinstance(items, str):
            items = [items]
        return [str(i).strip() for i in (items or []) if str(i).strip()]
    if isinstance(value, dict):
        return {lang: clean(value.get(lang)) for lang in languages}
    return {lang: clean(value) for lang in languages}


def validate(data: Dict[str, Any], languages: List[str], image_names: List[str]) -> PostSpec:
    errors: List[str] = []
    warnings: List[str] = []

    posts_raw = data.get("posts")
    if not isinstance(posts_raw, dict):
        raise GenerationError("missing the 'posts' object")
    posts: Dict[str, Dict[str, str]] = {}
    for lang in languages:
        item = posts_raw.get(lang)
        if not isinstance(item, dict):
            errors.append(f"posts.{lang} is missing")
            continue
        title, body = str(item.get("title", "")).strip(), str(item.get("body", "")).strip()
        if not title:
            errors.append(f"posts.{lang}.title is empty")
        if len(body) < 20:
            errors.append(f"posts.{lang}.body is empty or far too short")
        posts[lang] = {"title": title, "body": body}

    known = set(image_names)
    for lang, item in posts.items():
        refs = _IMG_REF.findall(item["body"])
        unknown = sorted({r for r in refs if r not in known})
        if unknown:
            errors.append(f"posts.{lang} references images that were not provided: {', '.join(unknown)}")
        missing = [n for n in image_names if n not in refs]
        if missing:
            # Do not fail: append them so no image is silently lost, and tell the author.
            item["body"] += "\n\n" + "\n\n".join(f"![{n}](IMG:{n})" for n in missing)
            warnings.append(f"[{lang}] the model did not place: {', '.join(missing)} (appended at the end)")

    if errors:
        raise GenerationError("; ".join(errors))

    slug = str(data.get("slug", "")).strip().lower()
    if not _SLUG.match(slug):
        fixed = slugify(slug) or slugify(posts[languages[0]]["title"])
        if fixed != slug:
            warnings.append(f"slug '{slug}' was not a clean ASCII slug, using '{fixed or 'post'}'")
        slug = fixed or "post"
    return PostSpec(
        slug=slug,
        categories=_per_language(data.get("categories"), languages),
        tags=_per_language(data.get("tags"), languages),
        posts=posts, warnings=warnings,
    )


def generate(provider: Provider, user_prompt: str, languages: List[str], image_names: List[str],
             images: Optional[List[Image]] = None, retries: int = 1) -> PostSpec:
    prompt = user_prompt
    last = ""
    for attempt in range(retries + 1):
        reply = provider.complete(SYSTEM_PROMPT, prompt, images)
        try:
            return validate(_extract_json(reply), languages, image_names)
        except GenerationError as e:
            last = str(e)
            prompt = (user_prompt + f"\n\nYour previous reply was rejected: {last}.\n"
                      "Reply again with ONLY the corrected JSON object.")
    raise GenerationError(f"The model's reply was unusable after {retries + 1} attempts: {last}")


def expansion_warning(notes: str, body: str) -> Optional[str]:
    """The model is told not to invent things, but a very short note still tempts it to pad the post.
    A body much longer than the notes is the tell-tale sign, so ask the author to check it."""
    n, b = len(notes.strip()), len(body.strip())
    if b > 500 and b > 4 * n:
        return (f"the post is about {b // max(n, 1)}x longer than your notes ({b} vs {n} characters), so the model "
                "may have added details you did not write. Read it carefully, and give more detailed notes next time.")
    return None
