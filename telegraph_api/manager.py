"""
Telegra.ph API Management & Content Serialization Library

Responsibility:
    Provides a low-level, high-reliability Python interface (`TelegraphManager`) for interacting
    with Telegra.ph API endpoints (`createAccount`, `createPage`, `editPage`, `getPage`, `getPageList`,
    `getViews`). Includes robust AST conversion between Markdown, HTML, and Telegra.ph DOM Node trees,
    and features multi-mirror API failover (`graph.org`, `telegra.ph`, `edit.telegra.ph`).

Non-Responsibility:
    Does not handle CLI argument parsing or user interaction terminal prompts.

Layer:
    Layer 3 (Deterministic Execution Engine)

Lifetime & Threading Constraints:
    Instantiated per API session or CLI command execution. Synchronous thread execution with exponential
    backoff retry mechanisms for rate limits (`FLOOD_WAIT`) and multi-endpoint failover.
"""

import os
import json
import time
import re
import requests
import markdown
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag

# Permitted HTML tag names supported by Telegra.ph DOM Node specification
ALLOWED_TAGS = {
    'a', 'aside', 'b', 'blockquote', 'br', 'code', 'em', 'figcaption',
    'figure', 'h3', 'h4', 'hr', 'i', 'iframe', 'img', 'li', 'ol', 'p',
    'pre', 's', 'strong', 'sub', 'sup', 'u', 'ul', 'video'
}

# Mapping table for converting standard HTML heading/container tags into Telegra.ph compliant equivalents
TAG_MAPPING = {
    'h1': 'h3',
    'h2': 'h4',
    'div': 'p',
    'section': 'p',
    'article': 'p',
    'span': None,  # Unwrap span tags and extract children directly
}

# Permitted element attributes allowed by Telegra.ph DOM AST
ALLOWED_ATTRS = {'href', 'src'}

class TelegraphAPIError(Exception):
    """Custom exception class for Telegra.ph API network or parameter errors."""
    pass

class TelegraphManager:
    """
    Core management class for interacting with Telegra.ph API and serializing content formats.

    Role:
        Executes HTTP RPC calls to Telegra.ph backend servers and serializes Markdown/HTML
        into Telegra.ph DOM JSON AST node structures.

    Collaborators:
        - `requests.Session`: Underlying HTTP transport layer.
        - `BeautifulSoup`: HTML parser for converting markup into DOM nodes.
        - `markdown`: Markdown parser for compiling `.md` strings to HTML AST.

    Lifecycle & Thread Model:
        Instantiated as needed per command workflow. Single-threaded synchronous calls.
        Features automatic failover across multiple API mirror hosts if primary endpoint fails.
    """

    # List of official and regional mirror endpoints for high-availability request routing
    API_ENDPOINTS = [
        "https://api.graph.org",
        "https://api.telegra.ph",
        "https://edit.telegra.ph"
    ]

    def __init__(self, access_token: str = None, api_url: str = None, proxy: str = None, max_retries: int = 3):
        """
        Initializes the TelegraphManager instance with access tokens, API endpoints, and proxies.

        @brief Construct TelegraphManager instance.
        @param access_token Optional Telegra.ph account access token string.
        @param api_url Optional API base URL override (defaults to environment or mirror endpoints).
        @param proxy Optional HTTP/HTTPS proxy server URL string.
        @param max_retries Maximum retry attempts per API endpoint on rate limit or transient network failure (default: 3).
        """
        self.access_token = access_token
        configured_url = api_url or os.getenv('TELEGRAPH_API_URL')
        
        # Step 1: Configure endpoint fallback list, prioritizing user-defined URLs if set
        if configured_url:
            self.endpoints = [configured_url.rstrip('/')] + [ep for ep in self.API_ENDPOINTS if ep != configured_url.rstrip('/')]
        else:
            self.endpoints = list(self.API_ENDPOINTS)

        self.working_endpoint_idx = 0
        self.max_retries = max_retries
        self.session = requests.Session()
        
        # Step 2: Set browser-like User-Agent headers to prevent Cloudflare/CDN blockades
        self.session.headers.update({
            'User-Agent': 'TelegraphPython/1.0 (Windows NT 10.0; Win64; x64)'
        })

        # Step 3: Configure proxy routing if specified in arguments or environment variables
        proxy_url = proxy or os.getenv('TELEGRAPH_PROXY') or os.getenv('HTTPS_PROXY') or os.getenv('HTTP_PROXY')
        if proxy_url:
            self.session.proxies = {
                'http': proxy_url,
                'https': proxy_url
            }

    @property
    def current_api_url(self) -> str:
        """
        Returns the currently active API mirror base URL.
        
        @brief Get active API endpoint URL.
        @return Base URL string (e.g. 'https://api.graph.org').
        """
        return self.endpoints[self.working_endpoint_idx]

    def _request(self, method: str, params: dict = None, data: dict = None) -> dict:
        """
        Executes an HTTP POST request against Telegra.ph API mirrors with auto-failover and backoff retries.

        @brief Internal RPC helper for executing Telegra.ph API calls.
        @param method Telegra.ph API method name (e.g. 'createPage', 'editPage').
        @param params Optional dictionary for query string parameters or JSON body.
        @param data Optional dictionary for form-encoded request data payload.
        @return Result dictionary extracted from the API response's 'result' key.
        @raise TelegraphAPIError If all mirror endpoints fail or API returns error response.
        @side_effects Performs outbound network HTTP requests; handles backoff sleep delays on rate-limits.
        """
        total_endpoints = len(self.endpoints)
        
        # Step 1: Cycle through all registered API mirror endpoints if primary host fails
        for ep_attempt in range(total_endpoints):
            base_url = self.endpoints[(self.working_endpoint_idx + ep_attempt) % total_endpoints]
            url = f"{base_url}/{method}"
            retries = 0
            
            # Step 2: Perform retry loop with exponential backoff for rate-limit handling
            while retries < self.max_retries:
                try:
                    response = self.session.post(url, data=data, json=params, timeout=12)
                    
                    # Handle 429 Too Many Requests response code with exponential delay
                    if response.status_code == 429:
                        wait_time = (2 ** retries) + 1
                        time.sleep(wait_time)
                        retries += 1
                        continue
                    
                    result = response.json()
                    if not result.get('ok'):
                        error_msg = result.get('error', 'Unknown Telegraph API Error')
                        # Intercept FLOOD_WAIT error codes issued by Telegram API backend
                        if 'FLOOD_WAIT' in error_msg or 'TOO_MANY_REQUESTS' in error_msg:
                            wait_time = (2 ** retries) + 2
                            time.sleep(wait_time)
                            retries += 1
                            continue
                        raise TelegraphAPIError(f"Telegraph API Error: {error_msg}")
                    
                    # Store working endpoint index upon successful call
                    self.working_endpoint_idx = (self.working_endpoint_idx + ep_attempt) % total_endpoints
                    return result.get('result')
                
                except TelegraphAPIError:
                    raise
                except (requests.RequestException, json.JSONDecodeError):
                    retries += 1
                    if retries >= self.max_retries:
                        break
                    time.sleep(1)

        raise TelegraphAPIError(
            f"Failed to connect to any Telegraph API mirrors ({', '.join(self.endpoints)}).\n"
            "If your network blocks Telegram services, configure TELEGRAPH_PROXY in .env or turn on your VPN."
        )

    def create_account(self, short_name: str, author_name: str = None, author_url: str = None) -> dict:
        """
        Creates a new Telegra.ph account access token.

        @brief Create new account on Telegra.ph.
        @param short_name Account short name (1-32 characters).
        @param author_name Default author name for published articles.
        @param author_url Default author profile link URL.
        @return Account information dictionary containing 'access_token', 'auth_url', etc.
        """
        data = {'short_name': short_name}
        if author_name: data['author_name'] = author_name
        if author_url: data['author_url'] = author_url
        res = self._request('createAccount', data=data)
        return res

    def upload_file(self, file_path, provider: str = None) -> str:
        """
        Uploads a local image or video file to free public image mirrors with automatic multi-provider failover.

        @brief Upload local image file to free public mirrors and return hosted URL.
        @param file_path Path object or string path to local image file.
        @param provider Optional preferred hoster name ('uguu', 'sxcu', 'catbox', 'imgbb', 'imgur', 'auto').
        @return Public web image URL string (e.g. 'https://h.uguu.se/xxxx.png').
        @raise FileNotFoundError If the specified local file does not exist on disk.
        @raise TelegraphAPIError If all image hosting mirrors fail or network is unreachable.
        @note Operates synchronously; attempts preferred hoster first, then cycles through fallbacks.
        """
        # Step 1: Validate local file existence on filesystem
        p = Path(file_path)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Local file not found for upload: {file_path}")

        # Step 2: Determine MIME content-type based on file extension
        ext = p.suffix.lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.mp4': 'video/mp4'
        }
        mime = mime_types.get(ext, 'application/octet-stream')

        # Step 3: Define provider handler functions
        def try_uguu():
            with open(p, 'rb') as f:
                res = requests.post(
                    'https://uguu.se/upload.php',
                    files={'files[]': (p.name, f, mime)},
                    timeout=15
                )
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, dict) and data.get('success'):
                        files = data.get('files', [])
                        if files and len(files) > 0 and files[0].get('url'):
                            return files[0]['url']
            return None

        def try_sxcu():
            with open(p, 'rb') as f:
                res = requests.post(
                    'https://sxcu.net/api/files/create',
                    files={'file': (p.name, f, mime)},
                    timeout=15
                )
                if res.status_code == 200:
                    data = res.json()
                    if isinstance(data, dict):
                        raw_url = data.get('thumb') or data.get('url')
                        if raw_url:
                            return raw_url
            return None

        def try_catbox():
            with open(p, 'rb') as f:
                res = requests.post(
                    'https://catbox.moe/user/api.php',
                    data={'reqtype': 'fileupload'},
                    files={'fileToUpload': (p.name, f, mime)},
                    timeout=20
                )
                if res.status_code == 200 and res.text.strip().startswith('http'):
                    return res.text.strip()
            return None

        def try_imgbb():
            imgbb_key = os.getenv('IMGBB_API_KEY') or os.getenv('TELEGRAPH_IMGBB_API_KEY')
            if imgbb_key:
                with open(p, 'rb') as f:
                    res = requests.post(
                        'https://api.imgbb.com/1/upload',
                        data={'key': imgbb_key},
                        files={'image': (p.name, f, mime)},
                        timeout=20
                    )
                    if res.status_code == 200:
                        data = res.json()
                        if isinstance(data, dict) and data.get('data', {}).get('url'):
                            return data['data']['url']
            return None

        def try_imgur():
            imgur_client_id = os.getenv('IMGUR_CLIENT_ID') or os.getenv('TELEGRAPH_IMGUR_CLIENT_ID')
            if imgur_client_id:
                with open(p, 'rb') as f:
                    res = requests.post(
                        'https://api.imgur.com/3/image',
                        headers={'Authorization': f'Client-ID {imgur_client_id}'},
                        files={'image': (p.name, f, mime)},
                        timeout=20
                    )
                    if res.status_code == 200:
                        data = res.json()
                        if isinstance(data, dict) and data.get('data', {}).get('link'):
                            return data['data']['link']
            return None

        providers_map = {
            'uguu': try_uguu,
            'sxcu': try_sxcu,
            'catbox': try_catbox,
            'imgbb': try_imgbb,
            'imgur': try_imgur
        }

        # Step 4: Build execution queue prioritizing user selection if specified
        order = ['uguu', 'sxcu', 'catbox', 'imgbb', 'imgur']
        pref = (provider or '').strip().lower()
        if pref in providers_map:
            order = [pref] + [k for k in order if k != pref]

        # Step 5: Cycle through mirrors until upload succeeds
        for name in order:
            try:
                url = providers_map[name]()
                if url:
                    return url
            except Exception:
                continue

        # Step 6: Raise API error if all mirror attempts fail
        raise TelegraphAPIError(
            f"Failed to upload local image file '{p.name}' to all image mirrors.\n"
            "Please verify your internet connection or check if proxy is required."
        )

    def process_local_images(self, md_text: str, base_dir: Path = None, provider: str = None) -> str:
        """
        Detects local image file references in Markdown text, uploads them, and replaces local paths with live web URLs.
        Supports Windows absolute paths (C:\\path\\img.png), POSIX paths (/path/img.png), relative paths, and quotes.

        @brief Auto-upload local image file references in Markdown text.
        @param md_text Markdown text body.
        @param base_dir Optional base directory for resolving relative file paths.
        @param provider Optional preferred hoster name ('uguu', 'sxcu', 'catbox', 'imgbb', 'imgur', 'auto').
        @return Updated Markdown text with hosted image URLs.
        @note Modifies Markdown body string; skips remote HTTP/HTTPS/data URLs.
        """
        # Step 1: Default base resolution directory to current working directory
        if base_dir is None:
            base_dir = Path.cwd()

        def replacer_md(match):
            alt_text = match.group(1)
            # Step 2: Sanitize raw path by stripping quotes and angle brackets
            raw_path = match.group(2).strip().strip('"\'<>')
            
            # Step 3: Skip remote HTTP, HTTPS, or base64 data URLs
            if raw_path.startswith(('http://', 'https://', 'data:')):
                return match.group(0)

            # Step 4: Resolve absolute and relative cross-platform file paths
            candidate_path = Path(raw_path)
            if not candidate_path.is_absolute():
                if (base_dir / candidate_path).exists():
                    candidate_path = base_dir / candidate_path
                elif (Path.cwd() / candidate_path).exists():
                    candidate_path = Path.cwd() / candidate_path
            
            # Step 5: Upload valid local file and replace Markdown image reference
            if candidate_path.exists() and candidate_path.is_file():
                print(f"[AUTO-UPLOAD] Uploading local image: {candidate_path.name}...")
                hosted_url = self.upload_file(candidate_path, provider=provider)
                print(f"  Hosted URL: {hosted_url}")
                return f"![{alt_text}]({hosted_url})"

            return match.group(0)

        # Step 6: Scan and replace all Markdown image syntax matches ![alt](src)
        return re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', replacer_md, md_text)

    def revoke_access_token(self) -> dict:
        """
        Revokes the current access token and generates a replacement token.

        @brief Revoke current access token.
        @return Dictionary containing newly generated 'access_token' and 'auth_url'.
        """
        if not self.access_token:
            raise TelegraphAPIError("access_token is required to revoke access token.")
        res = self._request('revokeAccessToken', data={'access_token': self.access_token})
        if res and 'access_token' in res:
            self.access_token = res['access_token']
        return res

    def get_account_info(self, fields: list = None) -> dict:
        """
        Retrieves profile metadata for the authenticated account.

        @brief Fetch account details.
        @param fields Optional list of field strings to request (defaults to all account fields).
        @return Account info dictionary containing requested attributes.
        """
        if not self.access_token:
            raise TelegraphAPIError("access_token is required.")
        if fields is None:
            fields = ['short_name', 'author_name', 'author_url', 'page_count']
        data = {
            'access_token': self.access_token,
            'fields': json.dumps(fields)
        }
        return self._request('getAccountInfo', data=data)

    def create_page(self, title: str, content: list, author_name: str = None, author_url: str = None, return_content: bool = False) -> dict:
        """
        Creates and publishes a new Telegra.ph article page.

        @brief Publish new page on Telegra.ph.
        @param title Page title (1-256 characters).
        @param content List of Telegraph DOM AST node dictionaries.
        @param author_name Optional author name override.
        @param author_url Optional author URL override.
        @param return_content If True, includes full page node content in response.
        @return Published page metadata dictionary containing 'path', 'url', etc.
        """
        if not self.access_token:
            raise TelegraphAPIError("access_token is required to create page.")
        data = {
            'access_token': self.access_token,
            'title': title,
            'content': json.dumps(content),
            'return_content': return_content
        }
        if author_name: data['author_name'] = author_name
        if author_url: data['author_url'] = author_url
        return self._request('createPage', data=data)

    def edit_page(self, path: str, title: str, content: list, author_name: str = None, author_url: str = None, return_content: bool = False) -> dict:
        """
        Updates an existing Telegra.ph article page.

        @brief Update existing page content on Telegra.ph.
        @param path Target page path slug (e.g. 'My-Article-Title-01-01').
        @param title Page title.
        @param content List of Telegraph DOM AST node dictionaries.
        @param author_name Optional author name override.
        @param author_url Optional author URL override.
        @param return_content If True, includes full page node content in response.
        @return Updated page metadata dictionary.
        """
        if not self.access_token:
            raise TelegraphAPIError("access_token is required to edit page.")
        data = {
            'access_token': self.access_token,
            'path': path,
            'title': title,
            'content': json.dumps(content),
            'return_content': return_content
        }
        if author_name: data['author_name'] = author_name
        if author_url: data['author_url'] = author_url
        return self._request('editPage', data=data)

    def get_page(self, path: str, return_content: bool = True) -> dict:
        """
        Fetches an existing Telegra.ph article page by path slug.

        @brief Fetch page content and metadata.
        @param path Target page path slug.
        @param return_content If True, includes full page node content array.
        @return Page details dictionary.
        """
        data = {
            'path': path,
            'return_content': return_content
        }
        return self._request('getPage', data=data)

    def get_page_list(self, offset: int = 0, limit: int = 50) -> dict:
        """
        Retrieves list of articles created under the authenticated account.

        @brief Fetch paginated page list.
        @param offset Pagination offset index (default: 0).
        @param limit Maximum items to return (1-50, default: 50).
        @return Page list dictionary containing 'total_count' and 'pages'.
        """
        if not self.access_token:
            raise TelegraphAPIError("access_token is required to list pages.")
        data = {
            'access_token': self.access_token,
            'offset': offset,
            'limit': limit
        }
        return self._request('getPageList', data=data)

    def get_views(self, path: str, year: int = None, month: int = None, day: int = None, hour: int = None) -> dict:
        """
        Fetches view statistics for a specific page.

        @brief Get page view count.
        @param path Target page path slug.
        @param year Optional filter year (2016-2026).
        @param month Optional filter month (1-12).
        @param day Optional filter day of month (1-31).
        @param hour Optional filter hour of day (0-23).
        @return Dictionary containing 'views' integer count.
        """
        data = {'path': path}
        if year: data['year'] = year
        if month: data['month'] = month
        if day: data['day'] = day
        if hour: data['hour'] = hour
        return self._request('getViews', data=data)

    @staticmethod
    def markdown_to_nodes(md_text: str, page_title: str = None) -> list:
        """
        Converts Markdown string into Telegraph DOM AST nodes, stripping frontmatter and duplicate H1 headers.

        @brief Convert Markdown string to Telegraph DOM AST node list.
        @param md_text Raw Markdown string content.
        @param page_title Optional title string.
        @return List of Telegraph DOM node dictionaries.
        @note Excludes 'nl2br' extension to preserve native standard list item padding.
        """
        # Step 1: Strip YAML frontmatter block (--- title: ... ---) if present
        clean_md = re.sub(r'^---\s*\n.*?\n---\s*\n', '', md_text, flags=re.DOTALL).strip()
        
        # Step 2: Strip leading # Title header to prevent duplicate titles on Telegra.ph
        clean_md = re.sub(r'^#\s+.*?\n', '', clean_md).strip()

        # Step 3: Render Markdown to HTML using sane_lists and extra extensions
        html = markdown.markdown(clean_md, extensions=['extra', 'codehilite', 'sane_lists'])
        return TelegraphManager.html_to_nodes(html)

    @staticmethod
    def html_to_nodes(html_str: str) -> list:
        """
        Converts HTML string into Telegraph DOM AST node list using BeautifulSoup.

        @brief Convert HTML string into Telegraph DOM AST node list.
        @param html_str Raw HTML markup string.
        @return List of Telegraph DOM node dictionaries/strings.
        """
        soup = BeautifulSoup(html_str, 'html.parser')
        nodes = []
        for child in soup.contents:
            node = TelegraphManager._bs4_element_to_node(child)
            if node:
                if isinstance(node, list):
                    nodes.extend(node)
                else:
                    nodes.append(node)
        cleaned = []
        for n in nodes:
            if isinstance(n, str) and not n.strip():
                continue
            cleaned.append(n)
        return cleaned

    @staticmethod
    def _bs4_element_to_node(element):
        """
        Recursive helper to map a BeautifulSoup HTML element/string into a Telegraph DOM AST node.

        @brief Recursively map BS4 DOM element to Telegraph node.
        @param element BeautifulSoup NavigableString or Tag instance.
        @return Node dict, string, list of nodes, or None.
        """
        # Step 1: Handle plain text strings
        if isinstance(element, NavigableString):
            text = str(element)
            parent_tag = element.parent.name.lower() if element.parent else ''
            if parent_tag in ('code', 'pre') or text.strip():
                return text
            return None

        # Step 2: Handle HTML element tags
        if isinstance(element, Tag):
            tag_name = element.name.lower()
            if tag_name in TAG_MAPPING:
                mapped = TAG_MAPPING[tag_name]
                if mapped is None:
                    children = []
                    for child in element.contents:
                        c_node = TelegraphManager._bs4_element_to_node(child)
                        if c_node is not None:
                            if isinstance(c_node, list):
                                children.extend(c_node)
                            else:
                                children.append(c_node)
                    return children
                tag_name = mapped

            if tag_name == 'img':
                src_val = element.attrs.get('src', '')
                alt_val = str(element.attrs.get('alt', '')).strip()
                img_node = {'tag': 'img', 'attrs': {'src': src_val}}
                if alt_val and alt_val.lower() != 'image':
                    return {
                        'tag': 'figure',
                        'children': [
                            img_node,
                            {'tag': 'figcaption', 'children': [alt_val]}
                        ]
                    }
                return img_node

            node = {'tag': tag_name}
            
            # Step 3: Filter permitted attributes (href, src)
            attrs = {}
            for attr, val in element.attrs.items():
                if attr in ALLOWED_ATTRS:
                    if isinstance(val, list):
                        attrs[attr] = " ".join(val)
                    else:
                        attrs[attr] = str(val)
            if attrs:
                node['attrs'] = attrs

            # Step 4: Recursively process child nodes
            children = []
            for child in element.contents:
                c_node = TelegraphManager._bs4_element_to_node(child)
                if c_node is not None:
                    if isinstance(c_node, list):
                        children.extend(c_node)
                    else:
                        children.append(c_node)
            if children:
                node['children'] = children
            return node

        return None

    @staticmethod
    def nodes_to_markdown(nodes: list) -> str:
        """
        Converts a list of Telegraph DOM AST nodes back into a standard Markdown string.

        @brief Reverse convert Telegraph DOM AST nodes into Markdown text.
        @param nodes List of Telegraph DOM node dictionaries/strings.
        @return Markdown text string.
        """
        lines = []
        for node in nodes:
            md_item = TelegraphManager._node_to_md(node)
            if md_item and md_item.strip():
                lines.append(md_item.strip())
        return "\n\n".join(lines)

    @staticmethod
    def _node_to_md(node) -> str:
        """
        Recursive helper to convert an individual Telegraph DOM AST node to Markdown syntax.

        @brief Recursively convert DOM node to Markdown element.
        @param node Telegraph DOM AST node dictionary or text string.
        @return Markdown formatted string element.
        """
        if isinstance(node, str):
            return node
        if isinstance(node, dict):
            tag = node.get('tag', '')
            attrs = node.get('attrs', {})
            children_raw = node.get('children', [])
            
            children_text = "".join([TelegraphManager._node_to_md(c) for c in children_raw]).strip()
            
            if tag in ('h1', 'h2', 'h3'):
                return f"### {children_text}"
            elif tag == 'h4':
                return f"#### {children_text}"
            elif tag in ('b', 'strong'):
                return f"**{children_text}**"
            elif tag in ('i', 'em'):
                return f"*{children_text}*"
            elif tag == 'code':
                return f"`{children_text}`"
            elif tag == 'pre':
                return f"```\n{children_text.strip('`')}\n```"
            elif tag == 'blockquote':
                bq_lines = [f"> {line}" for line in children_text.splitlines() if line.strip()]
                return "\n".join(bq_lines)
            elif tag == 'a':
                href = attrs.get('href', '')
                return f"[{children_text}]({href})"
            elif tag == 'figure':
                img_src = ""
                caption_text = ""
                for c in children_raw:
                    if isinstance(c, dict):
                        if c.get('tag') == 'img':
                            img_src = c.get('attrs', {}).get('src', '')
                        elif c.get('tag') == 'figcaption':
                            caption_text = TelegraphManager._node_to_md(c).strip()
                if img_src:
                    caption_label = caption_text if caption_text else "Image"
                    return f"![{caption_label}]({img_src})"
                return children_text
            elif tag == 'figcaption':
                return children_text
            elif tag == 'img':
                src = attrs.get('src', '')
                return f"![Image]({src})"
            elif tag == 'p':
                return children_text
            elif tag in ('ul', 'ol'):
                items = []
                for c in children_raw:
                    if isinstance(c, dict) and c.get('tag') == 'li':
                        item_text = TelegraphManager._node_to_md(c).strip()
                        items.append(f"- {item_text}")
                return "\n".join(items)
            elif tag == 'li':
                return children_text
            elif tag == 'hr':
                return "---"
            else:
                return children_text
        return ""
