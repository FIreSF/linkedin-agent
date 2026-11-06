"""Draft storage. Every draft is a JSON record plus a plain .txt for easy copying."""

import json
import os
import time

from . import config


def _ensure() -> None:
    config.DRAFTS.mkdir(parents=True, exist_ok=True)


def new_id(kind: str) -> str:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{kind}-{os.urandom(2).hex()}"


def save(kind: str, title: str, text: str, meta: dict | None = None) -> dict:
    _ensure()
    did = new_id(kind)
    record = {
        "id": did,
        "kind": kind,
        "title": title,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        "status": "draft",
        "chars": len(text),
        "text": text,
        "meta": meta or {},
    }
    (config.DRAFTS / f"{did}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    (config.DRAFTS / f"{did}.txt").write_text(text + "\n")
    return record


def all_drafts(status: str | None = None) -> list[dict]:
    _ensure()
    rows = []
    for path in sorted(config.DRAFTS.glob("*.json"), reverse=True):
        try:
            rec = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if status and rec.get("status") != status:
            continue
        rows.append(rec)
    return rows


def find(prefix: str) -> dict:
    matches = [r for r in all_drafts() if r["id"].startswith(prefix)]
    if not matches:
        raise KeyError(f"No draft matching '{prefix}'.")
    if len(matches) > 1:
        raise KeyError(
            f"'{prefix}' matches {len(matches)} drafts. Use more characters: "
            + ", ".join(m["id"] for m in matches[:5])
        )
    return matches[0]


def set_status(prefix: str, status: str) -> dict:
    rec = find(prefix)
    rec["status"] = status
    path = config.DRAFTS / f"{rec['id']}.json"
    path.write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return rec


def update_text(prefix: str, text: str) -> dict:
    """Replace a draft's text, e.g. after you edited it before posting."""
    rec = find(prefix)
    rec["text"] = text.strip()
    rec["chars"] = len(rec["text"])
    rec["edited"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (config.DRAFTS / f"{rec['id']}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    (config.DRAFTS / f"{rec['id']}.txt").write_text(rec["text"] + "\n")
    return rec


def set_image(prefix: str, path: str, alt: str = "") -> dict:
    """Attach (or replace) an image on a draft."""
    rec = find(prefix)
    rec["image"] = {"path": str(path), "alt": alt.strip()}
    (config.DRAFTS / f"{rec['id']}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return rec


def clear_image(prefix: str) -> dict:
    rec = find(prefix)
    rec.pop("image", None)
    (config.DRAFTS / f"{rec['id']}.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False))
    return rec
