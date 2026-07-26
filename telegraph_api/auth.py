"""
Telegra.ph Automated Auth Token Extractor Script

Responsibility:
    Automates extracting `tph_token` cookies from fresh, unclicked Telegram `@Telegraph`
    login authentication links (`https://edit.telegra.ph/auth/<code >`) and saves the token
    to the local `.env` configuration file.

Non-Responsibility:
    Does not publish articles or manage Telegraph page contents.

Layer:
    Layer 3 (Deterministic Execution Tool)

Lifetime & Threading Constraints:
    Runs synchronously via CLI invocation (`python -m telegraph_api.auth <URL>`). Single-threaded.
    Handles HTTP GET requests with custom User-Agent headers and optional proxy configurations.
"""

import os
import sys
import re
import requests
from pathlib import Path
from dotenv import load_dotenv

# Define path to environment file located at project root
ENV_PATH = Path(__file__).parent.parent / '.env'
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

def extract_token_from_auth_url(auth_input: str) -> str:
    """
    Extracts the `tph_token` cookie string by sending HTTP GET requests to a Telegram auth URL.

    @brief Extract `tph_token` cookie from a Telegra.ph auth URL or code string.
    
    Why this exists:
        Telegram `@Telegraph` bot issues single-use auth URLs. Opening them in a browser
        consumes the token. This script performs non-browser HTTP GET inspection to extract
        the `tph_token` cookie and store it before it expires.

    @param auth_input Full auth URL (e.g. `https://edit.telegra.ph/auth/code`) or raw auth code string.
    @return Extracted token string if found; None if extraction fails or token expired.
    @side_effects Makes outbound HTTP GET requests over network/proxy.
    @note Auth URLs expire instantly upon initial server consumption. Must pass fresh links.
    """
    # Step 1: Normalize input and extract auth code via regex pattern
    auth_input = auth_input.strip()
    match = re.search(r'(?:edit\.)?telegra\.ph/auth/([a-zA-Z0-9]+)', auth_input)
    if match:
        auth_code = match.group(1)
    else:
        auth_code = auth_input

    # Step 2: Prepare candidate domain endpoints for retry loop
    urls_to_try = [
        f"https://edit.telegra.ph/auth/{auth_code}",
        f"https://telegra.ph/auth/{auth_code}"
    ]

    # Initialize requests session with browser-like headers to prevent request blocking
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    })

    # Step 3: Apply proxy configuration if present in environment variables
    proxy_url = os.getenv('TELEGRAPH_PROXY') or os.getenv('HTTPS_PROXY') or os.getenv('HTTP_PROXY')
    if proxy_url:
        print(f"Using proxy: {proxy_url}")
        session.proxies = {'http': proxy_url, 'https': proxy_url}

    # Step 4: Iterate over auth endpoint candidates to catch token in headers, cookies, or body
    for url in urls_to_try:
        print(f"Checking URL: {url} ...")
        try:
            # First attempt without auto-redirects to capture raw 302 'Set-Cookie' header
            res_no_redirect = session.get(url, allow_redirects=False, timeout=15)
            
            # Inspect raw Set-Cookie header for tph_token regex match
            set_cookie_header = res_no_redirect.headers.get('Set-Cookie', '')
            match_set_cookie = re.search(r'tph_token=([a-zA-Z0-9_-]+)', set_cookie_header)
            if match_set_cookie:
                return match_set_cookie.group(1)

            # Follow redirects if initial response did not yield token directly
            response = session.get(url, allow_redirects=True, timeout=15)
            
            # Check active session cookie jar
            token = session.cookies.get('tph_token')
            if token:
                return token

            # Traverse redirect history headers for Set-Cookie headers
            for r in response.history:
                if 'tph_token' in r.cookies:
                    return r.cookies.get('tph_token')
                sc = r.headers.get('Set-Cookie', '')
                m = re.search(r'tph_token=([a-zA-Z0-9_-]+)', sc)
                if m:
                    return m.group(1)

            # Fall back to regex scan over final HTML body text
            match_body = re.search(r'tph_token=([a-zA-Z0-9_-]+)', response.text)
            if match_body:
                return match_body.group(1)

        except Exception as e:
            # Log network failure gracefully and proceed to next mirror URL
            print(f"Warning: {url} attempt gave error: {e}")

    return None

def main():
    """
    CLI entry point for auth.py.
    
    @brief Parses command line arguments, calls token extractor, and saves token to `.env`.
    """
    # Step 1: Validate argument count
    if len(sys.argv) < 2:
        print("Usage: python -m telegraph_api.auth <AUTH_URL_OR_CODE>")
        print("Example: python -m telegraph_api.auth https://edit.telegra.ph/auth/YOUR_AUTH_CODE_HERE")
        sys.exit(1)

    auth_url = sys.argv[1]
    try:
        # Step 2: Attempt token extraction and write to .env file if successful
        token = extract_token_from_auth_url(auth_url)
        if token:
            print("\nSuccess! Found valid access_token:")
            print(f"  Token: {token}")
            
            env_content = f"TELEGRAPH_ACCESS_TOKEN={token}\n"
            ENV_PATH.write_text(env_content, encoding='utf-8')
            print(f"\nSaved token to {ENV_PATH.resolve()}")
            print("\nYou can now run:")
            print("  python telegraph.py account")
            print("  python telegraph.py list")
            print("  python telegraph.py pull-all")
        else:
            # Step 3: Print helpful troubleshooting instructions if token extraction failed
            print("\nCould not extract tph_token automatically.", file=sys.stderr)
            print("Reason: Auth links expire immediately once clicked or opened.", file=sys.stderr)
            print("\nHow to fix:", file=sys.stderr)
            print("1. Go to Telegram @Telegraph bot.", file=sys.stderr)
            print("2. Click 'Log in on this device' to generate a FRESH link.", file=sys.stderr)
            print("3. DO NOT click the link in your browser! Copy it directly.", file=sys.stderr)
            print("4. Pass that FRESH link into this command.", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
