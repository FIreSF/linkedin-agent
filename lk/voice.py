"""Voice memory: style rules + example posts that teach the agent your tone."""

import json

from . import config

STYLE_FILE = config.DATA / "style.md"
EXAMPLES_FILE = config.DATA / "examples.jsonl"
AVOID_FILE = config.DATA / "avoid.jsonl"
REFERENCE_FILE = config.DATA / "reference.jsonl"
REFERENCE_MD = config.DATA / "reference.md"

DEFAULT_STYLE = """# Voice

I write like a person talking to one colleague, not like a brand.

- Short sentences. One idea per line.
- Specific over impressive: names, numbers, tools, timeframes.
- Admit the messy part. Failure is the hook, not the thing to hide.
- No hype words: thrilled, humbled, excited to announce, game-changer, synergy.
- No motivational-poster endings. End with a real question or a concrete next step.
"""

RULES = """Hard rules for LinkedIn output:
- Write in English only. Never mix in Chinese, Arabic, or any other language. If a word
  is not English, do not use it.
- The hook is NEW writing. Never copy, quote, or lightly rephrase the story text I gave you.
- Hook: under 12 words, capitalized first letter, no hashtags, no emoji. It must create a reason to tap "see more".
- Exactly ONE question mark in the entire post. The body never ends with a question; only the CTA asks.
- Body: 1-2 sentences per paragraph, blank line between paragraphs. Max 1300 characters total unless asked.
- No "I'm thrilled to announce", "I'm humbled", "excited to share". These read as generated.
- No closing moral like "just the start of the journey" or "a reminder that learning never stops".
- No emoji unless the user's own examples use them. Never more than 2.
- Hashtags: 3-5 at the very end. Single words, letters and digits only. Never "#Security+", never "#comp-tia".
- Sound like a human who was there, not a summarizer who read about it.
"""


def load_style() -> str:
    if STYLE_FILE.exists():
        text = STYLE_FILE.read_text().strip()
        if text:
            return text
    return DEFAULT_STYLE


def _read_rows(path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def examples(limit: int = 5) -> list[dict]:
    return _read_rows(EXAMPLES_FILE)[-limit:]


def avoid(limit: int = 3) -> list[dict]:
    return _read_rows(AVOID_FILE)[-limit:]


def refs(limit: int = 2) -> list[dict]:
    return _read_rows(REFERENCE_FILE)[-limit:]


def _reference_block(limit: int = 2) -> str:
    parts = []
    if REFERENCE_MD.exists():
        md = REFERENCE_MD.read_text().strip()
        if md:
            parts.append("Distilled structural patterns:\n" + md[:900])
    rows = refs(limit)
    for i, row in enumerate(rows, 1):
        note = f" ({row['note']})" if row.get("note") else ""
        parts.append(f"Widely-shared post {i}{note}:\n{row.get('text', '')[:450]}")
    return "\n\n".join(parts)


def has_references() -> bool:
    return bool(refs(1)) or (REFERENCE_MD.exists() and bool(REFERENCE_MD.read_text().strip()))


def _examples_block(limit: int = 5) -> str:
    rows = examples(limit)
    if not rows:
        return "No example posts saved yet."
    chunks = []
    for i, row in enumerate(rows, 1):
        note = f" ({row['note']})" if row.get("note") else ""
        chunks.append(f"Example {i}{note}:\n{row.get('text', '')[:600]}")
    return "\n\n".join(chunks)


def _avoid_block(limit: int = 3) -> str:
    rows = avoid(limit)
    if not rows:
        return "None saved."
    chunks = []
    for i, row in enumerate(rows, 1):
        reason = f" — never do this: {row['note']}" if row.get("note") else ""
        chunks.append(f"Bad example {i}{reason}:\n{row.get('text', '')[:500]}")
    return "\n\n".join(chunks)


def system_prompt(task: str, extra: str = "") -> str:
    """Every prompt starts identical, so the voice stays consistent across tasks."""
    who = f"Your name is {config.NAME}."
    if config.ROLE:
        who += f" You work as {config.ROLE}."
    audience = f"You write for {config.AUDIENCE}."

    reference = ""
    if has_references():
        reference = f"""
=== STRUCTURE REFERENCE — OTHER PEOPLE'S POSTS ===
These are not mine. Do not learn my voice from them and never reuse their wording.
Extract only the SHAPE: how the hook earns attention, paragraph rhythm, where the
concrete detail sits, how the ending invites a reply. Then write something new.

{_reference_block()}
"""

    return f"""TASK={task}

{who} {audience} You write LinkedIn posts and replies in my voice.

=== MY VOICE ===
{load_style()}

=== POSTS I WROTE AND LIKED (learn the rhythm, do not copy the topics) ===
{_examples_block()}

=== POSTS I WOULD NEVER WRITE (these are anti-patterns; avoid the style, not the words) ===
{_avoid_block()}
{reference}
=== RULES ===
{RULES}
{extra}

Return ONLY valid JSON. No markdown fences, no commentary before or after.
"""
