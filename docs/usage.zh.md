# blogpub 命令行使用手册

[English](usage.md) · **中文**

## 目录

1. [基本约定](#1-基本约定)
2. [完整流程一览](#2-完整流程一览)
3. [命令详解](#3-命令详解)：`providers` · `init` · `new` · `drafts` · `preview` · `publish`
4. [配置文件 blogpub.yml](#4-配置文件-blogpubyml)
5. [环境变量](#5-环境变量)
6. [隐私和安全检查](#6-隐私和安全检查)
7. [常用场景](#7-常用场景)
8. [常见问题](#8-常见问题)

---

## 1. 基本约定

**先进入博客目录再运行。** 工具从当前目录开始，**逐级向上**查找 `blogpub.yml`（像 git 一样），所以在博客的子目录里也能用。找不到配置文件时，把当前目录当作博客，如果当前目录不是 Hexo 博客（没有 `_config.yml` 和 `source/`）就会报错。想在别处运行，用 `--blog /博客路径`。

```bash
cd ~/jizhe-nie.github.io
```

**设置的优先级**（高 → 低）：命令行选项 → `blogpub.yml` → 内置默认值。

**API Key 只通过环境变量提供**，不写进任何文件。配置文件里出现 `api_key`、`token`、`secret` 之类的字段会被直接拒绝。

**每个命令都有 `--help`**，例如 `blogpub new --help`。

---

## 2. 完整流程一览

```
blogpub init          一次性：生成 blogpub.yml
      │
blogpub new           笔记 + 图片 → 草稿（source/_drafts/）
      │                 ├─ 先扫描笔记里的密钥，有就拦住
      │                 ├─ 压缩图片、清除 GPS 等元数据
      │                 └─ 调用模型，校验结果，写入草稿
blogpub preview       在浏览器里看（hexo server --drafts）
      │                 不满意：直接编辑 source/_drafts/ 里的 .md，或补充笔记后重新 new
blogpub publish       草稿 → source/_posts/，提交，推送
                        ├─ 再扫描一遍成品
                        ├─ 只暂存自己生成的文件
                        └─ 可选：在建站时间线里追加一条记录
```

---

## 3. 命令详解

### `blogpub providers`

列出支持的模型服务商：名称、需要的环境变量、默认模型、能否看图。

```bash
blogpub providers
```

没有选项。输出里的"默认模型"只是起点，模型名更新很快，请在配置里用 `model:` 覆盖。

### `blogpub init`

在当前目录生成一份带注释的 `blogpub.yml`。文件已存在则报错，不会覆盖。

```bash
blogpub init
```

| 选项 | 说明 |
|---|---|
| `--dir 目录` | 在指定目录而不是当前目录生成 |

### `blogpub new`：从笔记生成草稿

```
blogpub new [笔记文件 | -] [选项]
```

**笔记的三种给法**（三选一）：

```bash
blogpub new notes.md
```

```bash
blogpub new --text "今天把博客搭好了，用 Hexo 加 Redefine 主题。"
```

```bash
cat notes.md | blogpub new -
```

**选项**

| 选项 | 说明 | 例子 |
|---|---|---|
| `笔记文件` | 笔记文件路径；写 `-` 表示从标准输入读 | `notes.md` |
| `--text 文本` | 直接在命令行里给出笔记 | `--text "..."` |
| `-i, --images 路径…` | 图片文件或文件夹，可以给多个；支持 png、jpg、webp、gif、heic 等 | `-i shots/ cover.png` |
| `--title 标题` | 给模型一个标题提示（模型可以润色它） | `--title "我的第一篇"` |
| `--category 分类` | 指定分类 | `--category 开发笔记` |
| `--tags 标签` | 指定标签，逗号分隔 | `--tags Hexo,SSH` |
| `--slug 名字` | 强制指定文章的 URL 名和文件名（只能是小写字母、数字、连字符） | `--slug my-first-post` |
| `--provider 名称` | 本次使用的模型服务商，覆盖配置文件 | `--provider kimi` |
| `--model 模型名` | 本次使用的模型，覆盖默认值 | `--model deepseek-chat` |
| `--base-url 地址` | API 地址，用于 `custom` 或中转代理 | `--base-url http://localhost:8000/v1` |
| `--languages 语言` | 本次要写的语言，逗号分隔，第一个是笔记的语言 | `--languages zh`、`--languages zh,en` |
| `--dry-run` | 试运行：显示结果但**不写任何文件**（仍会调用一次模型） | |
| `--allow-secrets` | 即使笔记里疑似有密钥也照样发送。**不建议使用** | |
| `-y, --yes` | 所有确认都自动回答"是"（用于脚本） | |
| `--config 路径` | 指定配置文件，默认在当前目录及上级目录查找 | `--config ~/my.yml` |
| `--blog 路径` | 指定博客目录，覆盖配置里的 `blog_dir` | `--blog ~/jizhe-nie.github.io` |

**它做了什么**（按顺序）：

1. 扫描笔记里的密钥、IP、邮箱、手机号等。发现**密钥类**会直接拒绝，发现**一般敏感信息**会问你是否继续。
2. 压缩图片（默认最大宽度 1600px），清除 EXIF（含 GPS），重命名成 `01-名字.jpg`。
3. 把笔记、图片文件名、已有的分类和标签（按语言分开）、最近文章标题发给模型。如果所选模型能看图，还会发送缩小后的图片。
4. 校验模型返回的内容；格式不对会自动重试一次。
5. 检查 slug 是否与现有文章冲突；检查成品；写入 `source/_drafts/`，图片放到 `source/images/posts/<slug>/`。
6. 打印警告：模型漏放的图片、留下的 `TODO`、文章远长于笔记（可能编造了细节）。

**生成的文件**（以 `languages: [zh, en]`、slug 为 `my-post` 为例）：

```
source/_drafts/my-post.md          中文版（笔记的语言）
source/_drafts/my-post-en.md       英文版
source/images/posts/my-post/       处理好的图片
```

### `blogpub drafts`

列出所有草稿的名字和标题。

```bash
blogpub drafts
```

| 选项 | 说明 |
|---|---|
| `--config 路径`、`--blog 路径` | 同 `new` |

### `blogpub preview`

在本地启动 Hexo 预览服务，**包含草稿**。按 `Ctrl-C` 结束。需要博客里已经执行过 `npm install`。

```bash
blogpub preview
```

```bash
blogpub preview --port 4001
```

| 选项 | 说明 |
|---|---|
| `--port 端口` | 预览端口，默认 4000 |
| `--config 路径`、`--blog 路径` | 同 `new` |

### `blogpub publish`：发布

```
blogpub publish <slug> [选项]
```

`slug` 是草稿名，用 `blogpub drafts` 查看；中英文两版会一起发布（通过 `translation` 字段自动关联）。

| 选项 | 说明 |
|---|---|
| `slug` | 要发布的草稿，例如 `my-post` |
| `-m, --message 说明` | 本次的提交说明，覆盖配置里的 `commit_message` |
| `--no-push` | 只提交，不推送 |
| `--no-commit` | 只把草稿移到 `source/_posts/`，**完全不用 git**（想自己提交时用）。如果配置了时间线，说明文件也会被改动，记得一起提交 |
| `--force` | 即使成品里检测到密钥也发布。**不建议使用** |
| `-y, --yes` | 跳过确认提问 |
| `--config 路径`、`--blog 路径` | 同 `new` |

**它做了什么**（按顺序）：

1. 再扫描一遍成品；检测到密钥类内容会拒绝（除非 `--force`）。
2. 检查是否有**别的**已暂存文件，有就停下，免得把它们误提交。
3. 列出将要做的事，**等你确认**。
4. 把草稿移到 `source/_posts/`，发布时间写成当前时间。
5. 如果配置了 `timeline_notes`，往时间线说明文件追加一条 `post:<slug>`。
6. 只 `git add` 自己生成的文件（文章、图片、时间线说明），提交，推送。
7. 打印 GitHub Actions 页面地址，博客约一两分钟后更新。

---

## 4. 配置文件 blogpub.yml

由 `blogpub init` 生成。所有项都可省略，用默认值。

| 项 | 默认值 | 说明 |
|---|---|---|
| `blog_dir` | `.` | Hexo 博客目录。相对路径相对于**配置文件所在目录** |
| `languages` | `[zh, en]` | 要写的语言，第一个是笔记的语言。单语博客写 `[zh]` 或 `[en]`，此时不写配对字段 |
| `provider` | `openai` | 模型服务商：openai、anthropic、deepseek、kimi、qwen、ollama、custom |
| `model` | 服务商默认 | 模型名。提示"模型不存在"时在这里改 |
| `base_url` | 服务商默认 | API 地址 |
| `api_key_env` | 服务商默认 | 读取 Key 的环境变量名 |
| `vision` | 服务商默认 | 是否把图片发给模型（模型必须能看图） |
| `images.dir` | `images/posts` | 图片放在 `source/` 下的哪个目录 |
| `images.max_width` | `1600` | 图片最大宽度（像素），不放大 |
| `images.quality` | `85` | JPEG 质量 |
| `images.send_max_side` | `1024` | 发给模型的缩略图最长边 |
| `front_matter.lang_field` | `post_lang` | 记录文章语言的 front-matter 字段名 |
| `front_matter.translation_field` | `translation` | 指向另一语言版本的字段名 |
| `slug_suffix` | `-{lang}` | 非首选语言的文件名后缀，如 `my-post-en` |
| `site_root` | `/` | Hexo 的 `root`，用于生成图片地址 |
| `commit_message` | `New post: {title}` | 提交说明，`{title}` 换成文章标题 |
| `style_notes` | 空 | 写给模型的文风要求 |
| `style_file` | 空 | 文风要求放在一个文件里时写它的路径 |
| `context_posts` | `5` | 给模型看最近几篇文章的标题 |
| `timeline_notes` | 空（关闭） | 填时间线说明文件路径，发布时自动追加记录 |
| `timeline_tags` | `[content]` | 时间线记录的标签 |
| `timeline_title_prefix` | `zh: 发布新文章：`、`en: New post: ` | 时间线标题前缀，按语言设置 |
| `timeout` | `180` | 单次请求超时秒数 |

---

## 5. 环境变量

| 变量 | 用途 |
|---|---|
| `OPENAI_API_KEY` | `openai` |
| `ANTHROPIC_API_KEY` | `anthropic` |
| `DEEPSEEK_API_KEY` | `deepseek` |
| `MOONSHOT_API_KEY` | `kimi` |
| `DASHSCOPE_API_KEY` | `qwen` |
| `LLM_API_KEY` | `custom` |
| `https_proxy` / `HTTPS_PROXY` | 需要代理访问 OpenAI、Claude 时设置 |

---

## 6. 隐私和安全检查

**发送前**扫描笔记，**发布前**扫描成品，用同一套规则：

| 级别 | 检测内容 | 处理 |
|---|---|---|
| 拦截 | 私钥、`sk-…` API Key、GitHub 令牌、AWS Key、Slack 令牌、Google API Key | 直接拒绝（`--allow-secrets` / `--force` 才能绕过） |
| 提醒 | 形如 `password=…` 的赋值、IP 地址、邮箱、国内手机号、`ssh 用户@主机`、个人目录路径 | 展示并询问是否继续 |

`127.0.0.1`、文档用的示例 IP（`203.0.113.x` 等）和 `example.com` 邮箱不会被报。提示里的内容只显示开头几个字符，**不会回显完整的密钥**。

---

## 7. 常用场景

只写英文版：

```bash
blogpub new notes.md --languages en
```

用另一家模型试一次，不改配置：

```bash
blogpub new notes.md --provider kimi --model moonshot-v1-32k
```

先看结果，满意再真正生成：

```bash
blogpub new notes.md --dry-run
```

指定标题、分类和标签：

```bash
blogpub new notes.md --title "用 Hexo 搭博客" --category 开发笔记 --tags Hexo,GitHub\ Pages
```

带图片：

```bash
blogpub new notes.md -i ~/Desktop/shots/
```

发布但先不推送，自己检查提交：

```bash
blogpub publish my-post --no-push
```

只把草稿移到 `_posts`，自己用 git 提交：

```bash
blogpub publish my-post --no-commit
```

---

## 8. 常见问题

| 现象 | 原因和处理 |
|---|---|
| `does not look like a Hexo blog` | 没在博客目录里运行。`cd` 进博客，或加 `--blog` |
| `Environment variable … is not set` | 没设置 Key，或变量名和所选服务商不对应（见第 5 节） |
| `HTTP 401` | Key 错误或已作废 |
| `HTTP 404` / 模型不存在 | 默认模型名过期，在配置里设置 `model:` |
| 超时或连接失败 | 国内访问 OpenAI / Claude 需要代理，设置 `https_proxy` |
| `secrets found in the notes` | 笔记含疑似密钥，删掉再运行 |
| `already exists` | 同名文章或草稿已存在，用 `--slug` 换个名字 |
| `already staged` | 有别的已暂存改动，先提交或 `git restore --staged 文件` |
| 警告"文章比笔记长很多" | 笔记太短，模型可能补充了你没写的内容，仔细核对，或写更具体的笔记 |
| 草稿里有 `TODO` | 模型缺信息的地方，补上或删掉；最好是把事实补进笔记重新生成 |
| `could not run hexo` | 博客里先运行一次 `npm install` |
