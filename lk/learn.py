"""Teach the agent: examples, anti-examples, bulk import, style distillation."""

import csv
import json
import time
from pathlib import Path

from . import voice

TEXT_SUFFIXES = {".txt", ".md", ".markdown"}


def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def add_example(text: str, note: str = "", bad: bool = False) -> int:
    text = text.strip()
    if not text:
        raise ValueError("Example post is empty.")
    row = {"text": text, "note": note.strip(), "added": int(time.time())}
    if bad:
        _append(voice.AVOID_FILE, row)
        return len(voice.avoid(limit=10_000))
    _append(voice.EXAMPLES_FILE, row)
    return len(voice.examples(limit=10_000))


def add_reference(text: str, note: str = "") -> int:
    """Other people's posts. Structure only — never used as voice examples."""
    text = text.strip()
    if not text:
        raise ValueError("Reference post is empty.")
    row = {"text": text, "note": note.strip(), "added": int(time.time())}
    _append(voice.REFERENCE_FILE, row)
    return len(voice.refs(limit=10_000))


def import_dir(folder: str, note: str = "", bad: bool = False, ref: bool = False) -> list[str]:
    """Every .txt/.md file in a folder becomes one example. Files are split on blank-line groups."""
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise ValueError(f"Not a folder: {root}")
    added = []
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        text = path.read_text(errors="ignore").strip()
        # Drop markdown headings so a "# Title" line does not become part of the post.
        text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
        text = text.strip()
        if len(text) < 25:
            continue
        if ref:
            add_reference(text, note or path.stem)
        else:
            add_example(text, note or path.stem, bad=bad)
        added.append(path.name)
    if not added:
        raise ValueError(f"No .txt or .md files with content found in {root}")
    return added


def import_linkedin_csv(path: str, bad: bool = False) -> int:
    """Import your own posts from a LinkedIn data export (Posts.csv / Shares.csv)."""
    file = Path(path).expanduser()
    if not file.is_file():
        raise ValueError(f"File not found: {file}")
    count = 0
    with file.open(newline="", encoding="utf-8-sig", errors="ignore") as fh:
        reader = csv.DictReader(fh)
        fields = reader.fieldnames or []
        column = next(
            (f for f in fields if any(k in f.lower() for k in ("commentary", "text", "share"))),
            None,
        )
        if column is None:
            raise ValueError(f"No text column found. Columns were: {', '.join(fields) or 'none'}")
        for row in reader:
            text = (row.get(column) or "").strip()
            if len(text) < 25:
                continue
            add_example(text, "imported from LinkedIn export", bad=bad)
            count += 1
    if count == 0:
        raise ValueError("No posts with enough text found in that CSV.")
    return count


def analyze_reference() -> str:
    """Distil OTHER people's posts into structural patterns (never phrasing)."""
    rows = voice.refs(limit=10_000)
    if not rows:
        raise ValueError("No reference posts yet. Add one with: lk ref --text \"...\"")
    sounds = "\n\n---\n\n".join(f"POST {i}:\n{r['text']}" for i, r in enumerate(rows, 1))
    prompt = (
        "These are posts by other people in my industry that got engagement.\n\n"
        f"{sounds[:8000]}\n\n"
        "Describe their STRUCTURE only: hook formulas, paragraph shapes, where proof or "
        "numbers appear, how they end, which topic angles repeat. "
        "Do NOT quote sentences. Do NOT list phrases to reuse. Do NOT name anyone. "
        "Output markdown starting with '## Structural patterns'. 6-10 bullets."
    )
    messages = [
        {
            "role": "system",
            "content": voice.system_prompt(
                "STRUCTURE", "This is structural analysis, not a post. Plain markdown. Never quote the source."
            ),
        },
        {"role": "user", "content": prompt},
    ]
    from . import llm

    rules = llm.chat(messages, temperature=0.3, max_tokens=700).strip()
    voice.REFERENCE_MD.parent.mkdir(parents=True, exist_ok=True)
    voice.REFERENCE_MD.write_text(rules + "\n")
    return rules


def analyze() -> str:
    """Read every example and anti-example, rewrite data/style.md."""
    rows = voice.examples(limit=10_000)
    if not rows:
        raise ValueError("No examples saved yet. Add one with: lk learn --file post.txt")

    good = "\n\n---\n\n".join(f"POST {i}:\n{r['text']}" for i, r in enumerate(rows, 1))
    bad_rows = voice.avoid(limit=10_000)
    bad = ""
    if bad_rows:
        bad = "\n\nPOSTS I HATE (never write like these):\n\n" + "\n\n".join(
            f"BAD {i}:\n{r['text']}" for i, r in enumerate(bad_rows, 1)
        )

    prompt = (
        "Here are posts I wrote and liked.\n\n"
        f"{good[:9000]}\n"
        f"{bad[:3000]}\n\n"
        "Describe my writing style as rules someone else could follow. "
        "Cover: hook style, sentence length, paragraphing, vocabulary, emoji use, "
        "how I handle failure and numbers, how I end posts. "
        "If anti-examples are given, add 2 rules about what I never do. "
        "Output markdown starting with '## Learned style rules'. Use 6-10 bullets. "
        "Be specific and quote fragments as evidence. No preamble."
    )
    messages = [
        {"role": "system", "content": voice.system_prompt("STYLE", "This is style analysis, not a post. Plain markdown.")},
        {"role": "user", "content": prompt},
    ]
    from . import llm

    rules = llm.chat(messages, temperature=0.3, max_tokens=700).strip()

    manual = voice.load_style()
    if "## Learned style rules" in manual:
        manual = manual.split("## Learned style rules")[0].rstrip()
    merged = (manual + "\n\n" + rules).strip() + "\n"
    voice.STYLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    voice.STYLE_FILE.write_text(merged)
    return rules
