"""Story coach: score a draft against LinkedIn storytelling beats and show how to fix it.

This is a reviewer, not a writer. It reads what you wrote and tells you what is missing.
"""

import json

from . import voice

BEATS = ("hook", "stakes", "turn", "proof", "invite")

RUBRIC = """You are a LinkedIn story editor. You do not flatter. You find the weak line.

A post that works has five beats:
- hook: line 1 stops the scroll. Specific, under 12 words, creates a gap the reader needs closed.
- stakes: something was at risk, lost, or cost something. Not "I decided to learn X".
- turn: one concrete change. The moment it started working.
- proof: a specific detail — number, tool, timeframe, result. Not an adjective.
- invite: one question the reader can answer from their own life.

Scoring:
- 9-10: all five beats, specific throughout, nothing generic.
- 7-8: strong story, one beat thin.
- 5-6: readable but generic; could have been written by anyone.
- 3-4: announcement dressed as a story.
- 0-2: no story, just a claim.

Rules:
- Every criticism must quote the actual words from the post.
- Fixes must be instructions I can act on, not "make it more engaging".
- Never suggest adding hashtags, emojis, or motivational endings.
- The rewrite must keep my facts. Do not invent numbers, tools or events."""

SCHEMA = """Return JSON:
{
  "score": 0-10,
  "beats": {
    "hook":   {"ok": true/false, "quote": "the line", "note": "why it works or fails"},
    "stakes": {"ok": true/false, "quote": "the line", "note": "..."},
    "turn":   {"ok": true/false, "quote": "the line", "note": "..."},
    "proof":  {"ok": true/false, "quote": "the line", "note": "..."},
    "invite": {"ok": true/false, "quote": "the line", "note": "..."}
  },
  "strengths": ["1-2 things that genuinely work"],
  "fixes": ["2-4 specific edits, strongest first"],
  "rewrite": "my post rewritten with the same facts, or an empty string if it is already good"
}"""


def analyze(text: str, examples: list[dict] | None = None) -> dict:
    calibration = ""
    rows = examples if examples is not None else voice.examples(limit=2)
    if rows:
        calibration = "\n\nFor calibration, here is how I normally write:\n" + "\n\n".join(
            r["text"][:700] for r in rows
        )

    messages = [
        {"role": "system", "content": voice.system_prompt("COACH", RUBRIC + "\n" + SCHEMA + calibration)},
        {"role": "user", "content": f"My post:\n\n{text}"},
    ]
    from . import llm

    data = llm.chat_json(messages, temperature=0.35, max_tokens=1100)
    return normalize(data, text)


def normalize(data: dict, original: str) -> dict:
    beats = {}
    for beat in BEATS:
        raw = (data.get("beats") or {}).get(beat) or {}
        if isinstance(raw, str):
            raw = {"ok": True, "note": raw}
        beats[beat] = {
            "ok": bool(raw.get("ok")),
            "quote": str(raw.get("quote", "")).strip(),
            "note": str(raw.get("note", "")).strip(),
        }

    try:
        score = max(0, min(10, int(round(float(data.get("score", 0))))))
    except (TypeError, ValueError):
        score = 0

    def strings(key: str, limit: int) -> list[str]:
        values = data.get(key) or []
        if isinstance(values, str):
            values = [values]
        return [str(v).strip() for v in values if str(v).strip()][:limit]

    rewrite = str(data.get("rewrite", "")).strip()
    if rewrite.strip() == original.strip():
        rewrite = ""

    return {
        "score": score,
        "beats": beats,
        "strengths": strings("strengths", 2),
        "fixes": strings("fixes", 4),
        "rewrite": rewrite,
    }


def bar(score: int, width: int = 20) -> str:
    filled = round(width * score / 10)
    return "#" * filled + "." * (width - filled)


def verdict(score: int) -> str:
    if score >= 9:
        return "post it"
    if score >= 7:
        return "post it after one fix"
    if score >= 5:
        return "generic — one more pass"
    if score >= 3:
        return "this is an announcement, not a story"
    return "no story yet"


def render(result: dict, show_rewrite: bool = False) -> str:
    lines = [f"Story score: {result['score']}/10  [{bar(result['score'])}]  {verdict(result['score'])}", ""]

    for beat in BEATS:
        info = result["beats"][beat]
        mark = "[x]" if info["ok"] else "[ ]"
        label = beat.ljust(7)
        detail = info["note"]
        line = f"  {mark} {label} {detail}"
        if not info["ok"] and info["quote"]:
            line += f'\n             ↳ "{info["quote"]}"'
        lines.append(line)

    if result["strengths"]:
        lines += ["", "Works"]
        lines += [f"  + {s}" for s in result["strengths"]]

    if result["fixes"]:
        lines += ["", "Fix before posting"]
        lines += [f"  {i}. {f}" for i, f in enumerate(result["fixes"], 1)]

    if show_rewrite and result["rewrite"]:
        lines += ["", "Rewrite (same facts, stronger beats)", "", result["rewrite"]]

    return "\n".join(lines)


def to_json(result: dict) -> str:
    return json.dumps(result, indent=2, ensure_ascii=False)
