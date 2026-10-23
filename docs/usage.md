# blogpub command reference

**English** · [中文](usage.zh.md)

## Contents

1. [Conventions](#1-conventions)
2. [The whole workflow](#2-the-whole-workflow)
3. [Commands](#3-commands): `providers` · `init` · `new` · `drafts` · `preview` · `publish`
4. [Configuration: blogpub.yml](#4-configuration-blogpubyml)
5. [Environment variables](#5-environment-variables)
6. [Privacy and safety checks](#6-privacy-and-safety-checks)
7. [Recipes](#7-recipes)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Conventions

**Run it inside your blog folder.** blogpub looks for `blogpub.yml` in the current folder and then in each parent folder (like git), so it also works from a sub-folder of the blog. If no config file is found, the current folder is treated as the blog, and you get an error unless it is a Hexo project (`_config.yml` and `source/`). To run it from elsewhere use `--blog /path/to/blog`.

**Precedence** (high to low): command line options, `blogpub.yml`, built-in defaults.

**API keys come from environment variables only.** A config file containing `api_key`, `token`, `secret` and the like is rejected.

Every command has `--help`, for example `blogpub new --help`.

---

## 2. The whole workflow

```
blogpub init          once: create blogpub.yml
      |
blogpub new           notes + images -> draft(s) in source/_drafts/
      |                 - scans the notes for secrets first
      |                 - shrinks images and strips GPS and other metadata
      |                 - calls the model, validates, writes the drafts
blogpub preview       read it in the browser (hexo server --drafts)
      |                 not happy: edit the .md in source/_drafts/, or improve the notes and run `new` again
blogpub publish       draft -> source/_posts/, commit, push
                        - scans the finished post again
                        - stages only the files it created
                        - optionally adds an entry to the blog's build timeline
```

---

## 3. Commands

### `blogpub providers`

Lists the supported LLM providers: name, environment variable, default model, whether it can see images. No options. The default model is only a starting point; override it with `model:`.

### `blogpub init`

Writes a commented `blogpub.yml` in the current folder. Refuses to overwrite an existing one.

| Option | Meaning |
|---|---|
| `--dir DIR` | create the file in DIR instead of the current folder |

### `blogpub new`: draft from notes

```
blogpub new [NOTES_FILE | -] [options]
```

Give the notes as a file, as `-` (read standard input), or with `--text`.

| Option | Meaning |
|---|---|
| `NOTES_FILE` | path to the notes; `-` reads standard input |
| `--text TEXT` | notes given directly on the command line |
| `-i, --images PATH...` | image files or folders (png, jpg, webp, gif, heic, ...) |
| `--title TITLE` | title hint (the model may polish it) |
| `--category NAME` | category to use |
| `--tags a,b` | comma-separated tags to include |
| `--slug NAME` | force the URL name and file name; lowercase letters, digits and single hyphens only |
| `--provider NAME` | provider for this run, overrides the config |
| `--model NAME` | model for this run |
| `--base-url URL` | API address, for `custom` or a proxy |
| `--languages zh,en` | languages for this run; the first is the language of your notes |
| `--dry-run` | show the result and write nothing (it still calls the model once) |
| `--allow-secrets` | send the notes even if they look like they contain secrets (not recommended) |
| `-y, --yes` | answer yes to every confirmation |
| `--config PATH` | config file (default: found from the current folder upward) |
| `--blog PATH` | the blog folder, overrides `blog_dir` |

What it does, in order: scan the notes; process images (max width 1600, metadata stripped, renamed `01-name.jpg`); send notes, image names, existing categories and tags per language, and recent titles to the model (plus downscaled images when the model can see); validate the reply and retry once if it is malformed; check the slug is free; scan the result; write `source/_drafts/<slug>.md` (and `<slug>-en.md`) and `source/images/posts/<slug>/`; print warnings (images the model forgot, `TODO` markers, a post far longer than the notes).

### `blogpub drafts`

Lists drafts with their titles. Options: `--config`, `--blog`.

### `blogpub preview`

Runs the local Hexo server **with drafts**; stop it with Ctrl-C. Run `npm install` in the blog first.

| Option | Meaning |
|---|---|
| `--port PORT` | port (default 4000) |
| `--config`, `--blog` | as above |

### `blogpub publish`: publish

```
blogpub publish <slug> [options]
```

`slug` is the draft name from `blogpub drafts`. Translations linked by the `translation` field are published together.

| Option | Meaning |
|---|---|
| `slug` | the draft to publish |
| `-m, --message TEXT` | commit message, overrides `commit_message` |
| `--no-push` | commit but do not push |
| `--no-commit` | only move the drafts to `source/_posts/`; no git (the timeline notes file is still modified if configured, commit it yourself) |
| `--force` | publish even if secrets were detected (not recommended) |
| `-y, --yes` | skip the confirmation question |
| `--config`, `--blog` | as above |

What it does, in order: scan the finished post (secrets block it unless `--force`); stop if other files are already staged; show what it will do and ask; move the drafts to `source/_posts/` with the current time as the date; append a `post:<slug>` entry to the timeline notes if `timeline_notes` is set; `git add` only its own files (posts, images, timeline notes); commit; push; print your GitHub Actions page.

---

## 4. Configuration: blogpub.yml

| Key | Default | Meaning |
|---|---|---|
| `blog_dir` | `.` | the Hexo blog; a relative path is relative to the config file |
| `languages` | `[zh, en]` | languages to write, the first is your notes' language; one language writes no pairing fields |
| `provider` | `openai` | openai, anthropic, deepseek, kimi, qwen, ollama, custom |
| `model` | provider default | model name |
| `base_url` | provider default | API address |
| `api_key_env` | provider default | environment variable that holds the key |
| `vision` | provider default | send images to the model (the model must support it) |
| `images.dir` | `images/posts` | folder under `source/` for images |
| `images.max_width` | `1600` | maximum width in pixels, never upscaled |
| `images.quality` | `85` | JPEG quality |
| `images.send_max_side` | `1024` | longest side of the copies sent to the model |
| `front_matter.lang_field` | `post_lang` | front-matter field with the post's language |
| `front_matter.translation_field` | `translation` | field pointing to the other language version |
| `slug_suffix` | `-{lang}` | file name suffix of non-primary languages |
| `site_root` | `/` | Hexo `root`, used for image URLs |
| `commit_message` | `New post: {title}` | commit message |
| `style_notes` | empty | writing instructions for the model |
| `style_file` | empty | path to a file with writing instructions |
| `context_posts` | `5` | how many recent titles the model sees |
| `timeline_notes` | empty (off) | path of the timeline notes file to append to |
| `timeline_tags` | `[content]` | tags of the timeline entry |
| `timeline_title_prefix` | `zh: 发布新文章：`, `en: New post: ` | title prefix per language |
| `timeout` | `180` | request timeout in seconds |

---

## 5. Environment variables

| Variable | Used by |
|---|---|
| `OPENAI_API_KEY` | `openai` |
| `ANTHROPIC_API_KEY` | `anthropic` |
| `DEEPSEEK_API_KEY` | `deepseek` |
| `MOONSHOT_API_KEY` | `kimi` |
| `DASHSCOPE_API_KEY` | `qwen` |
| `LLM_API_KEY` | `custom` |
| `https_proxy` / `HTTPS_PROXY` | set when you need a proxy to reach OpenAI or Claude |

---

## 6. Privacy and safety checks

The notes are scanned **before sending** and the finished post **before publishing**, with the same rules.

| Level | Detected | Effect |
|---|---|---|
| block | private keys, `sk-...` API keys, GitHub tokens, AWS keys, Slack tokens, Google API keys | refused (only `--allow-secrets` / `--force` override) |
| warn | `password=...` assignments, IP addresses, e-mail addresses, mainland China mobile numbers, `ssh user@host`, home directory paths | shown, and you are asked to continue |

`127.0.0.1`, documentation IPs (`203.0.113.x`, ...) and `example.com` addresses are ignored. Findings are masked and never echo a full secret.

---

## 7. Recipes

English post only:

```bash
blogpub new notes.md --languages en
```

Try another provider without touching the config:

```bash
blogpub new notes.md --provider kimi --model moonshot-v1-32k
```

Look first, write nothing:

```bash
blogpub new notes.md --dry-run
```

Set title, category and tags:

```bash
blogpub new notes.md --title "Building my blog" --category "Dev Notes" --tags Hexo,SSH
```

With images:

```bash
blogpub new notes.md -i ~/Desktop/shots/
```

Publish but inspect the commit before pushing:

```bash
blogpub publish my-post --no-push
```

---

## 8. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `does not look like a Hexo blog` | not run inside the blog: `cd` into it, or pass `--blog` |
| `Environment variable ... is not set` | the key is not exported, or the name does not match the provider (section 5) |
| `HTTP 401` | wrong or revoked key |
| `HTTP 404` / model not found | the default model name is outdated: set `model:` |
| timeout or connection error | reaching OpenAI or Claude may need a proxy: set `https_proxy` |
| `secrets found in the notes` | remove them and run again |
| `already exists` | a post or draft with that name exists: use `--slug` |
| `already staged` | other files are staged: commit them or `git restore --staged FILE` |
| "the post is much longer than your notes" | the notes were too thin, the model may have invented details: check carefully or write more specific notes |
| `TODO` in a draft | the model lacked information: fill it in, or better, add the facts to the notes and regenerate |
| `could not run hexo` | run `npm install` in the blog once |
