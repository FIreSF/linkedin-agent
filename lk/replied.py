"""Dedup store: one reply per person per post.

Records (post_urn, author_id_or_name, first_reply_at) so the watcher
and queue can block a second reply to the same person on the same post.
"""
import json
import time

from . import config

REPLIED_FILE = config.DATA / "replied.json"


def _load() -> dict:
    if not REPLIED_FILE.exists():
        return {}
    try:
        data = json.loads(REPLIED_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save(data: dict) -> None:
    REPLIED_FILE.parent.mkdir(parents=True, exist_ok=True)
    REPLIED_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def key(post_urn: str, author: str) -> str:
    """Stable dedup key: post URN + normalized author handle."""
    urn = (post_urn or "").strip()
    who = (author or "").strip().lower()
    who = " ".join(who.split())
    return f"{urn}::{who}"


def has_replied(post_urn: str, author: str) -> bool:
    return key(post_urn, author) in _load()


def mark(post_urn: str, author: str, note: str = "") -> dict:
    data = _load()
    k = key(post_urn, author)
    if k not in data:
        record = {
            "post": post_urn,
            "author": author,
            "first_reply_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "first_reply_unix": int(time.time()),
        }
        if note:
            record["note"] = note
        data[k] = record
        _save(data)
    return data[k]


def count() -> int:
    return len(_load())


def all_keys() -> list[str]:
    return list(_load().keys())
