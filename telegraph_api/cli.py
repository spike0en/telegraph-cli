"""
Telegra.ph CLI Command Line Interface Module

Responsibility:
    Provides positional and flagged CLI commands (`create`, `publish`, `edit`, `delete`, `pull`,
    `pull-all`, `list`, `views`, `account`, `create-account`, `help`) for managing Telegra.ph articles
    locally and live on Telegra.ph / Graph.org mirrors.

Non-Responsibility:
    Does not execute raw HTTP RPC calls directly; delegates network and AST parsing to `TelegraphManager`.

Layer:
    Layer 2 (Orchestration Engine / User CLI Interface)

Lifetime & Threading Constraints:
    Runs synchronously per CLI invocation (`.\\telegraph <command>`). Single-threaded.
    Handles environment variables stored in `.env` and automatic file resolution inside `articles/`.
"""

import os
import sys
import argparse
import re
import shutil
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv, set_key

from .manager import TelegraphManager, TelegraphAPIError

# Path reference to root .env file storing account access tokens and defaults
ENV_PATH = Path(__file__).parent.parent / '.env'

def load_token_and_defaults():
    """
    Loads account token and default configuration values from `.env`.

    @brief Load environment credentials and default author metadata.
    @return Tuple containing (access_token, short_name, author_name, author_url).
    """
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    token = os.getenv('TELEGRAPH_ACCESS_TOKEN')
    short_name = os.getenv('TELEGRAPH_SHORT_NAME', 'MyBlog')
    author_name = os.getenv('TELEGRAPH_AUTHOR_NAME')
    author_url = os.getenv('TELEGRAPH_AUTHOR_URL')
    return token, short_name, author_name, author_url

def save_env_var(key: str, value: str):
    """
    Writes or updates a key-value pair in the project `.env` file.

    @brief Save configuration key to .env file.
    @param key Target environment variable key name string.
    @param value Value string to save.
    @side_effects Modifies or creates `.env` file on disk.
    """
    if not ENV_PATH.exists():
        ENV_PATH.write_text("# Telegraph Config\n")
    set_key(str(ENV_PATH), key, value)

def sanitize_filename(name: str) -> str:
    """
    Sanitizes article title into a clean, filesystem-safe Markdown filename.

    @brief Normalize title string into filesystem-safe filename.
    @param name Raw article title string.
    @return Cleaned filename string (e.g. 'Guide_to_Flashing_ROMs').
    """
    # Step 1: Replace ampersands with 'and', slashes/colons with dashes
    s = re.sub(r'\s*&\s*', ' and ', name)
    s = re.sub(r'\s*[\/:|\\]+\s*', ' - ', s)
    s = re.sub(r"['’]", '', s)
    # Step 2: Remove illegal filesystem special characters
    s = re.sub(r'[^\w\s\-\(\)\.]', '', s)
    s = re.sub(r'\s+', '_', s.strip())
    s = re.sub(r'_+-_+|_+-|-+_', '_-_', s)
    s = re.sub(r'_+', '_', s)
    s = s.strip('._-')
    return s[:120] or "untitled"

def find_local_article_file(path_slug: str = None, file_arg: str = None) -> Path:
    """
    Smartly resolves the local Markdown file inside `articles/` or workspace directory.

    @brief Resolve local Markdown file by path slug or filename argument.
    @param path_slug Target Telegra.ph page path slug (e.g. 'My-Page-01-01').
    @param file_arg Optional explicit file path argument string.
    @return Path object pointing to resolved local Markdown file.
    @raise FileNotFoundError If matching file cannot be located.
    """
    articles_dir = Path("articles")
    
    # Step 1: Handle explicit --file argument if passed by user
    if file_arg:
        p = Path(file_arg)
        if p.exists():
            return p
        if (articles_dir / file_arg).exists():
            return articles_dir / file_arg
        if not file_arg.endswith('.md') and (articles_dir / f"{file_arg}.md").exists():
            return articles_dir / f"{file_arg}.md"
        sanitized = f"{sanitize_filename(file_arg)}.md"
        if (articles_dir / sanitized).exists():
            return articles_dir / sanitized
        raise FileNotFoundError(f"File not found: {file_arg} (checked workspace and 'articles/' directory)")

    # Step 2: Auto-resolve matching Markdown file in articles/ by matching frontmatter path
    if articles_dir.exists() and path_slug:
        for f in articles_dir.glob("*.md"):
            content = f.read_text(encoding='utf-8')
            if f'path: "{path_slug}"' in content or f'path: \'{path_slug}\'' in content:
                return f

    raise FileNotFoundError(
        f"Could not automatically find local article file for '{path_slug or file_arg}' in 'articles/' directory.\n"
        f"Please specify --file <PATH_TO_FILE>"
    )

def update_date_banner(clean_body: str, date_human: str) -> str:
    """
    Updates or inserts a standard blockquote `> Last Updated: <Date>` banner at the top of the article body.

    @brief Update or insert > Last Updated: banner in article Markdown body.
    @param clean_body Body text without YAML frontmatter.
    @param date_human Formatted human readable date string (e.g. 'July 26, 2026').
    @return Body text string with updated date banner.
    """
    pattern = r'^(>\s*(?:Last\s+)?Updated:\s*)[^\n]+'
    if re.search(pattern, clean_body, flags=re.IGNORECASE | re.MULTILINE):
        return re.sub(pattern, f"> Last Updated: {date_human}", clean_body, count=1, flags=re.IGNORECASE | re.MULTILINE)
    else:
        if clean_body:
            return f"> Last Updated: {date_human}\n\n{clean_body}"
        return f"> Last Updated: {date_human}"

def format_article_frontmatter(title: str, path: str, views: int, updated_at: str, clean_body: str, author: str = None, author_url: str = None) -> str:
    """
    Formats complete article Markdown text with updated YAML frontmatter header.

    @brief Build standard Markdown string with YAML frontmatter header.
    @param title Page title string.
    @param path Telegraph page path slug string.
    @param views View count integer.
    @param updated_at ISO date string (e.g. '2026-07-26').
    @param clean_body Article body Markdown text string.
    @param author Optional author name string.
    @param author_url Optional author profile URL string.
    @return Formatted full article text string.
    """
    author_line = f"author: \"{author}\"\n" if author else ""
    author_url_line = f"author_url: \"{author_url}\"\n" if author_url else ""
    return (
        f"---\n"
        f"title: \"{title}\"\n"
        f"path: \"{path}\"\n"
        f"url: \"https://telegra.ph/{path}\"\n"
        f"mirror_url: \"https://graph.org/{path}\"\n"
        f"{author_line}"
        f"{author_url_line}"
        f"views: {views}\n"
        f"updated_at: \"{updated_at}\"\n"
        f"---\n\n"
        f"{clean_body.strip()}\n"
    )

def print_help_guide():
    """
    Prints CLI cheat-sheet usage guide to stdout.
    
    @brief Output CLI cheat-sheet guide.
    """
    guide = r"""
========================================================================
           TELEGRA.PH ARTICLE MANAGEMENT CLI CHEAT-SHEET
========================================================================

COMMANDS & SHORTHAND EXAMPLES:

1.  .\telegraph create "Title" (or .\telegraph new "Title")
    Generate a new Markdown draft template in 'articles/Title.md'.
    Example: .\telegraph create "Nothing Phone (3) Review"

2.  .\telegraph publish <FILE_OR_TITLE> [--title TITLE] [--no-date]
    Publish a local Markdown file live to Telegra.ph & Graph.org!
    Auto-populates path/URLs in frontmatter and updates '> Last Updated' date banner (pass --no-date to skip).
    Example: .\telegraph publish "Nothing Phone (3) Review"

3.  .\telegraph edit <PATH_OR_URL> [--file FILE] [--no-date]
    Update a live article with updated local Markdown content.
    Auto-locates matching file in 'articles/' and refreshes '> Last Updated' date banner (pass --no-date to skip).
    Example: .\telegraph edit OTA-Sideloading-Guide-for-Nothing-Devices-01-17 --no-date

4.  .\telegraph delete <PATH_OR_URL>
    Wipe a live article (sets title to DELETED, clears body content)
    and removes its local Markdown file from your articles/ directory.
    Example: .\telegraph delete https://graph.org/Old-Article-Path-12-34

5.  .\telegraph views <PATH_OR_URL> [--year YYYY] [--month MM] [--day DD]
    Get total view statistics for a specific article.
    Example: .\telegraph views OTA-Sideloading-Guide-for-Nothing-Devices-01-17

6.  .\telegraph pull-all [--clean] [--include-deleted] [--dir FOLDER]
    Download ALL active articles from your account into local .md files.
    Use '--clean' to wipe stale local files first. Default: 'articles/'

7.  .\telegraph list [--offset N] [--limit N]
    List all articles published under this account with paths & views.

8.  .\telegraph account
    Show connected account details (Short Name, Author, Total Posts).

9.  .\telegraph upload <IMAGE_FILE_PATH>
    Upload a local image or video file and return a hosted web URL.
    Example: .\telegraph upload my_photo.png

10. .\telegraph create-account --short-name <NAME> [--author NAME] [--url URL]
    Generate a new Telegraph account token and save it to .env.

========================================================================
"""
    print(guide)

def cmd_create_account(args):
    """
    CLI Command Handler: Creates a new Telegra.ph account and updates `.env`.

    @brief Create new account CLI handler.
    @param args Argparse namespace containing short_name, author, url.
    """
    manager = TelegraphManager()
    try:
        res = manager.create_account(
            short_name=args.short_name,
            author_name=args.author,
            author_url=args.url
        )
        token = res.get('access_token')
        auth_url = res.get('auth_url')
        print("[SUCCESS] Account successfully created!")
        print(f"  Short Name: {args.short_name}")
        print(f"  Author Name: {args.author or 'N/A'}")
        print(f"  Access Token: {token}")
        if auth_url:
            print(f"  Management Auth URL: {auth_url}")

        save_env_var('TELEGRAPH_ACCESS_TOKEN', token)
        save_env_var('TELEGRAPH_SHORT_NAME', args.short_name)
        if args.author:
            save_env_var('TELEGRAPH_AUTHOR_NAME', args.author)
        if args.url:
            save_env_var('TELEGRAPH_AUTHOR_URL', args.url)
        print(f"\nSaved access token to {ENV_PATH}")
    except TelegraphAPIError as e:
        print(f"Error creating account: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_account_info(args):
    """
    CLI Command Handler: Displays authenticated account details.

    @brief Display account info CLI handler.
    @param args Argparse namespace object.
    """
    token, _, _, _ = load_token_and_defaults()
    if not token:
        print("Error: No access token found. Set TELEGRAPH_ACCESS_TOKEN in .env", file=sys.stderr)
        sys.exit(1)
    manager = TelegraphManager(access_token=token)
    try:
        info = manager.get_account_info()
        print("Account Information:")
        print(f"  Short Name:  {info.get('short_name')}")
        print(f"  Author Name: {info.get('author_name', 'N/A')}")
        print(f"  Author URL:  {info.get('author_url', 'N/A')}")
        print(f"  Page Count:  {info.get('page_count')}")
    except TelegraphAPIError as e:
        print(f"Error fetching account info: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_create(args):
    """
    CLI Command Handler: Generates a local draft `.md` template file in `articles/`.

    @brief Draft new article CLI handler.
    @param args Argparse namespace containing pos_title or title.
    """
    title = getattr(args, 'pos_title', None) or args.title
    if not title:
        print("Error: Article title is required. Usage: .\\telegraph create \"My Article Title\"", file=sys.stderr)
        sys.exit(1)

    out_dir = Path("articles")
    out_dir.mkdir(parents=True, exist_ok=True)

    base_filename = sanitize_filename(title)
    out_path = out_dir / f"{base_filename}.md"

    if out_path.exists():
        print(f"[NOTE] Draft file already exists: {out_path}")
        print(f"Edit the file and run: .\\telegraph publish \"{title}\" when ready.")
        return

    today_iso = datetime.now().strftime('%Y-%m-%d')
    today_human = datetime.now().strftime('%B %d, %Y')

    draft_template = (
        f"---\n"
        f"title: \"{title}\"\n"
        f"path: \"\"\n"
        f"url: \"\"\n"
        f"mirror_url: \"\"\n"
        f"views: 0\n"
        f"updated_at: \"{today_iso}\"\n"
        f"---\n\n"
        f"> Last Updated: {today_human}\n\n"
        f"📌 **{title}**\n\n"
        f"Write your article content here using standard Markdown...\n\n"
        f"--- \n\n"
        f"### 📌 1. Section Title\n\n"
        f"Your section text goes here.\n"
    )

    out_path.write_text(draft_template, encoding='utf-8')
    print(f"[SUCCESS] Draft Template Created!")
    print(f"  Title:      {title}")
    print(f"  Local File: {out_path.resolve()}")
    print(f"\nNext Steps:")
    print(f" 1. Open and edit '{out_path}' in VS Code / Markdown editor.")
    print(f" 2. Run '.\\telegraph publish \"{out_path.name}\"' when ready to publish live!")

def cmd_publish(args):
    """
    CLI Command Handler: Publishes a local Markdown file live to Telegra.ph and updates frontmatter.

    @brief Publish local file CLI handler.
    @param args Argparse namespace containing pos_file, file, title, author, url, no_date.
    """
    token, _, default_author, default_url = load_token_and_defaults()
    if not token:
        print("Error: No access token found. Set TELEGRAPH_ACCESS_TOKEN in .env", file=sys.stderr)
        sys.exit(1)

    file_arg = getattr(args, 'pos_file', None) or args.file
    if not file_arg:
        print("Error: Specify file path or article name. Example: .\\telegraph publish \"My Article Title\"", file=sys.stderr)
        sys.exit(1)

    try:
        file_path = find_local_article_file(path_slug="", file_arg=file_arg)
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    raw_content = file_path.read_text(encoding='utf-8')
    
    # Step 1: Extract title from frontmatter header or fallback to filename
    title = args.title
    if not title:
        m = re.search(r'title:\s*["\'](.*?)["\']', raw_content)
        if m:
            title = m.group(1)
        else:
            title = file_path.stem.replace('_', ' ')

    today_iso = datetime.now().strftime('%Y-%m-%d')
    today_human = datetime.now().strftime('%B %d, %Y')

    clean_body = re.sub(r'^---\s*\n.*?\n---\s*\n', '', raw_content, flags=re.DOTALL).strip()
    if not getattr(args, 'no_date', False):
        clean_body = update_date_banner(clean_body, today_human)

    manager = TelegraphManager(access_token=token)
    hoster_choice = getattr(args, 'hoster', None) or getattr(args, 'provider', None)
    clean_body = manager.process_local_images(clean_body, base_dir=file_path.parent, provider=hoster_choice)

    # Step 2: Convert input format to Telegraph DOM AST nodes
    if file_path.suffix.lower() in ('.html', '.htm'):
        nodes = manager.html_to_nodes(clean_body)
    else:
        nodes = manager.markdown_to_nodes(clean_body)

    author_name = args.author
    if not author_name:
        m_auth = re.search(r'^(?:author|author_name):\s*["\']?(.*?)["\']?\s*$', raw_content, re.MULTILINE)
        if m_auth:
            author_name = m_auth.group(1).strip()
    if not author_name:
        author_name = default_author

    author_url = args.url
    if not author_url:
        m_url = re.search(r'^author_url:\s*["\']?(.*?)["\']?\s*$', raw_content, re.MULTILINE)
        if m_url:
            author_url = m_url.group(1).strip()
    if not author_url:
        author_url = default_url

    try:
        # Step 3: Publish page live via Telegra.ph API
        res = manager.create_page(
            title=title,
            content=nodes,
            author_name=author_name,
            author_url=author_url
        )
        path = res.get('path')
        
        # Step 4: Write updated frontmatter with live URLs and date back to local file
        updated_file_text = format_article_frontmatter(
            title=title,
            path=path,
            views=res.get('views', 0),
            updated_at=today_iso,
            clean_body=clean_body,
            author=author_name,
            author_url=author_url
        )
        file_path.write_text(updated_file_text, encoding='utf-8')

        print("[SUCCESS] Page Published Successfully Live!")
        print(f"  Title:           {title}")
        print(f"  Author:          {author_name or 'N/A'}")
        print(f"  Author URL:      {author_url or 'N/A'}")
        print(f"  Path:            {path}")
        print(f"  URL (Global):    https://telegra.ph/{path}")
        print(f"  URL (India/Alt): https://graph.org/{path}")
        print(f"  Last Updated:    {today_human} ({today_iso})")
        print(f"  Updated File:    {file_path.name}")
    except TelegraphAPIError as e:
        print(f"Error publishing page: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_edit(args):
    """
    CLI Command Handler: Updates an existing live page with updated local Markdown content.

    @brief Edit live article CLI handler.
    @param args Argparse namespace containing pos_path, path, file, title, author, url, no_date.
    """
    token, _, default_author, default_url = load_token_and_defaults()
    if not token:
        print("Error: No access token found. Set TELEGRAPH_ACCESS_TOKEN in .env", file=sys.stderr)
        sys.exit(1)

    path = getattr(args, 'pos_path', None) or args.path
    if not path:
        print("Error: Page path or URL is required.", file=sys.stderr)
        sys.exit(1)

    # Step 1: Strip domain prefix from URL if user passed full telegra.ph / graph.org URL
    if 'telegra.ph/' in path or 'graph.org/' in path:
        path = re.sub(r'https?://[^/]+/', '', path)

    try:
        file_path = find_local_article_file(path_slug=path, file_arg=args.file)
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    raw_content = file_path.read_text(encoding='utf-8')

    title = args.title
    if not title:
        m = re.search(r'title:\s*["\'](.*?)["\']', raw_content)
        if m:
            title = m.group(1)
        else:
            page_info = TelegraphManager().get_page(path, return_content=False)
            title = page_info.get('title')

    today_iso = datetime.now().strftime('%Y-%m-%d')
    today_human = datetime.now().strftime('%B %d, %Y')

    clean_body = re.sub(r'^---\s*\n.*?\n---\s*\n', '', raw_content, flags=re.DOTALL).strip()
    if not getattr(args, 'no_date', False):
        clean_body = update_date_banner(clean_body, today_human)

    manager = TelegraphManager(access_token=token)
    hoster_choice = getattr(args, 'hoster', None) or getattr(args, 'provider', None)
    clean_body = manager.process_local_images(clean_body, base_dir=file_path.parent, provider=hoster_choice)

    # Step 2: Convert Markdown content to DOM AST nodes
    if file_path.suffix.lower() in ('.html', '.htm'):
        nodes = manager.html_to_nodes(clean_body)
    else:
        nodes = manager.markdown_to_nodes(clean_body)

    author_name = args.author
    if not author_name:
        m_auth = re.search(r'^(?:author|author_name):\s*["\']?(.*?)["\']?\s*$', raw_content, re.MULTILINE)
        if m_auth:
            author_name = m_auth.group(1).strip()
    if not author_name:
        author_name = default_author

    author_url = args.url
    if not author_url:
        m_url = re.search(r'^author_url:\s*["\']?(.*?)["\']?\s*$', raw_content, re.MULTILINE)
        if m_url:
            author_url = m_url.group(1).strip()
    if not author_url:
        author_url = default_url

    try:
        # Step 3: Execute editPage RPC call
        res = manager.edit_page(
            path=path,
            title=title,
            content=nodes,
            author_name=author_name,
            author_url=author_url
        )

        # Step 4: Write updated frontmatter and body back to local file
        updated_file_text = format_article_frontmatter(
            title=title,
            path=path,
            views=res.get('views', 0),
            updated_at=today_iso,
            clean_body=clean_body,
            author=author_name,
            author_url=author_url
        )
        file_path.write_text(updated_file_text, encoding='utf-8')

        print("[SUCCESS] Page Updated Successfully!")
        print(f"  Title:           {res.get('title')}")
        print(f"  Author:          {author_name or 'N/A'}")
        print(f"  Author URL:      {author_url or 'N/A'}")
        print(f"  Path:            {path}")
        print(f"  URL (Global):    https://telegra.ph/{path}")
        print(f"  URL (India/Alt): https://graph.org/{path}")
        print(f"  Last Updated:    {today_human} ({today_iso})")
        print(f"  Source File:     {file_path.name}")
    except TelegraphAPIError as e:
        print(f"Error updating page: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_delete(args):
    """
    CLI Command Handler: Wipes a live page (sets title to DELETED) and removes local file.

    @brief Delete live page CLI handler.
    @param args Argparse namespace containing pos_path, path, file.
    """
    token, _, _, _ = load_token_and_defaults()
    if not token:
        print("Error: No access token found. Set TELEGRAPH_ACCESS_TOKEN in .env", file=sys.stderr)
        sys.exit(1)

    path = getattr(args, 'pos_path', None) or args.path
    if not path:
        print("Error: Page path or URL is required.", file=sys.stderr)
        sys.exit(1)

    if 'telegra.ph/' in path or 'graph.org/' in path:
        path = re.sub(r'https?://[^/]+/', '', path)

    manager = TelegraphManager(access_token=token)
    try:
        # Step 1: Wipe live content by overwriting body with empty placeholder node
        empty_nodes = [{'tag': 'p', 'children': ['.']}]
        res = manager.edit_page(
            path=path,
            title="DELETED",
            content=empty_nodes
        )
        print("[SUCCESS] Article Wiped & Marked DELETED Live!")
        print(f"  Path:            {path}")
        print(f"  URL (Global):    https://telegra.ph/{path}")
        print(f"  URL (India/Alt): https://graph.org/{path}")

        # Step 2: Delete matching local Markdown file from articles/ directory
        try:
            local_file = find_local_article_file(path_slug=path, file_arg=args.file)
            local_file.unlink()
            print(f"  Removed Local:   {local_file.name}")
        except FileNotFoundError:
            pass

    except TelegraphAPIError as e:
        print(f"Error deleting page: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_pull(args):
    """
    CLI Command Handler: Downloads a single page by path/URL and saves locally as Markdown.

    @brief Download single page CLI handler.
    @param args Argparse namespace containing pos_path, path, output.
    """
    path = getattr(args, 'pos_path', None) or args.path
    if not path:
        print("Error: Page path or URL is required.", file=sys.stderr)
        sys.exit(1)

    if 'telegra.ph/' in path or 'graph.org/' in path:
        path = re.sub(r'https?://[^/]+/', '', path)

    out_arg = args.output
    if not out_arg:
        page_info = TelegraphManager().get_page(path=path, return_content=False)
        title = page_info.get('title', 'Untitled')
        out_arg = str(Path("articles") / f"{sanitize_filename(title)}.md")

    today_iso = datetime.now().strftime('%Y-%m-%d')
    manager = TelegraphManager()
    try:
        # Step 1: Fetch page content nodes
        res = manager.get_page(path=path, return_content=True)
        title = res.get('title', 'Untitled')
        content_nodes = res.get('content', [])
        md_text = manager.nodes_to_markdown(content_nodes)

        # Step 2: Format content with frontmatter header
        output_content = format_article_frontmatter(
            title=title,
            path=path,
            views=res.get('views', 0),
            updated_at=today_iso,
            clean_body=md_text,
            author=res.get('author_name'),
            author_url=res.get('author_url')
        )
        out_file = Path(out_arg)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        out_file.write_text(output_content, encoding='utf-8')

        print("[SUCCESS] Page Pulled Successfully!")
        print(f"  Title:    {title}")
        print(f"  Saved to: {out_file.resolve()}")
    except TelegraphAPIError as e:
        print(f"Error pulling page: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_pull_all(args):
    """
    CLI Command Handler: Downloads ALL articles published under the account into local `.md` files.

    @brief Sync all account articles CLI handler.
    @param args Argparse namespace containing dir, clean, include_deleted.
    """
    token, _, _, _ = load_token_and_defaults()
    if not token:
        print("Error: No access token found. Set TELEGRAPH_ACCESS_TOKEN in .env", file=sys.stderr)
        sys.exit(1)

    manager = TelegraphManager(access_token=token)
    out_dir = Path(args.dir)

    # Step 1: Wipe existing local files if --clean flag is present
    if getattr(args, 'clean', False) and out_dir.exists():
        shutil.rmtree(out_dir)
        print(f"Cleared existing files in '{out_dir}'...")

    out_dir.mkdir(parents=True, exist_ok=True)

    today_iso = datetime.now().strftime('%Y-%m-%d')

    try:
        print("Fetching account page list...")
        offset = 0
        limit = 50
        all_pages = []

        # Step 2: Paginate through getPageList to collect all user articles
        while True:
            res = manager.get_page_list(offset=offset, limit=limit)
            pages = res.get('pages', [])
            all_pages.extend(pages)
            if len(pages) < limit:
                break
            offset += limit

        print(f"Found {len(all_pages)} total articles under this account.")
        print(f"Downloading and converting articles to Markdown in '{out_dir}'...\n")

        used_filenames = set()
        saved_count = 0
        skipped_deleted = 0

        # Step 3: Iterate through pages, convert nodes to Markdown, and save files
        for idx, page_info in enumerate(all_pages, 1):
            path = page_info.get('path')
            title = page_info.get('title', f"Untitled_{path}")
            
            if not getattr(args, 'include_deleted', False) and title.strip().upper() == 'DELETED':
                print(f" [{idx}/{len(all_pages)}] Skipped (DELETED): {path}")
                skipped_deleted += 1
                continue

            try:
                page_full = manager.get_page(path=path, return_content=True)
                content_nodes = page_full.get('content', [])
                md_body = manager.nodes_to_markdown(content_nodes)
                
                file_text = format_article_frontmatter(
                    title=title,
                    path=path,
                    views=page_full.get('views', 0),
                    updated_at=today_iso,
                    clean_body=md_body,
                    author=page_full.get('author_name'),
                    author_url=page_full.get('author_url')
                )

                base_filename = sanitize_filename(title)
                filename = f"{base_filename}.md"
                
                if filename in used_filenames:
                    filename = f"{base_filename}_{path[:8]}.md"
                used_filenames.add(filename)

                out_path = out_dir / filename
                out_path.write_text(file_text, encoding='utf-8')
                print(f" [{idx}/{len(all_pages)}] Saved: {out_path.name}")
                saved_count += 1
            except TelegraphAPIError as err:
                print(f" [FAILED] Failed to download {path}: {err}", file=sys.stderr)

        print(f"\n[SUCCESS] Downloaded {saved_count} active articles (skipped {skipped_deleted} DELETED) into '{out_dir.resolve()}'!")

    except TelegraphAPIError as e:
        print(f"Error fetching article list: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_list(args):
    """
    CLI Command Handler: Lists all pages created by the authenticated account.

    @brief List pages CLI handler.
    @param args Argparse namespace containing offset and limit.
    """
    token, _, _, _ = load_token_and_defaults()
    if not token:
        print("Error: No access token found. Set TELEGRAPH_ACCESS_TOKEN in .env", file=sys.stderr)
        sys.exit(1)

    manager = TelegraphManager(access_token=token)
    try:
        res = manager.get_page_list(offset=args.offset, limit=args.limit)
        total = res.get('total_count', 0)
        pages = res.get('pages', [])

        print(f"Total Pages: {total} (Showing {len(pages)} starting at offset {args.offset})")
        print("=" * 70)
        for idx, p in enumerate(pages, 1):
            title = p.get('title', '')
            path = p.get('path', '')
            status = " [DELETED]" if title.strip().upper() == 'DELETED' else ""
            print(f"{idx}. Title: {title}{status}")
            print(f"   Path:            {path}")
            print(f"   URL (Global):    https://telegra.ph/{path}")
            print(f"   URL (India/Alt): https://graph.org/{path}")
            print(f"   Views:           {p.get('views', 0)}")
            print("-" * 70)
    except TelegraphAPIError as e:
        print(f"Error listing pages: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_views(args):
    """
    CLI Command Handler: Fetches page view statistics.

    @brief Page view count CLI handler.
    @param args Argparse namespace containing pos_path, path, year, month, day, hour.
    """
    path = getattr(args, 'pos_path', None) or args.path
    if not path:
        print("Error: Page path or URL is required.", file=sys.stderr)
        sys.exit(1)

    if 'telegra.ph/' in path or 'graph.org/' in path:
        path = re.sub(r'https?://[^/]+/', '', path)

    manager = TelegraphManager()
    try:
        res = manager.get_views(path=path, year=args.year, month=args.month, day=args.day, hour=args.hour)
        views = res.get('views', 0)
        print(f"Page Path:   {path}")
        print(f"Total Views: {views}")
    except TelegraphAPIError as e:
        print(f"Error getting views: {e}", file=sys.stderr)
        sys.exit(1)

def cmd_upload(args):
    """
    CLI Command Handler: Uploads a local image or video file and prints the hosted public web URL.

    @brief Upload local image file CLI handler.
    @param args Argparse namespace containing pos_file, file.
    @side_effects Performs outbound network uploads to image mirrors.
    """
    # Step 1: Extract target image file path from CLI positional or flagged arguments
    file_path_str = getattr(args, 'pos_file', None) or args.file
    if not file_path_str:
        print("Error: Specify image file path. Usage: python telegraph.py upload <IMAGE_FILE_PATH>", file=sys.stderr)
        sys.exit(1)

    # Step 2: Validate filesystem existence of specified file
    p = Path(file_path_str)
    if not p.exists():
        print(f"Error: File not found: {p.resolve()}", file=sys.stderr)
        sys.exit(1)

    # Step 3: Instantiate manager engine and execute upload via multi-provider failover chain
    manager = TelegraphManager()
    hoster_choice = getattr(args, 'hoster', None) or getattr(args, 'provider', None)
    try:
        url = manager.upload_file(p, provider=hoster_choice)
        # Step 4: Display upload result and ready-to-use Markdown syntax
        print("[SUCCESS] Image Uploaded Successfully!")
        print(f"  Local File: {p.name}")
        print(f"  Hosted URL: {url}")
        print(f"  Markdown:   ![Image Description]({url})")
    except TelegraphAPIError as e:
        print(f"Error uploading image: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    """
    Main CLI argument parser registration and execution dispatcher.
    
    @brief Main argument parser entrypoint for telegraph CLI.
    """
    parser = argparse.ArgumentParser(description="Telegra.ph Article Management CLI Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    sp_help = subparsers.add_parser("help", help="Show CLI cheat-sheet guide")
    sp_help.set_defaults(func=lambda args: print_help_guide())

    sp_upload = subparsers.add_parser("upload", help="Upload a local image/video file and print hosted URL")
    sp_upload.add_argument("pos_file", nargs="?", help="Path to local image/video file (positional)")
    sp_upload.add_argument("--file", help="Path to local image/video file (flag)")
    sp_upload.add_argument("--hoster", "--provider", choices=["auto", "uguu", "sxcu", "catbox", "imgbb", "imgur"], default="auto", help="Preferred image hoster provider (default: auto)")
    sp_upload.set_defaults(func=cmd_upload)

    sp_account = subparsers.add_parser("create-account", help="Create a new Telegraph account")
    sp_account.add_argument("--short-name", required=True, help="Short name for account (1-32 chars)")
    sp_account.add_argument("--author", help="Default author name")
    sp_account.add_argument("--url", help="Default author URL")
    sp_account.set_defaults(func=cmd_create_account)

    sp_acc_info = subparsers.add_parser("account", help="Show account info")
    sp_acc_info.set_defaults(func=cmd_account_info)

    # Create / New subcommand
    sp_create = subparsers.add_parser("create", aliases=["new"], help="Create a new Markdown draft template in articles/")
    sp_create.add_argument("pos_title", nargs="?", help="Article Title (positional)")
    sp_create.add_argument("--title", help="Article Title (flag)")
    sp_create.set_defaults(func=cmd_create)

    # Publish subcommand
    sp_pub = subparsers.add_parser("publish", help="Publish a local Markdown file live to Telegra.ph")
    sp_pub.add_argument("pos_file", nargs="?", help="File path or article title (positional)")
    sp_pub.add_argument("--file", help="File path (flag)")
    sp_pub.add_argument("--title", help="Page Title override (optional)")
    sp_pub.add_argument("--author", help="Author name")
    sp_pub.add_argument("--url", help="Author URL")
    sp_pub.add_argument("--hoster", "--provider", choices=["auto", "uguu", "sxcu", "catbox", "imgbb", "imgur"], default="auto", help="Preferred image hoster provider (default: auto)")
    sp_pub.add_argument("--no-date", action="store_true", help="Skip automatic date banner injection")
    sp_pub.set_defaults(func=cmd_publish)

    sp_edit = subparsers.add_parser("edit", help="Update an existing page with new local file content")
    sp_edit.add_argument("pos_path", nargs="?", help="Telegraph page path or full URL (positional)")
    sp_edit.add_argument("--path", help="Telegraph page path or full URL (flag)")
    sp_edit.add_argument("--file", help="Path to local .md file (optional, auto-looks in articles/)")
    sp_edit.add_argument("--title", help="Updated Page Title (optional)")
    sp_edit.add_argument("--author", help="Author name")
    sp_edit.add_argument("--url", help="Author URL")
    sp_edit.add_argument("--hoster", "--provider", choices=["auto", "uguu", "sxcu", "catbox", "imgbb", "imgur"], default="auto", help="Preferred image hoster provider (default: auto)")
    sp_edit.add_argument("--no-date", action="store_true", help="Skip automatic date banner injection")
    sp_edit.set_defaults(func=cmd_edit)

    sp_del = subparsers.add_parser("delete", help="Wipe a live article and delete local markdown file")
    sp_del.add_argument("pos_path", nargs="?", help="Telegraph page path or full URL (positional)")
    sp_del.add_argument("--path", help="Telegraph page path or full URL (flag)")
    sp_del.add_argument("--file", help="Path to local .md file to remove (optional)")
    sp_del.set_defaults(func=cmd_delete)

    sp_pull = subparsers.add_parser("pull", help="Download a single Telegraph page and save locally as Markdown")
    sp_pull.add_argument("pos_path", nargs="?", help="Telegraph page path or full URL (positional)")
    sp_pull.add_argument("--path", help="Telegraph page path or full URL (flag)")
    sp_pull.add_argument("--output", help="Output local file path (default: articles/<Title>.md)")
    sp_pull.set_defaults(func=cmd_pull)

    sp_pull_all = subparsers.add_parser("pull-all", help="Download ALL Telegraph articles from your account as local .md files")
    sp_pull_all.add_argument("--dir", default="articles", help="Output directory folder (default: articles)")
    sp_pull_all.add_argument("--clean", action="store_true", help="Clean/wipe output directory before fetching")
    sp_pull_all.add_argument("--include-deleted", action="store_true", help="Include DELETED articles in download")
    sp_pull_all.set_defaults(func=cmd_pull_all)

    sp_list = subparsers.add_parser("list", help="List pages created by this account")
    sp_list.add_argument("--offset", type=int, default=0, help="Offset")
    sp_list.add_argument("--limit", type=int, default=50, help="Limit (max 50)")
    sp_list.set_defaults(func=cmd_list)

    sp_views = subparsers.add_parser("views", help="Get view count for a page")
    sp_views.add_argument("pos_path", nargs="?", help="Telegraph page path or full URL (positional)")
    sp_views.add_argument("--path", help="Telegraph page path or full URL (flag)")
    sp_views.add_argument("--year", type=int, help="Year (optional)")
    sp_views.add_argument("--month", type=int, help="Month (optional)")
    sp_views.add_argument("--day", type=int, help="Day (optional)")
    sp_views.add_argument("--hour", type=int, help="Hour (optional)")
    sp_views.set_defaults(func=cmd_views)

    args = parser.parse_args()
    if not hasattr(args, 'func'):
        print_help_guide()
        sys.exit(1)

    args.func(args)

if __name__ == '__main__':
    main()
