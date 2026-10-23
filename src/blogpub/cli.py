"""Command line interface: init, providers, new, drafts, preview, publish."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__, gitops, images as imglib, safety, timeline
from .blog import Blog, BlogError, split_front_matter
from .config import ConfigError, load_config
from .generate import GenerationError, build_user_prompt, expansion_warning, generate
from .providers import PRESETS, ProviderError, make_provider
from .render import render_files

EXAMPLE_CONFIG = """\
# blogpub configuration. Copy to your blog folder as blogpub.yml.
# API keys are NEVER stored here: export them as environment variables (see `blogpub providers`).

blog_dir: .                 # the Hexo project (folder with _config.yml and source/)
languages: [zh, en]         # first = language of your notes; use [en] for a single-language blog

provider: openai            # openai | anthropic | deepseek | kimi | qwen | ollama | custom
# model: gpt-4o             # override the preset's default model name
# base_url: https://...     # only needed for `custom`, or a proxy
# vision: true              # send your images to the model (only for models that can see)

# style_notes: |
#   Write in a relaxed first-person tone. Explain why, not only how.
# style_file: style.md

# commit_message: "New post: {title}"
# timeline_notes: source/_data/timeline-notes.yml   # also record each published post here (a build timeline)
# timeline_tags: [content]
# slug_suffix: "-{lang}"    # file name suffix for the non-primary language versions
# front_matter:             # fields used to pair the translations of one post
#   lang_field: post_lang
#   translation_field: translation
# images:
#   dir: images/posts       # under source/
#   max_width: 1600
#   quality: 85
"""


def die(msg: str, code: int = 1) -> "SystemExit":
    print(f"error: {msg}", file=sys.stderr)
    return SystemExit(code)


def confirm(question: str, yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        raise die("this needs your confirmation but the terminal is not interactive; pass --yes to confirm automatically")
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def show_findings(findings: List[safety.Finding], header: str) -> None:
    print(header)
    for f in findings:
        print(f"  {f}")


# ---------------------------------------------------------------- commands
def cmd_providers(args: argparse.Namespace) -> int:
    print(f"{'name':<10} {'key variable':<18} {'default model':<18} vision  description")
    for name, p in PRESETS.items():
        print(f"{name:<10} {str(p.get('api_key_env') or '-'):<18} {str(p.get('model') or '-'):<18} "
              f"{'yes' if p.get('vision') else 'no':<7} {p['label']}")
    print("\nSet the key in your shell, for example:  export OPENAI_API_KEY='...'")
    print("Model names change often; set `model:` in blogpub.yml (or --model) to the one you want.")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.dir).resolve() / "blogpub.yml"
    if target.exists():
        raise die(f"{target} already exists")
    target.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    print(f"Created {target}\nEdit `provider` and `languages`, then export your API key and run `blogpub new notes.md`.")
    return 0


def _blog(cfg: Dict[str, Any]) -> Blog:
    """Open the blog, with a helpful hint when the command was run in the wrong folder."""
    try:
        return Blog(cfg["blog_dir"])
    except BlogError as e:
        if cfg.get("_config_file"):
            raise
        raise BlogError(
            f"{e}\nNo blogpub.yml was found here or in any parent folder, so the current folder was used.\n"
            "Run blogpub inside your blog folder (cd into it first), or pass --blog /path/to/your/blog.")


def _load(args: argparse.Namespace) -> Dict[str, Any]:
    cfg = load_config(getattr(args, "config", None))
    for key in ("provider", "model", "base_url"):
        if getattr(args, key, None):
            cfg[key] = getattr(args, key)
    if getattr(args, "languages", None):
        cfg["languages"] = [x.strip() for x in args.languages.split(",") if x.strip()]
    if getattr(args, "blog", None):
        cfg["blog_dir"] = str(Path(args.blog).expanduser().resolve())
    return cfg


def _read_notes(args: argparse.Namespace) -> str:
    if args.text:
        return args.text
    if args.notes == "-":
        return sys.stdin.read()
    if not args.notes:
        raise die("give a notes file, '-' for stdin, or --text '...'")
    path = Path(args.notes).expanduser()
    if not path.is_file():
        raise die(f"notes file not found: {args.notes}")
    return path.read_text(encoding="utf-8")


def cmd_new(args: argparse.Namespace) -> int:
    cfg = _load(args)
    blog = _blog(cfg)
    languages: List[str] = cfg["languages"]
    notes = _read_notes(args)
    if len(notes.strip()) < 20:
        raise die("the notes are too short to write a post from")

    # 1) Privacy: look at the notes before they leave this computer.
    findings = safety.scan(notes)
    if findings:
        show_findings(findings, "Possible sensitive data in your notes (they would be sent to the model provider):")
        if safety.worst(findings) == safety.BLOCK and not args.allow_secrets:
            raise die("secrets found in the notes; remove them, or pass --allow-secrets if you are sure")
        if not confirm("Send the notes anyway?", args.yes):
            print("Cancelled.")
            return 1

    provider = make_provider(cfg)
    image_files = imglib.collect(args.images or [])
    tmp = Path(tempfile.mkdtemp(prefix="blogpub-"))
    try:
        processed = imglib.process(image_files, tmp, cfg) if image_files else []
        names = [p.name for p in processed]
        send_images = [p.thumb for p in processed] if provider.vision else []
        if processed and not provider.vision:
            print(f"Note: {provider.name} is not set up for vision, so the images are listed by file name only. "
                  "Describe them in your notes (e.g. 'build.png shows the green check') so they are placed well.")

        taxonomy = blog.taxonomy_by_language(cfg["front_matter"]["lang_field"], languages)
        style = cfg.get("style_notes") or ""
        if cfg.get("style_file"):
            style += "\n" + Path(cfg["style_file"]).expanduser().read_text(encoding="utf-8")
        prompt = build_user_prompt(
            notes, languages, names, taxonomy, blog.recent_titles(int(cfg["context_posts"])), style,
            args.title, args.category, [t.strip() for t in args.tags.split(",")] if args.tags else None)

        print(f"Sending {len(notes)} characters of notes and {len(send_images)} image(s) to "
              f"{provider.name} ({provider.model}) ...")
        spec = generate(provider, prompt, languages, names, send_images)
        if args.slug:
            if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", args.slug):
                raise die("--slug may only contain lowercase letters, digits and single hyphens, e.g. my-first-post")
            spec.slug = args.slug

        taken = blog.slug_taken(spec.slug)
        if taken:
            raise die(f"a post or draft named '{spec.slug}' already exists ({taken.name}); use --slug to choose another")

        warn = expansion_warning(notes, spec.posts[languages[0]]["body"])
        if warn:
            spec.warnings.append(warn)
        files = render_files(spec, languages, cfg)
        todos = sum(text.count("TODO") for text in files.values())
        if todos:
            spec.warnings.append(f"the model left {todos} TODO marker(s) where it lacked information; search for TODO in the draft and fill them in or remove them")
        final = "\n".join(files.values())
        post_findings = safety.scan(final)

        print(f"\nSlug: {spec.slug}")
        for lang in languages:
            print(f"  [{lang}] {spec.posts[lang]['title']}   "
                  f"(category: {', '.join(spec.categories.get(lang, [])) or '-'}; tags: {', '.join(spec.tags.get(lang, [])) or '-'})")
        for w in spec.warnings:
            print(f"  warning: {w}")
        if post_findings:
            show_findings(post_findings, "Check these in the generated post:")

        if args.dry_run:
            print("\n--dry-run: nothing was written. Generated files:")
            for name, content in files.items():
                print(f"\n===== {name} =====\n{content}")
            return 0

        written = blog.write_drafts(files)
        if processed:
            dest = blog.images_dir(cfg["images"]["dir"], spec.slug)
            dest.mkdir(parents=True, exist_ok=True)
            for p in processed:
                shutil.move(str(p.path), str(dest / p.name))
        print("\nDrafts written:")
        for w in written:
            print(f"  {w.relative_to(blog.root)}")
        print(f"\nNext:\n  blogpub preview            # read it in the browser (hexo server --drafts)\n"
              f"  blogpub publish {spec.slug}    # commit and push when you are happy")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_drafts(args: argparse.Namespace) -> int:
    cfg = _load(args)
    blog = _blog(cfg)
    drafts = blog.drafts()
    if not drafts:
        print("No drafts.")
        return 0
    for d in drafts:
        fm, _ = split_front_matter(d.read_text(encoding="utf-8"))
        print(f"{d.stem:<40} {fm.get('title', '')}")
    return 0


def cmd_preview(args: argparse.Namespace) -> int:
    cfg = _load(args)
    blog = _blog(cfg)
    local = blog.root / "node_modules" / ".bin" / "hexo"
    cmd = [str(local)] if local.exists() else ["npx", "hexo"]
    cmd += ["server", "--drafts", "-p", str(args.port)]
    print(f"Starting: {' '.join(cmd)}  (Ctrl-C to stop)\nOpen http://localhost:{args.port}/ — drafts appear in the post list.")
    try:
        return subprocess.call(cmd, cwd=blog.root)
    except KeyboardInterrupt:
        return 0
    except FileNotFoundError:
        raise die("could not run hexo; run `npm install` in the blog folder first")


def cmd_publish(args: argparse.Namespace) -> int:
    cfg = _load(args)
    blog = _blog(cfg)
    fm_cfg = cfg["front_matter"]
    group = blog.draft_group(args.slug, fm_cfg["translation_field"])

    texts = {d.name: d.read_text(encoding="utf-8") for d in group}
    findings = safety.scan("\n".join(texts.values()))
    if findings:
        show_findings(findings, "Check before publishing:")
        if safety.worst(findings) == safety.BLOCK and not args.force:
            raise die("secrets found in the post; fix them in the draft, or pass --force if you are sure")

    titles = []
    for d in group:
        fm, _ = split_front_matter(texts[d.name])
        titles.append(str(fm.get("title", d.stem)))
    primary_title = titles[0]
    for d, t in zip(group, titles):
        if d.stem == args.slug:
            primary_title = t
    message = args.message or cfg["commit_message"].format(title=primary_title)

    image_dir = blog.images_dir(cfg["images"]["dir"], args.slug)
    mine = [str((blog.posts_dir / d.name).relative_to(blog.root)) for d in group]
    if image_dir.is_dir():
        mine.append(str(image_dir.relative_to(blog.root)))
    notes_path = (blog.root / str(cfg["timeline_notes"])) if cfg.get("timeline_notes") else None
    notes_rel = str(notes_path.relative_to(blog.root)) if notes_path else None
    # Catch problems before anything is moved.
    if not args.no_commit:
        if not gitops.is_repo(blog.root):
            raise die(f"{blog.root} is not a git repository (use --no-commit to only move the files)")
        foreign = gitops.other_staged_files(blog.root, mine + ([notes_rel] if notes_rel else []))
        if foreign:
            raise die("these files are already staged and would be included:\n  " + "\n  ".join(foreign))

    print("About to publish:")
    for d, t in zip(group, titles):
        print(f"  {d.name}: {t}")
    print(f"Commit message: {message}")
    if notes_rel:
        print(f"Timeline: add a note for post:{args.slug} to {notes_rel}")
    print("Then: " + ("only move the drafts" if args.no_commit else ("commit (no push)" if args.no_push else "commit and push")))
    if not confirm("Continue?", args.yes):
        print("Cancelled.")
        return 1

    # Collect what the timeline entry needs before the drafts are moved.
    entry = None
    if notes_path:
        titles: Dict[str, str] = {}
        bodies: Dict[str, str] = {}
        for d in group:
            fm, body = split_front_matter(texts[d.name])
            lang = str(fm.get(fm_cfg["lang_field"]) or cfg["languages"][0])
            titles[lang] = str(fm.get("title", d.stem))
            bodies[lang] = body
        entry = timeline.build_entry(titles, bodies, cfg)

    moved = blog.publish(group)
    print("Moved to source/_posts: " + ", ".join(m.name for m in moved))
    if entry and notes_path:
        try:
            if timeline.append_note(notes_path, args.slug, entry):
                mine.append(notes_rel)
                print(f"Timeline note added: {notes_rel} (post:{args.slug})")
            else:
                print(f"Timeline note for post:{args.slug} already exists, left unchanged.")
        except Exception as e:  # never lose a publish over the timeline
            print(f"warning: could not update the timeline notes ({e}); the post itself is published.")
    if args.no_commit:
        return 0
    try:
        short = gitops.commit_and_push(blog.root, mine, message, push=not args.no_push)
    except gitops.GitError as e:
        raise die(f"{e}\nThe posts are in source/_posts but not (fully) committed; fix the problem and commit them yourself.")
    print(f"Committed {short}" + ("" if args.no_push else " and pushed."))
    url = gitops.actions_url(blog.root)
    if url and not args.no_push:
        print(f"Your site rebuilds in a minute or two: {url}")
    return 0


# ------------------------------------------------------------------ parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="blogpub", description="Notes + images -> polished Hexo post -> one-command publish.")
    p.add_argument("--version", action="version", version=f"blogpub {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--config", help="path to blogpub.yml (default: ./blogpub.yml)")
        sp.add_argument("--blog", help="path to the Hexo blog (overrides blog_dir)")

    s = sub.add_parser("providers", help="list supported LLM providers"); s.set_defaults(func=cmd_providers)
    s = sub.add_parser("init", help="create a blogpub.yml here"); s.add_argument("--dir", default=".", help="folder to create blogpub.yml in (default: current folder)"); s.set_defaults(func=cmd_init)

    s = sub.add_parser("new", help="write a draft from your notes and images"); common(s)
    s.add_argument("notes", nargs="?", help="notes file, or - for stdin")
    s.add_argument("--text", help="notes given directly on the command line")
    s.add_argument("-i", "--images", nargs="+", metavar="PATH", help="image files or folders")
    s.add_argument("--title", help="title hint"); s.add_argument("--category", help="category to use")
    s.add_argument("--tags", help="comma-separated tags to include"); s.add_argument("--slug", help="force the URL slug")
    s.add_argument("--provider", choices=list(PRESETS), help="LLM provider, overrides blogpub.yml (see `blogpub providers`)")
    s.add_argument("--model", help="model name, overrides the provider default")
    s.add_argument("--base-url", dest="base_url", help="API address, for `custom` or a proxy")
    s.add_argument("--languages", help="override languages, e.g. zh,en or en")
    s.add_argument("--dry-run", action="store_true", help="show the result without writing anything")
    s.add_argument("--allow-secrets", action="store_true", help="send notes even if they look like they hold secrets")
    s.add_argument("-y", "--yes", action="store_true", help="answer yes to confirmations")
    s.set_defaults(func=cmd_new)

    s = sub.add_parser("drafts", help="list drafts"); common(s); s.set_defaults(func=cmd_drafts)
    s = sub.add_parser("preview", help="run hexo server with drafts"); common(s)
    s.add_argument("--port", type=int, default=4000, help="port for hexo server (default: 4000)"); s.set_defaults(func=cmd_preview)

    s = sub.add_parser("publish", help="move a draft to _posts, commit and push"); common(s)
    s.add_argument("slug", help="draft slug (see `blogpub drafts`)")
    s.add_argument("-m", "--message", help="commit message")
    s.add_argument("--no-push", action="store_true", help="commit but do not push")
    s.add_argument("--no-commit", action="store_true", help="only move the drafts into _posts; no git at all")
    s.add_argument("--force", action="store_true", help="publish even if secrets were detected")
    s.add_argument("-y", "--yes", action="store_true", help="skip the confirmation question")
    s.set_defaults(func=cmd_publish)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (ConfigError, BlogError, ProviderError, GenerationError, imglib.ImageError, gitops.GitError) as e:
        raise die(str(e))


if __name__ == "__main__":
    sys.exit(main())
