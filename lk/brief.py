"""Research a topic on the public web and turn it into a post brief.

Reads public pages only. Never touches LinkedIn.
"""

import html as html_lib
import json
import re
import time
from pathlib import Path

import requests

from . import config, llm, search

BRIEFS = config.DATA / "briefs"
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
SKIP = re.compile(r"<(/?(script|style|noscript|svg|head|nav|footer|form))[^>]*>.*?</\2>", re.I | re.S)


def _extract(html: str) -> str:
    html = SKIP.sub(" ", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr)>", "\n", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    # Drop navigation furniture that survives extraction.
    junk = re.compile(
        r"^(skip to (main )?content|skip to navigation|menu|search|home|sign in|log in|subscribe)$",
        re.I,
    )
    lines = [line.strip() for line in text.splitlines() if line.strip() and not junk.match(line.strip())]
    return "\n".join(lines)


def _get(url: str) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=15)
        if resp.status_code >= 400 or "text/html" not in resp.headers.get("content-type", ""):
            return ""
        return resp.text
    except requests.RequestException:
        return ""


def title_of(html: str) -> str:
    for pattern in (
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
        r"<title[^>]*>(.*?)</title>",
        r"<h1[^>]*>(.*?)</h1>",
    ):
        match = re.search(pattern, html, re.I | re.S)
        if match:
            title = html_lib.unescape(re.sub(r"\s+", " ", match.group(1))).strip()
            title = re.split(r"\s+[|\-–—]\s+", title)[0].strip()
            if len(title) > 8:
                return title[:100]
    return ""


def fetch(url: str, limit: int = 4000) -> str:
    html = _get(url)
    return _extract(html)[:limit] if html else ""


def research(query: str, pages: int = 3) -> list[dict]:
    """Search, then read the top pages. Returns [{title, url, text}]."""
    found = search.web(query, limit=pages + 2)
    sources = []
    for hit in found:
        if len(sources) >= pages:
            break
        body = fetch(hit["url"])
        if len(body) < 250:
            continue
        sources.append({"title": hit["title"], "url": hit["url"], "text": body})
    return sources


def build(query: str, pages: int = 3) -> dict:
    sources = research(query, pages)
    if not sources:
        raise ValueError(
            "Could not read any pages for that query. Try different words, "
            "or write the post with: lk post \"topic\""
        )
    return _brief(query, sources)


def build_url(url: str, query: str = "") -> dict:
    """Brief a single article you picked from a digest."""
    html = _get(url)
    if not html:
        raise ValueError(f"Could not read that page: {url}")
    text = _extract(html)[:8000]
    if len(text) < 250:
        raise ValueError(f"Page had no readable text: {url}")
    title = title_of(html) or query or url
    return _brief(query or title, [{"title": title, "url": url, "text": text}])


def _brief(query: str, sources: list[dict]) -> dict:
    material = "\n\n".join(
        f"SOURCE {i}: {s['title']} ({s['url']})\n{s['text'][:2500]}"
        for i, s in enumerate(sources, 1)
    )
    prompt = (
        f"Topic: {query}\n\n{material}\n\n"
        "Build a brief I can write a LinkedIn post from. "
        "Use only facts present in the sources. If a number is missing, say so rather than inventing it.\n"
        'Return JSON: {"facts": ["5-8 concrete facts, each with a number, name or timeframe where the source gives one"], '
        '"angles": ["3 takes I could argue, specific not generic"], '
        '"hooks": ["3 candidate first lines, under 12 words, no cliches"]}'
    )
    messages = [
        {
            "role": "system",
            "content": "You are a research assistant. You never invent facts. Return only valid JSON.",
        },
        {"role": "user", "content": prompt},
    ]
    data = llm.chat_json(messages, temperature=0.4, max_tokens=900)

    return {
        "query": query,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "facts": [str(f).strip() for f in data.get("facts", [])][:8],
        "angles": [str(a).strip() for a in data.get("angles", [])][:3],
        "hooks": [str(h).strip() for h in data.get("hooks", [])][:3],
        "sources": [{"title": s["title"], "url": s["url"]} for s in sources],
    }


def slug(text: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]
    return base or "brief"


def save(brief: dict) -> Path:
    BRIEFS.mkdir(parents=True, exist_ok=True)
    path = BRIEFS / f"{slug(brief['query'])}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps(brief, indent=2, ensure_ascii=False))
    return path


def latest() -> dict | None:
    if not BRIEFS.exists():
        return None
    files = sorted(BRIEFS.glob("*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text())


def load(key: str) -> dict:
    """Load by full id, prefix, or 'latest'."""
    if key in ("", "latest"):
        brief = latest()
        if not brief:
            raise KeyError("No briefs saved yet. Run: lk brief \"topic\"")
        return brief
    if BRIEFS.exists():
        for path in sorted(BRIEFS.glob("*.json"), reverse=True):
            if path.stem == key or path.stem.startswith(key):
                return json.loads(path.read_text())
    raise KeyError(f"No brief matching '{key}'.")


def as_context(brief: dict, limit: int = 1600) -> str:
    text = (
        "Researched facts:\n"
        + "\n".join(f"- {f}" for f in brief.get("facts", []))
        + "\n\nAngles:\n"
        + "\n".join(f"- {a}" for a in brief.get("angles", []))
        + "\n\nCandidate hooks:\n"
        + "\n".join(f"- {h}" for h in brief.get("hooks", []))
    )
    return text[:limit]


def render(brief: dict) -> str:
    lines = [f"Brief: {brief['query']}", f"({brief['created']})", ""]
    lines.append("Facts")
    for f in brief.get("facts", []):
        lines.append(f"  - {f}")
    lines.append("")
    lines.append("Angles")
    for a in brief.get("angles", []):
        lines.append(f"  - {a}")
    lines.append("")
    lines.append("Candidate hooks")
    for h in brief.get("hooks", []):
        lines.append(f"  - {h}")
    lines.append("")
    lines.append("Sources")
    for s in brief.get("sources", []):
        lines.append(f"  - {s['title']}\n    {s['url']}")
    return "\n".join(lines)
