"""A weekly plan built from your topics. Suggestions only — it never posts.

Low activity on purpose: three posts a week, a reply window after each, and
short engagement blocks. More than that starts to look like a bot.
"""

import time

from . import config, store

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Tuesday, Wednesday, Thursday mornings get the most reach.
POST_DAYS = [1, 2, 3]
POST_TIME = "08:30"


def _topics() -> list[str]:
    raw = config.get("LK_TOPICS", "")
    items = [t.strip() for t in raw.split(",") if t.strip()]
    return items or ["what you are building", "a mistake you fixed", "a tool you rely on"]


def build(posts_per_week: int = 3, start: time.struct_time | None = None) -> str:
    topics = _topics()
    start = start or time.localtime()
    today = start.tm_wday
    days = set(POST_DAYS[: max(1, min(posts_per_week, 5))])

    lines: list[str] = []
    lines.append(f"Week plan · {time.strftime('%d %b %Y', start)}")
    lines.append("")
    lines.append("3 posts a week. Reply to comments within an hour. Nothing here is automatic.")
    lines.append("")

    topic_index = 0
    for offset in range(7):
        weekday = (today + offset) % 7
        stamp = time.strftime("%d %b", time.localtime(time.mktime(start) + offset * 86400))
        name = WEEKDAYS[weekday]
        marker = "  ← today" if offset == 0 else ""
        lines.append(f"{name} {stamp}{marker}")

        if weekday in days:
            topic = topics[topic_index % len(topics)]
            topic_index += 1
            now_hour = int(time.strftime("%H"))
            late = offset == 0 and now_hour >= 9
            if late:
                lines.append(f"  POST    missed today's {POST_TIME} slot — carry this to the next post day")
                lines.append(f"          topic: {topic}")
            else:
                lines.append(f"  POST    {POST_TIME}   topic: {topic}")
            lines.append("          shape: hook → one specific thing that happened → what changed")
            lines.append("  CHECK   before posting: lk coach <id> · lk humanize <id> · lk safe <id>")
            lines.append("  REPLY   09:30–10:30   answer every comment (queue caps at 5/day)")
        elif weekday == 4:
            lines.append("  BANK    20 min   draft next week's post from a real thing that happened")
            lines.append("  ENGAGE  10 min   comment on 2 posts in your topic area")
        elif weekday == 5:
            lines.append("  REST    no posting, no commenting")
        else:
            lines.append("  ENGAGE  15 min   comment on 2 posts in your topic area")
            lines.append("  REPLY   10 min   answer anything still open")

        lines.append("")

    lines.append("Weekly habits")
    lines.append("  - After every post: reply to comments the same hour")
    lines.append("  - After you edit a draft by hand: lk edit <id>, so the voice learns")
    lines.append("  - Never send the same reply to two people")
    lines.append("  - Keep replies under 5/day; the queue enforces the cap")
    lines.append("")
    lines.append("Topic rotation: " + " / ".join(topics))
    return "\n".join(lines)


def save(text: str) -> dict:
    title = "week plan " + time.strftime("%d %b %Y")
    return store.save("plan", title, text, {"generated": time.strftime("%Y-%m-%d %H:%M:%S")})
