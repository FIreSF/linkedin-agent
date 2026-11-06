"""Pre-publish safety checks.

Nothing in this module contacts LinkedIn. It only inspects the text you are
about to paste, and compares it with drafts already on disk.
"""

import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from . import store, voice

HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"

EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]")
LINK = re.compile(r"https?://\S+")
MENTION = re.compile(r"(?<!\S)@[A-Za-z0-9_.-]{2,}")
TAG = re.compile(r"#\w+")

AI_TELLS = (
    "as an ai",
    "in today's fast-paced world",
    "delve into",
    "it's not just about",
    "let that sink in",
    "here's the thing:",
    "i'm thrilled",
    "i am thrilled",
    "game changer",
    "unlock the power",
)


def _stripped(text: str) -> str:
    """Text without hashtag lines or extra whitespace, for comparison."""
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))
    return re.sub(r"\s+", " ", body).strip().lower()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _stripped(a), _stripped(b)).ratio()


def _parse(stamp: str) -> datetime | None:
    try:
        return datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _shingles(text: str, size: int = 8) -> set[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    return {" ".join(words[i : i + size]) for i in range(max(0, len(words) - size + 1))}


def audit(record: dict) -> list[tuple[str, str]]:
    """Return [(level, message)]. Empty list means safe to post."""
    findings: list[tuple[str, str]] = []
    text = record.get("text", "")
    kind = record.get("kind", "post")

    # 1. Duplicate or near-duplicate content — the fastest way to look automated.
    for other in store.all_drafts():
        if other["id"] == record["id"]:
            continue
        score = similarity(text, other.get("text", ""))
        if score >= 0.85:
            findings.append(
                (
                    HIGH,
                    f"{score:.0%} identical to {other['id']} ({other['status']}). "
                    "Posting the same text twice is what triggers spam detection.",
                )
            )
            break

    # 2. Same reply sent to several people — flags comment automation instantly.
    if kind in ("reply", "comment"):
        reply = _stripped(text)
        repeats = [
            r for r in store.all_drafts()
            if r["id"] != record["id"] and r.get("kind") in ("reply", "comment")
            and _stripped(r.get("text", "")) == reply
        ]
        if repeats:
            findings.append(
                (HIGH, f"You already drafted this exact reply ({repeats[0]['id']}). Vary it or skip that comment.")
            )

    # 3. Volume. Humans do not post twice a day, every day.
    now = datetime.now()
    recent = []
    for r in store.all_drafts():
        if r["id"] == record["id"] or r.get("status") != "posted":
            continue
        when = _parse(r.get("created", ""))
        if when and now - when < timedelta(hours=24):
            recent.append(r)
    if kind in ("post", "cert") and len(recent) >= 2:
        findings.append(
            (HIGH, f"{len(recent)} posts marked as posted in the last 24h. Space them out — one per day is normal.")
        )
    elif kind in ("reply", "comment") and len(recent) >= 12:
        findings.append(
            (MEDIUM, f"{len(recent)} comments posted in 24h. Keep it near human volume, roughly a handful.")
        )

    # 4. Links and mentions.
    links = LINK.findall(text)
    if links:
        findings.append(
            (MEDIUM, f"{len(links)} link(s). LinkedIn throttles reach on link posts; put links in the first comment instead.")
        )
    mentions = MENTION.findall(text)
    if len(mentions) > 3:
        findings.append((MEDIUM, f"{len(mentions)} @mentions. Mass-tagging is treated as engagement bait."))

    # 5. Formatting limits.
    if len(text) > 3000:
        findings.append((HIGH, f"{len(text)} characters; LinkedIn's hard limit is 3000."))
    tags = TAG.findall(text)
    if len(tags) > 5:
        findings.append((MEDIUM, f"{len(tags)} hashtags. Above 5 reads as spam; 3 is plenty."))
    for tag in tags:
        if not re.fullmatch(r"#[a-z0-9]+", tag):
            findings.append((MEDIUM, f"'{tag}' contains characters LinkedIn will not parse. Use one word, letters and digits only."))
    emojis = EMOJI.findall(text)
    if len(emojis) > 2:
        findings.append((LOW, f"{len(emojis)} emoji. More than 2 looks promotional."))
    if text.count("?") > 1:
        findings.append((LOW, "More than one question; keep one, in the CTA."))

    # 6. AI tells.
    lowered = text.lower()
    for phrase in AI_TELLS:
        if phrase in lowered:
            findings.append((MEDIUM, f"Phrase that reads as generated: '{phrase}'."))

    # 7. Broken output (model artifacts).
    if re.search(r"(?m)^\s*\d{5,}\s*$", text):
        findings.append((HIGH, "A line of random digits leaked from the model. Delete it before posting."))
    if re.search(r"(?m)^\s*#\w*\d{5,}", text):
        findings.append((MEDIUM, "Numeric hashtag fragment. Remove it."))

    # 8. Accidental copying of a reference post you saved from someone else.
    mine = _shingles(text)
    if mine:
        for ref in voice.refs(limit=50):
            shared = mine & _shingles(ref.get("text", ""))
            if shared:
                count = len(shared)
                findings.append(
                    (
                        HIGH,
                        f"Copies {count} eight-word sequence(s) from a reference post you saved. "
                        "That is someone else's sentence — rewrite it.",
                    )
                )
                break

    return findings


def report(record: dict, header: str = "Safety") -> bool:
    """Print findings. Returns True when nothing HIGH was found."""
    findings = audit(record)
    if not findings:
        print(f"  {header}: clean — no spam signals found.")
        return True

    order = {HIGH: 0, MEDIUM: 1, LOW: 2}
    for level, message in sorted(findings, key=lambda f: order[f[0]]):
        print(f"  [{level}] {message}")
    return not any(level == HIGH for level, _ in findings)
