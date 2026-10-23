# blogpub

**English** · [中文](#中文)

Turn rough notes and images into a polished [Hexo](https://hexo.io) blog post with an LLM, read it in your browser, then publish with one command. Works with **ChatGPT (OpenAI), Claude, DeepSeek, Kimi, Qwen, Ollama** and any OpenAI-compatible API. You bring the API key; blogpub is not tied to any one model.

```
notes.md + images/  ──►  LLM  ──►  draft(s) in source/_drafts  ──►  preview  ──►  commit + push  ──►  your CI deploys
```

## Why

- **Notes in, post out.** Write the facts in whatever shape; the model structures them. It is told never to invent steps, numbers or commands.
- **Bilingual out of the box (optional).** One run can produce, for example, a Chinese and an English version and link them to each other through front matter.
- **Privacy first.** Your notes are scanned for API keys, tokens, private keys, IP addresses, e-mail addresses, phone numbers and home paths *before* anything is sent to a provider, and the finished post is scanned again *before* it is published. Image metadata (EXIF, including GPS location) is stripped.
- **Safe to publish.** Drafts go to Hexo's `_drafts` folder, you preview them with `hexo server --drafts`, and only after you confirm does blogpub move them to `_posts`, stage **only the files it created** and commit. It refuses to run if you have other staged changes.
- **No lock-in.** Plain files in, plain Hexo posts out. The API key lives only in an environment variable and is never written to a file (a config file containing a key is rejected).

## Install

Python 3.9 or newer.

```bash
git clone https://github.com/jizhe-nie/blogpub.git
cd blogpub
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # add  ".[heic]"  to read iPhone HEIC photos everywhere
```

## Quick start

```bash
cd my-hexo-blog
blogpub init                              # writes blogpub.yml, edit provider / languages
export OPENAI_API_KEY='...'               # or ANTHROPIC_API_KEY, DEEPSEEK_API_KEY, MOONSHOT_API_KEY ...

blogpub new notes.md -i screenshots/      # draft from your notes + images
blogpub preview                           # http://localhost:4000, drafts are included
blogpub publish my-post                   # move to _posts, commit, push
```

Try it without any API key: `blogpub new notes.md --provider mock --dry-run`.

## Providers

`blogpub providers` lists them. Set the key in your shell, pick the provider in `blogpub.yml` (or `--provider`).

| provider | key variable | sees images | notes |
|---|---|---|---|
| `openai` | `OPENAI_API_KEY` | yes | ChatGPT models |
| `anthropic` | `ANTHROPIC_API_KEY` | yes | Claude models |
| `deepseek` | `DEEPSEEK_API_KEY` | no | OpenAI-compatible |
| `kimi` | `MOONSHOT_API_KEY` | no | Moonshot AI, OpenAI-compatible |
| `qwen` | `DASHSCOPE_API_KEY` | no | Alibaba DashScope, OpenAI-compatible |
| `ollama` | – | no | local models, no key |
| `custom` | `LLM_API_KEY` | no | set `base_url` and `model` (Gemini's compatibility endpoint, vLLM, a proxy, ...) |

Model names change often, so the defaults are only starting points: set `model:` in `blogpub.yml` or pass `--model`. Set `vision: true` if your model can look at images. If it cannot, describe the images in your notes ("`build.png` shows the green check") and blogpub still places them by file name.

## How images work

Give images with `-i` (files or folders). blogpub shrinks them (default max width 1600px), strips all metadata, names them `01-name.ext`, copies them to `source/images/posts/<slug>/`, and tells the model each file name. The model must reference every image exactly once as `![alt](IMG:file.png)`; blogpub checks that, turns the references into real URLs, and appends any image the model forgot.

## Bilingual posts

With `languages: [zh, en]` the first language is the one your notes are written in. blogpub writes `my-post.md` and `my-post-en.md` and links them with two front-matter fields (`post_lang` and `translation`, configurable under `front_matter:`). What your theme does with those fields is up to you. Use `languages: [en]` for a normal single-language blog; no pairing fields are written then.

## Configuration

See [`blogpub.example.yml`](blogpub.example.yml). Command line flags override the file. Useful extras: `style_notes` / `style_file` (your tone, rules), `commit_message`, `images.max_width`, `slug_suffix`.

## What gets sent to the model provider

Your notes, the list of image file names, your existing category and tag names, the titles of your latest posts (for tone), and, only if `vision` is on, downscaled copies of your images (at most 1024px, no metadata). Nothing else. Read your provider's data policy; use `ollama` to stay fully local.

## Development

```bash
pip install -e ".[dev]" && pytest
```

The test suite includes real HTTP round trips against a local fake server, so provider code is exercised without any API key.

## License

MIT

---

# 中文

[English](#blogpub) · **中文**

把零散的笔记和图片交给大模型，整理成一篇像样的 [Hexo](https://hexo.io) 博客文章，在浏览器里预览，再一条命令发布。支持 **ChatGPT（OpenAI）、Claude、DeepSeek、Kimi、通义千问、Ollama** 以及任何兼容 OpenAI 的接口，API Key 由你自己提供，不绑定任何一家模型。

```
笔记 + 图片  ──►  大模型  ──►  草稿（source/_drafts）  ──►  本地预览  ──►  提交并推送  ──►  你的 CI 自动部署
```

## 特点

- **笔记进，文章出。** 事实怎么随手写都行，模型负责整理结构；它被明确要求不得编造步骤、数字和命令。
- **可选的中英双语。** 一次运行可以同时生成中文和英文两版，并通过 front-matter 互相关联。
- **隐私优先。** 笔记在发给模型**之前**会先扫描 API Key、令牌、私钥、IP 地址、邮箱、手机号和个人目录路径；成品在发布**之前**再扫一遍。图片的 EXIF（包括 GPS 位置）会被清除。
- **发布前可控。** 草稿写进 Hexo 的 `_drafts`，用 `hexo server --drafts` 预览，你确认之后才会移到 `_posts`，并且只暂存它自己生成的文件再提交；如果你有别的已暂存改动，它会拒绝运行。
- **不锁定。** 输入输出都是普通文件。API Key 只放环境变量，绝不写入文件（配置文件里出现密钥会被直接拒绝）。

## 安装

需要 Python 3.9 及以上。

```bash
git clone https://github.com/jizhe-nie/blogpub.git
cd blogpub
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # 想在任何系统上读取 iPhone 的 HEIC 照片，用 ".[heic]"
```

## 快速开始

```bash
cd 你的-hexo-博客
blogpub init                              # 生成 blogpub.yml，按需修改 provider 和 languages
export DEEPSEEK_API_KEY='...'             # 或 OPENAI_API_KEY、ANTHROPIC_API_KEY、MOONSHOT_API_KEY ...

blogpub new notes.md -i screenshots/      # 用笔记和图片生成草稿
blogpub preview                           # 打开 http://localhost:4000 预览（含草稿）
blogpub publish my-post                   # 移到 _posts，提交并推送
```

没有 API Key 也能试用：`blogpub new notes.md --provider mock --dry-run`。

## 支持的模型

用 `blogpub providers` 查看。在终端里设置 Key，在 `blogpub.yml` 里选 `provider`（或用 `--provider`）。

| provider | Key 环境变量 | 能看图 | 说明 |
|---|---|---|---|
| `openai` | `OPENAI_API_KEY` | 是 | ChatGPT 系列模型 |
| `anthropic` | `ANTHROPIC_API_KEY` | 是 | Claude 系列模型 |
| `deepseek` | `DEEPSEEK_API_KEY` | 否 | 兼容 OpenAI 接口 |
| `kimi` | `MOONSHOT_API_KEY` | 否 | 月之暗面，兼容 OpenAI 接口 |
| `qwen` | `DASHSCOPE_API_KEY` | 否 | 阿里云百炼，兼容 OpenAI 接口 |
| `ollama` | – | 否 | 本地模型，不需要 Key |
| `custom` | `LLM_API_KEY` | 否 | 自己填 `base_url` 和 `model`（如 Gemini 兼容接口、vLLM、中转代理等） |

模型名更新很快，默认值只是起点：请在 `blogpub.yml` 里设置 `model:`，或用 `--model`。如果你的模型能看图，设置 `vision: true`；不能看图的话，在笔记里描述一下图片（比如"`build.png` 是构建成功的截图"），工具仍会按文件名把图片放到合适的位置。

## 图片怎么处理

用 `-i` 传入图片（文件或文件夹）。工具会缩小图片（默认最大宽度 1600px）、清除所有元数据、重命名为 `01-name.ext`、复制到 `source/images/posts/<slug>/`，并把每个文件名告诉模型。模型必须用 `![说明](IMG:文件名)` 引用每张图恰好一次；工具会校验这一点，把引用换成真实路径，并把模型漏掉的图片追加到文末。

## 双语文章

设置 `languages: [zh, en]` 时，第一个语言就是你写笔记用的语言。工具会生成 `my-post.md` 和 `my-post-en.md`，并用两个 front-matter 字段（`post_lang` 和 `translation`，可在 `front_matter:` 下改名）把它们关联起来；主题怎么使用这两个字段由你决定。普通单语博客设置 `languages: [en]`（或 `[zh]`）即可，此时不会写入配对字段。

## 会发送给模型服务商的内容

你的笔记、图片的文件名列表、你已有的分类和标签名、最近几篇文章的标题（用于参考语气），以及在开启 `vision` 时缩小后的图片副本（最长边 1024px，不含元数据）。除此之外没有别的。请阅读你所用服务商的数据政策；想完全本地运行，请使用 `ollama`。

## 开发

```bash
pip install -e ".[dev]" && pytest
```

测试里包含对本地假服务器的真实 HTTP 往返，所以不需要任何 API Key 就能验证各家接口的代码。

## 许可证

MIT
