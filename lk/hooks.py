"""Twenty-one opening-line formulas, with an optional rewrite of a draft's hook."""

from . import llm

HOOKS: list[dict[str, str]] = [
    {
        "name": "confession",
        "formula": "I was wrong about ___.",
        "example": "I was wrong about backups. Restores are the only thing that counts.",
    },
    {
        "name": "number with tension",
        "formula": "Two ___. One ___.",
        "example": "Two attempts, one home lab. The lab was the difference.",
    },
    {
        "name": "cost first",
        "formula": "This cost me ___.",
        "example": "This cost me a weekend and one client. Worth it.",
    },
    {
        "name": "moment before",
        "formula": "The ___ came at ___.",
        "example": "The alert came at 3am. It was a backup job.",
    },
    {
        "name": "contradiction",
        "formula": "Everyone says ___. I did the opposite.",
        "example": "Everyone says post daily. I post when I have something to say.",
    },
    {
        "name": "small detail",
        "formula": "One line in the ___ broke it.",
        "example": "One line in the config broke the whole pipeline.",
    },
    {
        "name": "question to reader",
        "formula": "What would you do if ___?",
        "example": "What would you do if the logs lied to you?",
    },
    {
        "name": "failure receipt",
        "formula": "I failed ___. Here is the receipt.",
        "example": "I failed the first attempt. Here is the receipt.",
    },
    {
        "name": "time marker",
        "formula": "Six months ago I ___.",
        "example": "Six months ago I could not read a packet capture.",
    },
    {
        "name": "direct address",
        "formula": "If you run ___, read this.",
        "example": "If you run backups on the same host, read this.",
    },
    {
        "name": "myth bust",
        "formula": "___ is not the problem.",
        "example": "Ransomware is not the problem. Recovery time is.",
    },
    {
        "name": "before and after",
        "formula": "Last year: ___. Today: ___.",
        "example": "Last year: three alerts a night. Today: one dashboard.",
    },
    {
        "name": "object lesson",
        "formula": "A broken ___ taught me ___.",
        "example": "A broken drive taught me to test restores.",
    },
    {
        "name": "unpopular opinion",
        "formula": "Unpopular opinion: ___.",
        "example": "Unpopular opinion: most security dashboards are decoration.",
    },
    {
        "name": "specific number",
        "formula": "N ___. All ___. (real numbers)",
        "example": "12 old accounts. All reused passwords.",
    },
    {
        "name": "confession of ignorance",
        "formula": "I still cannot explain ___.",
        "example": "I passed the exam. I still cannot explain how the attack works.",
    },
    {
        "name": "interruption",
        "formula": "I stopped mid-___.",
        "example": "I stopped mid-demo when the scan found our own bucket.",
    },
    {
        "name": "comparison",
        "formula": "The course taught ___. The ___ taught ___.",
        "example": "The course taught terms. The lab taught timing.",
    },
    {
        "name": "warning",
        "formula": "This is how ___ get ___.",
        "example": "This is how accounts get stolen. Not with exploits.",
    },
    {
        "name": "quiet fact",
        "formula": "Nobody talks about ___.",
        "example": "Nobody talks about the 40 minutes of finding the problem.",
    },
    {
        "name": "open loop",
        "formula": "The fix took ___. Finding it took ___.",
        "example": "The fix took 6 minutes. Finding it took 40.",
    },
]


def listing() -> list[dict[str, str]]:
    return HOOKS


def render(rows: list[dict[str, str]] | None = None) -> str:
    rows = rows or HOOKS
    lines = []
    for i, row in enumerate(rows, 1):
        lines.append(f"{i:>2}. {row['name']}")
        lines.append(f"    formula: {row['formula']}")
        lines.append(f"    example: {row['example']}")
    return "\n".join(lines)


def pick(name: str) -> dict[str, str] | None:
    key = name.strip().lower()
    for row in HOOKS:
        if row["name"].lower() == key:
            return row
    return None


def rewrite_hook(post_text: str, formula_name: str = "") -> dict:
    """Rewrite only the first paragraph of a post using one hook formula."""
    chosen = pick(formula_name) if formula_name else HOOKS[0]
    if not chosen:
        raise ValueError(f"Unknown hook: {formula_name}")

    body = post_text.strip()
    parts = body.split("\n\n", 1)
    rest = parts[1] if len(parts) > 1 else ""

    prompt = (
        f"Rewrite ONLY the opening line of this post.\n\n"
        f"Hook formula: {chosen['formula']}\n"
        f"Example of the shape (do not copy it): {chosen['example']}\n\n"
        f"Post:\n{body[:2000]}\n\n"
        "Rules:\n"
        "- One sentence, under 12 words.\n"
        "- Keep the same true facts. Invent nothing.\n"
        "- No hashtags, no emoji, no quotation marks.\n"
        "- Return the new opening line only, nothing else."
    )
    messages = [
        {"role": "system", "content": "You rewrite LinkedIn opening lines. Output one line."},
        {"role": "user", "content": prompt},
    ]
    new_hook = llm.chat(messages, temperature=0.8, max_tokens=80).strip().strip('"')
    new_hook = new_hook.splitlines()[0] if new_hook else ""
    if not new_hook:
        raise ValueError("Model returned an empty hook.")
    return {
        "formula": chosen["name"],
        "old": parts[0].strip(),
        "new": new_hook,
        "text": (new_hook + ("\n\n" + rest if rest else "")).strip(),
    }
