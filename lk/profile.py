"""Profile copy. LinkedIn has no API for editing a profile, so this writes the text you paste."""

from . import llm, voice

HEADLINE_LIMIT = 220
ABOUT_LIMIT = 2600


def update(
    cert: str = "",
    issuer: str = "",
    skills: str = "",
    achievement: str = "",
    role: str = "",
) -> dict:
    facts = []
    if cert:
        facts.append(f"New certificate or badge: {cert}")
    if issuer:
        facts.append(f"Issued by: {issuer}")
    if skills:
        facts.append(f"Skills it proves: {skills}")
    if achievement:
        facts.append(f"What actually happened: {achievement}")
    if role:
        facts.append(f"My current role: {role}")
    if not facts:
        raise ValueError("Give me at least a certificate, skill, or achievement.")

    prompt = (
        "\n".join(facts)
        + """

Write three things for my LinkedIn profile. Never invent credentials, employers or numbers.

- headline: under 200 characters. Role + what I actually do + one proof point. No buzzwords, no "passionate".
- about: 3 short paragraphs separated by blank lines. Opens with what I do, then the specific thing I just
  achieved and what it changed, then what I am looking for. First person. No motivational ending.
- experience_bullet: one line to add under my current role, starting with a verb, with a concrete outcome.

Return JSON: {"headline": "...", "about": "...", "experience_bullet": "..."}"""
    )
    messages = [
        {
            "role": "system",
            "content": voice.system_prompt(
                "PROFILE",
                "This is profile copy, not a post. Return only valid JSON with the three keys.",
            ),
        },
        {"role": "user", "content": prompt},
    ]
    data = llm.chat_json(messages, temperature=0.6, max_tokens=700)

    return {
        "headline": str(data.get("headline", "")).strip()[:HEADLINE_LIMIT],
        "about": str(data.get("about", "")).strip()[:ABOUT_LIMIT],
        "experience_bullet": str(data.get("experience_bullet", "")).strip(),
    }


def render(result: dict) -> str:
    lines = [
        f"Headline  ({len(result['headline'])}/{HEADLINE_LIMIT})",
        "",
        result["headline"],
        "",
        f"About  ({len(result['about'])}/{ABOUT_LIMIT})",
        "",
        result["about"],
        "",
        "Experience bullet",
        "",
        result["experience_bullet"],
        "",
        "Paste these into your profile. LinkedIn has no API for editing it.",
    ]
    return "\n".join(lines)


def warnings(result: dict) -> list[str]:
    out = []
    if len(result["headline"]) > HEADLINE_LIMIT:
        out.append("Headline is over the 220 character limit.")
    if "\n\n" not in result["about"]:
        out.append("About came back as one block; LinkedIn reads better as 3 short paragraphs.")
    low = (result["headline"] + " " + result["about"]).lower()
    for phrase in (
        "passionate",
        "results-driven",
        "dynamic professional",
        "proven track record",
        "robust",
        "enhancing my ability",
        "looking to apply",
        "leverage",
    ):
        if phrase in low:
            out.append(f"Cliché phrase: '{phrase}'.")
    return out
