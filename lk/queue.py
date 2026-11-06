"""A small scheduled queue, so replies go out spaced apart instead of in a burst.

Safety rails:
- Only approved items run when LK_REQUIRE_APPROVAL=1 (default).
- Quiet hours: no sending between LK_QUIET_START and LK_QUIET_END.
- Daily reply cap: LK_MAX_REPLIES_PER_DAY (default 5).
- Spacing: LK_REPLY_SPACING_S plus random jitter so sends don't look clockwork.
"""

import json
import os
import random
import time

from . import config

QUEUE_FILE = config.DATA / "queue.json"

PENDING = "pending"
PENDING_APPROVAL = "pending-approval"
APPROVED = "approved"
SENT = "sent"
FAILED = "failed"
CANCELLED = "cancelled"
DRY_RUN = "dry-run"


def _load() -> list[dict]:
    if not QUEUE_FILE.exists():
        return []
    try:
        data = json.loads(QUEUE_FILE.read_text())
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _save(items: list[dict]) -> None:
    QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(items, indent=2, ensure_ascii=False))


def _is_approved(item: dict) -> bool:
    return item.get("approved") is True or item.get("status") in (APPROVED, PENDING)


def _require_approval() -> bool:
    return config.get("LK_REQUIRE_APPROVAL", "1") not in ("0", "false", "no", "off")


def _daily_cap() -> int:
    return int(config.get("LK_MAX_REPLIES_PER_DAY", "5") or 5)


def _spacing() -> int:
    return int(config.get("LK_REPLY_SPACING_S", "360") or 360)


def _jitter() -> float:
    return random.uniform(0, _spacing() * 0.5)


def _in_quiet_hours() -> bool:
    from . import publish

    return publish.in_quiet_hours()


def add(
    kind: str,
    target: str,
    text: str,
    spacing: int | None = None,
    label: str = "",
    draft_id: str = "",
    post_urn: str = "",
    author: str = "",
) -> dict:
    """Add a comment/post to the queue.

    Items default to pending-approval when approval is required.
    Spacing comes from LK_REPLY_SPACING_S + jitter (no burst sending).
    """
    if spacing is None:
        spacing = _spacing()

    items = _load()

    # Dedup: one reply per person per post, even before the first one sends
    if kind == "comment" and author:
        from . import replied

        target_urn = post_urn or target
        if replied.has_replied(target_urn, author):
            raise ValueError(
                f"{author} already got a reply on this post — skipping (one reply per person per post)."
            )
        who = " ".join(author.strip().lower().split())
        for existing in items:
            if existing.get("kind") != "comment":
                continue
            if existing.get("status") in (CANCELLED, FAILED):
                continue
            same_post = (existing.get("post_urn") or existing.get("target") or "") == target_urn
            same_person = " ".join(str(existing.get("author", "")).strip().lower().split()) == who
            if same_post and same_person:
                raise ValueError(
                    f"{author} is already queued for a reply on this post — "
                    "skipping (one reply per person per post)."
                )

    pending = [i["due"] for i in items if i.get("status") in (APPROVED, PENDING)]
    base = max(time.time(), max(pending) if pending else time.time())
    due = base + spacing + _jitter()

    item = {
        "id": f"q{int(time.time() * 1000)}",
        "kind": kind,
        "target": target,
        "text": text,
        "label": label,
        "draft_id": draft_id,
        "post_urn": post_urn or target,
        "author": author,
        "due": due,
        "status": PENDING_APPROVAL if _require_approval() else PENDING,
        "approved": False,
    }
    items.append(item)
    _save(items)
    return item


def approve(item_id: str) -> dict | None:
    items = _load()
    for item in items:
        if item["id"] == item_id and item.get("status") == PENDING_APPROVAL:
            item["status"] = APPROVED
            item["approved"] = True
            _save(items)
            return item
    return None


def reject(item_id: str) -> bool:
    items = _load()
    for item in items:
        if item["id"] == item_id and item.get("status") == PENDING_APPROVAL:
            item["status"] = CANCELLED
            item["approved"] = False
            _save(items)
            return True
    return False


def listing(status: str = "all") -> list[dict]:
    items = _load()
    if status == "all":
        return items
    if status == "pending":
        return [i for i in items if i.get("status") in (PENDING, APPROVED)]
    return [i for i in items if i.get("status") == status]


def due_items(now: float | None = None) -> list[dict]:
    now = now or time.time()
    return [
        i
        for i in _load()
        if i.get("status") in (PENDING, APPROVED)
        and i.get("due", 0) <= now
        and _is_approved(i)
    ]


def next_due() -> float | None:
    pending = [i["due"] for i in _load() if i.get("status") in (PENDING, APPROVED) and _is_approved(i)]
    return min(pending) if pending else None


def _set_status(item_id: str, status: str, note: str = "") -> None:
    items = _load()
    for item in items:
        if item["id"] == item_id:
            item["status"] = status
            if note:
                item["note"] = note
    _save(items)


def cancel(item_id: str) -> bool:
    items = _load()
    for item in items:
        if item["id"] == item_id and item.get("status") in (PENDING, PENDING_APPROVAL, APPROVED):
            item["status"] = CANCELLED
            _save(items)
            return True
    return False


def _today_replies() -> int:
    # Reuse the publish usage file that is already tracking daily counts
    from . import publish

    return publish.daily_reply_count()


def run(dry_run: bool = False, loop: bool = False, poll: int = 30) -> tuple[int, int]:
    """Post everything due and approved. Returns (sent, failed)."""
    from . import publish, replied

    sent = failed = 0
    while True:
        if _in_quiet_hours() and not dry_run:
            label = f"quiet hours {config.get('LK_QUIET_START','22')}:00–{config.get('LK_QUIET_END','8')}:00"
            print(f"[{time.strftime('%H:%M:%S')}] {label} — holding sends")
            if not loop:
                return sent, failed
            time.sleep(poll)
            continue

        ready = due_items()

        # Daily cap: stop sending replies once max hit
        if _today_replies() >= _daily_cap() and any(i["kind"] == "comment" for i in ready):
            print(f"[{time.strftime('%H:%M:%S')}] daily reply cap ({_daily_cap()}) reached — holding")
            if not loop:
                return sent, failed
            time.sleep(poll)
            continue

        # If approval gate on, surface anything still pending approval
        pending_approval = [i for i in _load() if i.get("status") == PENDING_APPROVAL]
        if pending_approval:
            print(f"[!] {len(pending_approval)} item(s) awaiting approval — run 'lk queue approve <id>'")

        for item in ready:
            # Final approval check (defense in depth)
            if _require_approval() and not _is_approved(item):
                continue

            # Dedup re-check before sending (in case data changed)
            if item["kind"] == "comment" and item.get("author"):
                if replied.has_replied(item.get("post_urn", item["target"]), item["author"]):
                    _set_status(item["id"], CANCELLED, "already replied to this author on this post")
                    print(f"[!] {item['id']} skipped — already replied to {item['author']} on this post")
                    continue

            if _today_replies() >= _daily_cap() and item["kind"] == "comment":
                _set_status(item["id"], APPROVED, "daily cap hit — will retry tomorrow")
                # Hold in approved so it can go tomorrow instead of failing
                print(f"[{time.strftime('%H:%M:%S')}] daily cap — holding {item['id']}")
                break

            try:
                if item["kind"] == "comment":
                    publish.publish_comment(item["target"], item["text"], dry_run=dry_run)
                else:
                    publish.publish_post(item["text"], dry_run=dry_run)

                _set_status(item["id"], SENT if not dry_run else DRY_RUN, "")

                if item["kind"] == "comment" and item.get("author"):
                    replied.mark(item.get("post_urn", item["target"]), item["author"], note=item.get("label", ""))

                sent += 1
                stamp = time.strftime("%H:%M:%S")
                print(f"[{stamp}] sent {item['id']} ({item['kind']}) {item.get('label', '')[:50]}")
            except publish.APIError as exc:
                _set_status(item["id"], FAILED, str(exc))
                failed += 1
                print(f"[!] {item['id']} failed: {exc}")

        if not loop:
            break

        wait = next_due()
        nap = poll if wait is None else max(1, min(poll, int(wait - time.time())))
        time.sleep(nap)
    return sent, failed
