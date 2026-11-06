"""Deterministic text cleanup. No model, no network, no guessing.

Removes the mechanical tells that make a draft read as generated: em dashes,
invisible characters, slop vocabulary and doubled punctuation. Every change is
reported so nothing is silently rewritten.
"""

import re

# Invisible / zero-width / bidi characters that carry no meaning and look like
# a watermark to a detector.
INVISIBLE = {
    "\u00ad": "soft hyphen",
    "\u200b": "zero-width space",
    "\u200c": "zero-width non-joiner",
    "\u200d": "zero-width joiner",
    "\u200e": "left-to-right mark",
    "\u200f": "right-to-left mark",
    "\u2060": "word joiner",
    "\ufeff": "byte-order mark",
    "\u202a": "left-to-right embedding",
    "\u202b": "right-to-left embedding",
    "\u202c": "pop directional formatting",
    "\u202d": "left-to-right override",
    "\u202e": "right-to-left override",
}

# Word swaps. Conservative on purpose: only words that almost always read as
# filler in a personal post. Each replacement is reported.
SLOP = {
    "leverage": "use",
    "leverages": "uses",
    "leveraging": "using",
    "utilize": "use",
    "utilizes": "uses",
    "utilizing": "using",
    "utilized": "used",
    "delve": "dig",
    "delves": "digs",
    "delving": "digging",
    "seamless": "smooth",
    "seamlessly": "smoothly",
    "robust": "solid",
    "myriad": "many",
    "plethora": "many",
    "facilitate": "help",
    "facilitates": "helps",
    "endeavor": "effort",
    "embark": "start",
    "embarks": "starts",
    "realm": "area",
    "tapestry": "mix",
    "testament": "proof",
    "game-changer": "big change",
    "game changer": "big change",
    "synergy": "overlap",
    "synergies": "overlaps",
    "paradigm": "model",
    "holistic": "whole",
    "pivotal": "key",
    "meticulous": "careful",
    "meticulously": "carefully",
    "elevate": "raise",
    "elevates": "raises",
    "unlock": "open",
    "unlocks": "opens",
    "harness": "use",
    "harnesses": "uses",
    "foster": "build",
    "fosters": "builds",
    "navigate": "handle",
    "navigating": "handling",
    "landscape": "space",
    "cutting-edge": "new",
    "state-of-the-art": "new",
    "best-in-class": "good",
    "revolutionize": "change",
    "revolutionizes": "changes",
}

# Whole phrases that are pure filler. Deleted with the sentence they sit in when
# they open the line.
FILLER_OPENERS = [
    "in today's fast-paced world",
    "in today's digital age",
    "in the ever-evolving landscape",
    "it's no secret that",
    "needless to say",
    "at the end of the day",
    "when it comes to",
]

# Reported, not rewritten: these change meaning if swapped mechanically.
HYPE = [
    "thrilled",
    "humbled",
    "honored",
    "delighted",
    "ecstatic",
    "excited to announce",
    "excited to share",
    "beyond proud",
    "incredibly proud",
]

EM_DASH = re.compile(r"\s*\u2014\s*")
EN_DASH = re.compile(r"\s*\u2013\s*")
ZERO_WIDTH = re.compile("[" + "".join(INVISIBLE) + "]")
DOUBLE_PUNCT = re.compile(r"([,.;:!?])\s*([,.;:!?])+")
SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
MULTISPACE = re.compile(r"[ \t]{2,}")
MULTI_NEWLINE = re.compile(r"\n{3,}")
ASTERISK_BOLD = re.compile(r"\*\*(.+?)\*\*")


def humanize(text: str) -> tuple[str, list[str]]:
    """Return (cleaned_text, list_of_changes)."""
    original = text or ""
    changes: list[str] = []
    out = original

    # 1. invisible characters
    found = {name for ch, name in INVISIBLE.items() if ch in out}
    if found:
        out = ZERO_WIDTH.sub("", out)
        changes.append("removed invisible characters: " + ", ".join(sorted(found)))

    # 2. em dashes and en dashes
    if EM_DASH.search(out):
        out = EM_DASH.sub(", ", out)
        changes.append("replaced em dashes with commas")
    if EN_DASH.search(out):
        out = EN_DASH.sub("-", out)
        changes.append("replaced en dashes with hyphens")

    # 3. filler openers
    lowered = out.lower()
    for phrase in FILLER_OPENERS:
        if lowered.startswith(phrase):
            head, sep, tail = out.partition(" ")
            rest = out[len(phrase):].lstrip(" ,")
            out = rest[:1].upper() + rest[1:] if rest else out
            changes.append(f"removed filler opener: \"{phrase}\"")
            lowered = out.lower()
            break

    # 4. slop vocabulary (whole words only)
    for word, replacement in SLOP.items():
        pattern = re.compile(r"\b" + re.escape(word) + r"\b", re.IGNORECASE)
        if pattern.search(out):
            def _swap(match: re.Match) -> str:
                src = match.group(0)
                if src.isupper():
                    return replacement.upper()
                if src[:1].isupper():
                    return replacement[:1].upper() + replacement[1:]
                return replacement

            out = pattern.sub(_swap, out)
            changes.append(f"swapped \"{word}\" -> \"{replacement}\"")

    # 5. punctuation damage repair
    if DOUBLE_PUNCT.search(out):
        out = DOUBLE_PUNCT.sub(r"\1", out)
        changes.append("fixed doubled punctuation")
    if SPACE_BEFORE_PUNCT.search(out):
        out = SPACE_BEFORE_PUNCT.sub(r"\1", out)
        changes.append("removed space before punctuation")

    # 6. markdown bold in a plain post
    if ASTERISK_BOLD.search(out):
        out = ASTERISK_BOLD.sub(r"\1", out)
        changes.append("removed markdown bold")

    # 7. whitespace
    if MULTISPACE.search(out):
        out = MULTISPACE.sub(" ", out)
        changes.append("collapsed repeated spaces")
    if MULTI_NEWLINE.search(out):
        out = MULTI_NEWLINE.sub("\n\n", out)
        changes.append("collapsed blank lines")

    return out.strip(), changes


def report(text: str, changes: list[str]) -> str:
    if not changes:
        return "clean — nothing to remove."
    return "\n".join(f"  - {c}" for c in changes)


def repeated_openers(text: str) -> list[str]:
    """Flag lines that start with the same word three or more times."""
    counts: dict[str, int] = {}
    for line in text.splitlines():
        words = line.strip().split()
        if not words:
            continue
        first = words[0].strip(".,:;!?").lower()
        if not first:
            continue
        counts[first] = counts.get(first, 0) + 1
    return [w for w, n in counts.items() if n >= 3]


def hype_words(text: str) -> list[str]:
    """Hype words present in the text. Reported, never rewritten."""
    low = (text or "").lower()
    return [w for w in HYPE if w in low]
