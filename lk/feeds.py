"""Feed watcher: collect articles from RSS/Atom feeds and build a local digest.

Public sources only. No browser, no LinkedIn, no account access.
"""

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from . import config

FEEDS_FILE = config.DATA / "feeds.json"
SEEN_FILE = config.DATA / "seen.json"
DIGEST_DIR = config.DATA / "digest"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
ATOM = "{http://www.w3.org/2005/Atom}"

DEFAULT_FEEDS = {
    "Krebs on Security": "https://krebsonsecurity.com/feed/",
    "BleepingComputer": "https://www.bleepingcomputer.com/feed/",
    "The Hacker News": "https://feeds.feedburner.com/TheHackersNews",
    "Cloudflare Blog": "https://blog.cloudflare.com/rss/",
    "AWS Security": "https://aws.amazon.com/blogs/security/feed/",
    "Microsoft Security": "https://www.microsoft.com/en-us/security/blog/feed/",
    "Schneier on Security": "https://www.schneier.com/feed/atom/",
}

_TAGS = re.compile(r"<[^>]+>")


# ── feed list ────────────────────────────────────────────────────────────


def load_feeds() -> dict[str, str]:
    if not FEEDS_FILE.exists():
        save_feeds(DEFAULT_FEEDS)
        return dict(DEFAULT_FEEDS)
    try:
        data = json.loads(FEEDS_FILE.read_text())
    except json.JSONDecodeError:
        return dict(DEFAULT_FEEDS)
    return data if isinstance(data, dict) else dict(DEFAULT_FEEDS)


def save_feeds(feeds: dict[str, str]) -> None:
    FEEDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FEEDS_FILE.write_text(json.dumps(feeds, indent=2))


def add_feed(url: str, name: str = "") -> str:
    feeds = load_feeds()
    label = name or re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    feeds[label] = url
    save_feeds(feeds)
    return label


def remove_feed(name: str) -> bool:
    feeds = load_feeds()
    if name in feeds:
        del feeds[name]
        save_feeds(feeds)
        return True
    matches = [k for k in feeds if name.lower() in k.lower()]
    if len(matches) == 1:
        del feeds[matches[0]]
        save_feeds(feeds)
        return True
    return False


# ── parsing ──────────────────────────────────────────────────────────────


def _clean(text: str, limit: int = 220) -> str:
    text = _TAGS.sub(" ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _rss_date(raw: str) -> str:
    if not raw:
        return ""
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return ""


def fetch_feed(url: str, timeout: int = 15) -> list[dict]:
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except (requests.RequestException, ET.ParseError):
        return []

    items = []
    if root.tag.endswith("feed"):  # Atom
        for entry in root.findall(f"{ATOM}entry"):
            link_el = entry.find(f"{ATOM}link")
            items.append(
                {
                    "title": _clean(entry.findtext(f"{ATOM}title") or "", 200),
                    "link": link_el.get("href", "") if link_el is not None else "",
                    "published": _rss_date(
                        entry.findtext(f"{ATOM}published") or entry.findtext(f"{ATOM}updated") or ""
                    ),
                    "summary": _clean(entry.findtext(f"{ATOM}summary") or entry.findtext(f"{ATOM}content") or ""),
                }
            )
    else:
        channel = root.find("channel")
        source = channel if channel is not None else root
        for item in source.findall("item"):
            items.append(
                {
                    "title": _clean(item.findtext("title") or "", 200),
                    "link": (item.findtext("link") or "").strip(),
                    "published": _rss_date(item.findtext("pubDate") or ""),
                    "summary": _clean(item.findtext("description") or ""),
                }
            )
    return [i for i in items if i["title"] and i["link"]]


# ── seen state ───────────────────────────────────────────────────────────


def _seen() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_FILE.read_text()))
    except json.JSONDecodeError:
        return set()


def _mark_seen(links: list[str]) -> None:
    seen = list(dict.fromkeys(list(_seen()) + links))[-3000:]
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(seen))


# ── digest ───────────────────────────────────────────────────────────────


def _age(published: str) -> str:
    if not published:
        return "unknown"
    try:
        when = datetime.fromisoformat(published)
    except ValueError:
        return "unknown"
    delta = datetime.now(timezone.utc) - when
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "just now"
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def _topics() -> list[str]:
    raw = config.get("LK_TOPICS", "")
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


def _score(item: dict, topics: list[str]) -> int:
    if not topics:
        return 0
    haystack = (item["title"] + " " + item.get("summary", "")).lower()
    return sum(1 for t in topics if t in haystack)


def collect(hours: int = 48, top: int = 4, include_seen: bool = False) -> dict:
    feeds = load_feeds()
    seen = _seen()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    topics = _topics()

    groups, failures, fresh = [], [], []
    for name, url in feeds.items():
        items = fetch_feed(url)
        if not items:
            failures.append(name)
            continue

        kept = []
        for item in items:
            if not include_seen and item["link"] in seen:
                continue
            published = item.get("published", "")
            if published:
                try:
                    if datetime.fromisoformat(published) < cutoff:
                        continue
                except ValueError:
                    pass
            kept.append(item)

        kept.sort(key=lambda i: (_score(i, topics), i.get("published", "")), reverse=True)
        kept = kept[:top]
        if kept:
            groups.append({"name": name, "url": url, "items": kept})
            fresh.extend(i["link"] for i in kept)

    return {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "hours": hours,
        "groups": groups,
        "failures": failures,
        "new_links": fresh,
        "count": sum(len(g["items"]) for g in groups),
    }


def render(digest: dict) -> str:
    lines = [f"Digest — {digest['generated']}", f"New items: {digest['count']} (last {digest['hours']}h)", ""]
    number = 1
    for group in digest["groups"]:
        lines.append(f"{group['name']}")
        for item in group["items"]:
            lines.append(f"  {number:>2}. {item['title']}  ({_age(item.get('published', ''))})")
            lines.append(f"      {item['link']}")
            if item.get("summary"):
                lines.append(f"      {item['summary'][:160]}")
            item["_number"] = number
            number += 1
        lines.append("")
    if digest["failures"]:
        lines.append(f"Unreachable feeds: {', '.join(digest['failures'])}")
        lines.append("")
    lines.append('Turn one into a post:  lk brief --url "<link>"')
    return "\n".join(lines)


def save(digest: dict, text: str) -> Path:
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    path = DIGEST_DIR / f"{datetime.now().strftime('%Y-%m-%d-%H%M')}.md"
    path.write_text(text + "\n")
    (DIGEST_DIR / "latest.md").write_text(text + "\n")
    _mark_seen(digest["new_links"])
    return path
