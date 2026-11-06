"""Post generation: certificate stories, generic posts, calendars."""

import re

from . import llm, voice

STORY_SHAPE = """Story shape for a certificate or badge post:
1. HOOK: the moment before the result. A failed attempt, a doubt, a cost. Not the win.
2. STRUGGLE: one specific obstacle. What actually went wrong.
3. TURN: the single change that made it work.
4. PROOF: the certificate itself, stated plainly. What it does and does not prove.
5. INVITE: a question the reader can answer from their own experience.

Never write the post as an announcement. Write it as a story someone tells a friend.

HOOK EXAMPLES — this is the part models get wrong most often.
BAD (copies my story text verbatim): "Failed first attempt on performance-based questions"
BAD (generic): "Excited to share my new certification"
GOOD (an image from the moment): "The home lab I broke on purpose taught me more than the course did."
GOOD (a number with tension): "Two attempts, one home lab. The lab was the difference."
GOOD (a confession): "I passed the exam. I still could not explain how an attack works."

The hook must be a NEW sentence I have never written. Do not reuse my story wording.
"""


def _clean_text(value: str) -> str:
    return " ".join((value or "").split()).strip()


def certificate(
    title: str,
    issuer: str = "",
    skills: str = "",
    story: str = "",
    tone: str = "",
) -> dict:
    facts = [f"Certificate: {_clean_text(title)}"]
    if issuer:
        facts.append(f"Issuer: {_clean_text(issuer)}")
    if skills:
        facts.append(f"Skills covered: {_clean_text(skills)}")
    if story:
        facts.append(f"What actually happened (use this, do not invent): {_clean_text(story)}")
    if tone:
        facts.append(f"Tone I want: {_clean_text(tone)}")

    schema = """Return JSON with exactly these keys:
{"hook": "one line, under 12 words",
 "body": "3-5 short paragraphs separated by \\n\\n",
 "cta": "one question",
 "hashtags": ["3-5 lowercase tags without #"]}"""

    extra = STORY_SHAPE + "\n" + schema + (
        "\nIf I gave you a real story, use its details. If not, keep it truthful and "
        "generic about the effort, never invent a specific failure I did not mention."
    )

    messages = [
        {"role": "system", "content": voice.system_prompt("CERT", extra)},
        {"role": "user", "content": "\n".join(facts) + "\n\nWrite the post."},
    ]
    data = llm.chat_json(messages, temperature=0.75, max_tokens=800)
    return normalize(data, title)


def topic(text: str, angle: str = "", context: str = "") -> dict:
    schema = """Return JSON with exactly these keys:
{"hook": "one line, under 12 words",
 "body": "3-5 short paragraphs separated by \\n\\n",
 "cta": "one question",
 "hashtags": ["3-5 lowercase tags without #"]}"""

    extra = schema
    user = f"Topic: {_clean_text(text)}"
    if angle:
        user += f"\nAngle: {_clean_text(angle)}"
    if context:
        user += f"\nBackground material to draw from:\n{context[:2500]}"

    messages = [
        {"role": "system", "content": voice.system_prompt("POST", extra)},
        {"role": "user", "content": user + "\n\nWrite the post."},
    ]
    data = llm.chat_json(messages, temperature=0.8, max_tokens=800)
    return normalize(data)


def _clean_tag(raw: str) -> str:
    """LinkedIn tags allow letters and digits only. 'comp-tia' and 'security+' are dead tags."""
    return "".join(ch for ch in str(raw).lower() if ch.isalnum())


def _clean_hook(raw: str, title: str = "") -> str:
    hook = " ".join(str(raw).split()).strip().strip('"').strip("'")
    if hook and not hook[0].isupper():
        hook = hook[0].upper() + hook[1:]
    return hook


def _drop_trailing_question(body: str, cta: str) -> str:
    """If the body ends with a question and a CTA already asks one, cut the body's."""
    if not cta:
        return body
    stripped = body.rstrip()
    if not stripped.endswith("?"):
        return body
    match = re.search(r"(?:^|(?<=[.!?])\s)([^.!?]*\?)$", stripped, re.S)
    if not match:
        return body
    cut = stripped[: match.start()].rstrip()
    return cut or body


def normalize(data: dict, title: str = "") -> dict:
    tags = data.get("hashtags") or []
    if isinstance(tags, str):
        tags = [t for t in tags.replace("#", " ").replace(",", " ").split() if t]

    cleaned, seen = [], set()
    for raw in tags:
        tag = _clean_tag(raw)
        if len(tag) < 3 or tag in seen:
            continue
        if tag.isdigit():  # "#2026" is not a useful tag on its own
            continue
        seen.add(tag)
        cleaned.append("#" + tag)

    cta = str(data.get("cta", "")).strip()
    if cta[:1].islower():
        cta = cta[:1].upper() + cta[1:]
    body = _drop_trailing_question(str(data.get("body", "")).strip(), cta)
    body = re.sub(r"(?m)^[ \t]*\d{4,}[ \t]*$\n?", "", body)  # model artifact lines
    body = re.sub(r"\n{3,}", "\n\n", body).strip()

    return {
        "hook": _clean_hook(data.get("hook", ""), title),
        "body": body,
        "cta": cta,
        "hashtags": cleaned[:5],
    }


def render(post: dict) -> str:
    parts = [post.get("hook", "").strip(), post.get("body", "").strip(), post.get("cta", "").strip()]
    text = "\n\n".join(p for p in parts if p)
    if post.get("hashtags"):
        text += "\n\n" + " ".join(post["hashtags"])
    return text.strip()


def warnings(post: dict) -> list[str]:
    out = []
    text = render(post)
    hook = post.get("hook", "")
    if len(hook.split()) > 12:
        out.append(f"Hook is {len(hook.split())} words; aim for under 12.")
    if len(text) > 3000:
        out.append(f"Post is {len(text)} chars; LinkedIn's limit is 3000.")
    if len(post.get("hashtags", [])) > 5:
        out.append("More than 5 hashtags hurts reach.")
    lowered = text.lower()
    cliches = (
        "thrilled to announce",
        "humbled",
        "excited to announce",
        "game changer",
        "just the start",
        "continuous learning",
        "a reminder that",
        "remember, this is",
    )
    for phrase in cliches:
        if phrase in lowered:
            out.append(f"Contains a cliché: '{phrase}'.")
    if post.get("body", "").strip().startswith(hook.strip()):
        out.append("Body repeats the hook. Cut the first line of the body.")
    if render(post).count("?") > 1:
        out.append("More than one question. Keep one, in the CTA only.")
    return out
