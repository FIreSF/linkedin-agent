"""Comment and reaction drafting."""

import json

from . import llm, voice

REACTIONS = {
    "like": ("👍", "Like"),
    "celebrate": ("👏", "Celebrate"),
    "support": ("🤝", "Support"),
    "love": ("❤️", "Love"),
    "insightful": ("💡", "Insightful"),
    "funny": ("😄", "Funny"),
}

REACTION_RULES = """Pick a reaction: celebrate (wins, promotions, certificates), support (hard news, setbacks),
insightful (technical or opinion posts), love (personal stories), funny (light jokes), like (default).
Reply rules:
- 1-3 sentences. Under 240 characters.
- Respond to the specific idea, quote a detail from their post or comment.
- Never open with "Great post" or "Thanks for sharing".
- Add one thing: a related experience, a small disagreement, or a concrete question.
- No links, no promotion of myself, no sycophancy."""


def _schema() -> str:
    return 'Return JSON: {"reaction": "like|celebrate|support|love|insightful|funny", "reply": "text"}'


def reply_to_comment(post_text: str, their_comment: str, author: str = "") -> dict:
    who = f"The commenter is {author}." if author else ""
    user = (
        f"Original post:\n{post_text[:2000]}\n\n"
        f"Comment I need to reply to:\n{their_comment[:1000]}\n\n{who}\n"
        "Write my reply as the post author."
    )
    messages = [
        {"role": "system", "content": voice.system_prompt("REPLY", REACTION_RULES + "\n" + _schema())},
        {"role": "user", "content": user},
    ]
    return _normalize(llm.chat_json(messages, temperature=0.7, max_tokens=400))


def comment_on_post(post_text: str, angle: str = "") -> dict:
    user = f"Post to comment on:\n{post_text[:2500]}"
    if angle:
        user += f"\n\nMy angle: {angle}"
    user += "\n\nWrite a comment I can leave on this post."
    messages = [
        {"role": "system", "content": voice.system_prompt("COMMENT", REACTION_RULES + "\n" + _schema())},
        {"role": "user", "content": user},
    ]
    return _normalize(llm.chat_json(messages, temperature=0.75, max_tokens=400))


def _normalize(data: dict) -> dict:
    reaction = str(data.get("reaction", "like")).strip().lower()
    if reaction not in REACTIONS:
        reaction = "like"
    emoji, label = REACTIONS[reaction]
    reply = str(data.get("reply", "")).strip().strip('"')
    return {
        "reaction": reaction,
        "reaction_emoji": emoji,
        "reaction_label": label,
        "reply": reply,
    }


def render(result: dict) -> str:
    return (
        f"React: {result['reaction_emoji']} {result['reaction_label']}\n\n"
        f"Reply:\n{result['reply']}"
    )


def warnings(result: dict) -> list[str]:
    out = []
    reply = result.get("reply", "")
    if len(reply) > 400:
        out.append("Reply is long; LinkedIn comments are best under ~240 chars.")
    low = reply.lower()
    if low.startswith(("great post", "thanks for sharing", "well said")):
        out.append("Reply opens with a generic phrase; it will read as automated.")
    if any(ord(ch) > 127 and not ch.isascii() and ch.isalpha() for ch in reply):
        out.append("Reply contains non-English characters; rewrite before approving.")
    return out
