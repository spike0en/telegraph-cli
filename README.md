<div align="center">
  <img src="docs/assets/logo.png" alt="Telegraph CLI Logo" width="120">
  <h1>Telegra.ph Article Management CLI</h1>
  <p>A CLI tool for creating, publishing, editing, backing up, deleting, and managing Telegra.ph articles using Markdown or HTML.</p>

  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.8+-blue?style=for-the-badge" alt="Python"></a>
  <img src="https://hitscounter.dev/api/hit?url=https%3A%2F%2Fgithub.com%2Fspike0en%2Ftelegraph-cli&label=Views&icon=github&color=%231aa179&message=&style=for-the-badge&tz=Asia%2FCalcutta" alt="Hits">
</div>

## Why This CLI & Key Features

Telegra.ph lacks a local file editor and account backup tools. This CLI turns Telegra.ph into a local static-site publishing workflow:

- Draft articles locally in Markdown with YAML frontmatter headers and automatic date update banners.
- Embed local image files directly; the CLI auto-hosts them on free mirrors (`Uguu`, `Sxcu`, `Catbox`) and compiles captions into centered footers.
- Edit, update, or delete live articles by title, slug, or URL without losing local source files.
- Fail over to `graph.org` endpoints automatically to bypass regional ISP network blockades without a VPN.
- Download all account publications into local `.md` files and monitor live view statistics.
- Authenticate securely using Telegra.ph API tokens (`tph_token`) without linking Telegram account credentials.

## Quick Start & Installation

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/spike0en/telegraph-cli.git
cd telegraph-cli
pip install -r requirements.txt
```

### 2. Configure Environment Secrets

Copy `.env.example` to `.env` and set your token:

```bash
cp .env.example .env
```

### 3. Execution Options

Run commands directly with Python or use the provided wrapper scripts:

- Universal Python: `python telegraph.py <command>`
- Windows (CMD / PowerShell): `.\telegraph <command>`
- Linux / macOS (Shell): `./telegraph <command>`
- Editable Install: `pip install -e .` then `telegraph <command>`

## Step-by-Step Article Lifecycle Guide

Managing articles takes four basic steps.

### Step 1: Create a Draft Template

Generate a Markdown template in `articles/`:

```bash
python telegraph.py create "My New Guide"
```

This creates `articles/My_New_Guide.md` with pre-filled frontmatter metadata.

### Step 2: Edit Your Article Locally

Open `articles/My_New_Guide.md` in your text editor:

- Write content using standard Markdown syntax (`##` section headers, `-` bullet lists, `>` callouts).
- Embed local images using standard path formats for your operating system:
  - Relative Path (Universal): `![Caption Footer](./images/photo.png)`
  - Windows Path (CMD / PowerShell): `![Caption Footer](C:\path\to\image.png)`
  - Linux / macOS Path (Bash / Zsh): `![Caption Footer](/home/username/pictures/photo.png)`

### Step 3: Publish Live & Get Live URLs

Publish your draft:

```bash
python telegraph.py publish "My New Guide"
```

When published:

1. Local images upload automatically to free image mirrors (`Uguu`, `Sxcu`, `Catbox`).
2. Local image paths in your `.md` file update to hosted web URLs.
3. Frontmatter `updated_at` and the `> Last Updated` date banner refresh automatically.
4. Live article URLs (`https://telegra.ph/...` and `https://graph.org/...`) output to the terminal and save to your `.md` frontmatter header.

### Step 4: Update a Live Article

Make edits to your local `.md` file and push the updates live:

```bash
python telegraph.py edit "My-New-Guide-07-26"
```

You can pass the article slug, live URL, or filename. The CLI matches the corresponding local `.md` file automatically.

## Command Cheatsheet

| Task | CLI Command |
| :--- | :--- |
| Draft New Article | `python telegraph.py create "Article Title"` |
| Publish Local Article | `python telegraph.py publish "Article Title" [--hoster uguu/sxcu/catbox] [--no-date]` |
| Edit Live Article | `python telegraph.py edit <SLUG_OR_URL> [--hoster uguu/sxcu/catbox] [--no-date]` |
| Delete Article Live | `python telegraph.py delete <SLUG_OR_URL>` |
| Download Single Page | `python telegraph.py pull <SLUG_OR_URL>` |
| Backup All Articles | `python telegraph.py pull-all [--clean]` |
| Check Page View Count | `python telegraph.py views <SLUG_OR_URL>` |
| List Account Articles | `python telegraph.py list` |
| Show Account Info | `python telegraph.py account` |
| Upload Local Image | `python telegraph.py upload <IMAGE_PATH> [--hoster uguu/sxcu/catbox]` |
| Create New Account Token | `python telegraph.py create-account --short-name "MyBlog"` |

> Note: `publish` and `edit` update the `> Last Updated: Month DD, YYYY` date banner and auto-select image mirrors by default. Pass `--hoster <uguu|sxcu|catbox|imgbb|imgur>` to choose a provider, or `--no-date` to leave date banners unchanged.

## Formatting Guide

Telegra.ph compiles Markdown into HTML DOM nodes.

### 1. Heading Hierarchy

| Markdown Syntax | DOM Element | Rendered Style | Usage |
| :--- | :--- | :--- | :--- |
| `## Section` or `### Section` | `<H3>` | Large Header | Main section titles |
| `#### Subsection` | `<H4>` | Small Header | Subheadings and callouts |
| `# Title` | Stripped | N/A | Do not use in body text |

> Note: Avoid `#` headers in the article body. Telegra.ph renders the main title from frontmatter metadata.

### 2. Bullet Lists & Spacing

- Standard Lists: Place bullet items on consecutive lines without empty spaces:

```markdown
- Item 1 description.
- Item 2 description.
```

- Paragraph Spacing: Leave a blank line before starting a bullet list.
- Callout Blockquotes: Use `>` for callouts. Telegra.ph styles blockquotes with a left margin accent bar.

### 3. Links & Images

- Telegram Previews: Use `https://t.me/s/channel/12` format for Telegram links to generate instant web previews.
- Image Failover Chain: Local image references (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.mp4`) automatically upload through mirror providers (`Uguu.se` -> `Sxcu.net` -> `Catbox.moe` -> `ImgBB` -> `Imgur`).
- Manual Uploads: Run `python telegraph.py upload path/to/image.png [--hoster uguu/sxcu/catbox]` to upload a file directly.
- Image Footers & Captions: Alt text in Markdown (`![Caption text](url)`) or HTML `<figure><figcaption>` tags render as centered image footers.

### 4. Frontmatter Schema

Local files in `articles/` track metadata using YAML frontmatter:

```markdown
---
title: "Article Title Here"
path: "Article-Title-Here-07-26"
url: "https://telegra.ph/Article-Title-Here-07-26"
mirror_url: "https://graph.org/Article-Title-Here-07-26"
author: "Author Name"
author_url: "https://example.com"
views: 120
updated_at: "2026-07-26"
---
```

## Account Setup & Authentication

### Method A: Direct Account Creation

Create an account token directly from the CLI without a Telegram phone number or bot:

```bash
python telegraph.py create-account --short-name "MyBlog" --author "Your Name"
```

This saves `TELEGRAPH_ACCESS_TOKEN` to your `.env` file and outputs a management auth URL.

### Method B: Linking an Existing Account

Link an account managed by the `@Telegraph` Telegram bot:

#### Option 1: Automated Token Extractor

1. Open `@Telegraph` in Telegram and click **Log in on this device**.
2. Copy the authentication link (`https://edit.telegra.ph/auth/...`) without opening it in a browser.
3. Run the auth helper:

```bash
python -m telegraph_api.auth "https://edit.telegra.ph/auth/YOUR_LINK"
```

#### Option 2: Browser Cookie Inspection

1. Open `@Telegraph` in Telegram and click **Log in on this device**.
2. Open the link in a browser.
3. Press **F12** -> **Application/Storage** -> **Cookies** -> `https://edit.telegra.ph`.
4. Copy `tph_token` and paste it into `.env`:

```ini
TELEGRAPH_ACCESS_TOKEN=your_telegraph_access_token_here
```

## Repository Structure

```text
telegraph-cli/
├── telegraph_api/               # Core package
│   ├── __init__.py              # Package init
│   ├── manager.py               # API client and AST engine
│   ├── cli.py                   # CLI commands and argument parser
│   └── auth.py                  # Token extractor helper
├── articles/                    # Local article Markdown storage
├── .env.example                 # Environment template
├── .gitignore                   # Git ignore file
├── pyproject.toml               # Package manifest
├── requirements.txt             # Dependencies
├── LICENSE                      # MIT License
├── telegraph.py                 # Cross-platform entrypoint
├── telegraph                    # Shell script wrapper
├── telegraph.bat                # Windows Batch launcher
└── telegraph.ps1                # Windows PowerShell launcher
```

## License & Credits

Distributed under the [MIT License](LICENSE). Copyright (c) 2026 **spike0en**.
