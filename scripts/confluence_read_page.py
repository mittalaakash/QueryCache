"""Smoke test: fetch one Confluence Cloud page with an API token.

Reads CONFLUENCE_BASE_URL, CONFLUENCE_EMAIL, CONFLUENCE_TOKEN from .env
(or the environment).

Usage:
    python scripts/confluence_read_page.py            # list available pages
    python scripts/confluence_read_page.py <page_id>  # fetch one page
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

from dotenv import load_dotenv


load_dotenv()


class _Text(HTMLParser):
    """Storage-format XHTML -> plain text; newline at block boundaries."""

    BLOCKS = {"p", "br", "hr", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "div", "ul", "ol", "table"}

    def __init__(self):
        super().__init__()
        self.out: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCKS:
            self.out.append("\n")
        if tag == "li":
            self.out.append("- ")

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self.out.append(" | ")
        elif tag in self.BLOCKS:
            self.out.append("\n")

    def handle_data(self, data):
        self.out.append(data)


def to_text(xhtml: str) -> str:
    parser = _Text()
    parser.feed(xhtml)
    lines = (line.strip() for line in "".join(parser.out).splitlines())
    # <li><p>..</p></li> leaves the "- " marker alone on a line; glue it to the next.
    return "\n".join(line for line in lines if line).replace("-\n", "- ")


def _get(base_url: str, email: str, token: str, url: str) -> dict:
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    req = urllib.request.Request(
        url, headers={"Authorization": f"Basic {auth}", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_page(base_url: str, email: str, token: str, page_id: str) -> dict:
    return _get(
        base_url,
        email,
        token,
        f"{base_url.rstrip('/')}/api/v2/pages/{page_id}?body-format=storage",
    )


def list_pages(
    base_url: str, email: str, token: str, max_pages: int = 100
) -> list[dict]:
    """Follows the cursor `_links.next` until max_pages are collected."""
    root = base_url.rstrip("/")
    # `next` is a path relative to the site root, e.g. /wiki/api/v2/pages?cursor=...
    site = root.removesuffix("/wiki")
    url = f"{root}/api/v2/pages?limit=50&status=current"
    pages: list[dict] = []
    while url and len(pages) < max_pages:
        data = _get(base_url, email, token, url)
        pages += data["results"]
        nxt = data.get("_links", {}).get("next")
        url = f"{site}{nxt}" if nxt else None
    return pages[:max_pages]


def main() -> int:
    try:
        base_url, email, token = (
            os.environ[k]
            for k in ("CONFLUENCE_BASE_URL", "CONFLUENCE_EMAIL", "CONFLUENCE_TOKEN")
        )
    except KeyError as e:
        print(f"missing env var: {e}")
        return 2

    try:
        if len(sys.argv) == 1:
            pages = list_pages(base_url, email, token)
            print(f"{len(pages)} page(s):")
            for p in pages:
                print(
                    f"  {p['id']:>12}  v{p['version']['number']:<3} space={p['spaceId']}  {p['title']}"
                )
            return 0
        page = fetch_page(base_url, email, token, sys.argv[1])
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.read().decode()[:300]}")
        return 1

    body = page["body"]["storage"]["value"]
    print(f"keys:      {list(page.keys())}")
    print(f"id:      {page['id']}")
    print(f"title:   {page['title']}")
    print(f"version: {page['version']['number']}")
    print(f"\n{to_text(body)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
