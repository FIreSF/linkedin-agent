"""Free web search (DuckDuckGo HTML) so the agent can look things up before writing."""

import html
import re
from urllib.parse import parse_qs, unquote, urlparse

import requests

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

_RESULT = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.S,
)
_SNIPPET = re.compile(r'class="result__snippet"[^>]*>(?P<snippet>.*?)</a>', re.S)
_TAGS = re.compile(r"<[^>]+>")


def _clean(fragment: str) -> str:
    return html.unescape(_TAGS.sub("", fragment)).strip()


def _real_url(href: str) -> str:
    if href.startswith("//"):
        href = "https:" + href
    if "duckduckgo.com/l/" in href:
        query = parse_qs(urlparse(href).query)
        if "uddg" in query:
            return unquote(query["uddg"][0])
    return href


def web(query: str, limit: int = 5) -> list[dict]:
    """Return [{title, url, snippet}]. Never raises; returns [] on failure."""
    try:
        resp = requests.post(
            "https://html.duckduckgo.com/html/",
            data={"q": query},
            headers={"User-Agent": UA},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException:
        return []

    body = resp.text
    titles = list(_RESULT.finditer(body))
    snippets = list(_SNIPPET.finditer(body))

    results = []
    for i, match in enumerate(titles[:limit]):
        snippet = _clean(snippets[i].group("snippet")) if i < len(snippets) else ""
        results.append(
            {
                "title": _clean(match.group("title")),
                "url": _real_url(match.group("href")),
                "snippet": snippet,
            }
        )
    return results


def as_context(results: list[dict], limit: int = 4) -> str:
    if not results:
        return ""
    lines = []
    for r in results[:limit]:
        lines.append(f"- {r['title']} ({r['url']})\n  {r['snippet']}")
    return "\n".join(lines)
