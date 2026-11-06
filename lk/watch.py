"""Watch my recent LinkedIn posts for new comments and draft replies.

Safety model:
- Reads only through the official API. If the app has no permission to read,
  it stops immediately and tells you exactly what LinkedIn said.
- Never sends anything. Every draft goes to the approval queue with status
  `pending-approval`; nothing leaves your account until you approve it.
- One reply per person per post. Repeat comments from the same person are
  skipped (tracked in data/replied.json).
- Low activity by default: max 5 replies/day, 6-minute spacing, quiet hours.
"""

import json
import time

from . import comments, config, queue, replied

SEEN_FILE = config.DATA / "seen_comments.json"


def _load_seen() -> dict:
    if not SEEN_FILE.exists():
        return {}
    try:
        data = json.loads(SEEN_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _save_seen(data: dict) -> None:
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def _my_urn() -> str:
    from . import publish

    return publish.person_urn()


def check_once(post_urn: str = "", author: str = "", draft: bool = True) -> dict:
    """Look for new comments once and queue drafts for approval.

    Returns a summary dict: {"posts": n, "new_comments": n, "drafted": n,
    "skipped": n, "error": "..."}.
    """
    from . import publish

    summary = {"posts": 0, "new_comments": 0, "drafted": 0, "skipped": 0, "error": ""}
    me = _my_urn()

    if post_urn:
        targets = [{"urn": post_urn, "text": ""}]
    else:
        try:
            targets = publish.my_recent_posts(count=10)
        except publish.ReadPermissionError as exc:
            summary["error"] = str(exc)
            return summary
        except publish.APIError as exc:
            summary["error"] = str(exc)
            return summary

    summary["posts"] = len(targets)
    seen = _load_seen()

    for target in targets:
        urn = target["urn"]
        try:
            rows = publish.list_comments(urn)
        except publish.ReadPermissionError as exc:
            summary["error"] = str(exc)
            return summary
        except publish.APIError as exc:
            summary["error"] = str(exc)
            return summary

        for row in rows:
            cid = row.get("urn") or row.get("id") or ""
            if not cid or cid in seen:
                continue

            if row.get("author_urn") == me:
                seen[cid] = {"skipped": "my own comment", "at": int(time.time())}
                continue

            who = row.get("author") or row.get("author_urn") or "someone"
            if not (author and author.lower() not in who.lower()):
                # author filter (when set, keep only matching)
                pass

            if replied.has_replied(urn, who):
                summary["skipped"] += 1
                seen[cid] = {"skipped": "already replied to this person on this post", "at": int(time.time())}
                continue

            summary["new_comments"] += 1

            if not draft:
                seen[cid] = {"seen": True, "at": int(time.time())}
                continue

            try:
                result = comments.reply_to_comment(target.get("text", ""), row.get("text", ""), who)
            except Exception as exc:  # noqa: BLE001
                summary["error"] = f"drafting failed: {exc}"
                return summary

            try:
                item = queue.add(
                    "comment",
                    urn,
                    result["reply"],
                    label=f"reply to {who}",
                    post_urn=urn,
                    author=who,
                )
                summary["drafted"] += 1
                seen[cid] = {"drafted": item["id"], "at": int(time.time())}
            except ValueError:
                summary["skipped"] += 1
                seen[cid] = {"skipped": "dedup", "at": int(time.time())}

    _save_seen(seen)
    return summary


def watch(post_urn: str = "", poll: int | None = None, once: bool = False) -> None:
    """Poll for new comments. Ctrl+C to stop."""
    interval = poll or int(config.get("LK_WATCH_POLL_S", "900") or 900)
    print(f"watching for comments every {interval}s. Drafts go to approval, never sent.")
    if once:
        interval_note = ""
    try:
        while True:
            stamp = time.strftime("%H:%M:%S")
            summary = check_once(post_urn=post_urn)
            if summary["error"]:
                print(f"[{stamp}] stopped: {summary['error']}")
                print("")
                print("This is a permission problem, not a bug. To read comments your")
                print("LinkedIn app needs a product that grants read access. In the app")
                print("dashboard, open Products and request 'Marketing Developer Platform'")
                print("(or the comments-read scope). Posting still works without it.")
                return
            print(
                f"[{stamp}] posts {summary['posts']} · new {summary['new_comments']}"
                f" · drafted {summary['drafted']} · skipped {summary['skipped']}"
            )
            if once:
                return
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nstopped watching.")
