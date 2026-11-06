"""Thin client for a local Ollama server, with a mock mode for testing."""

import json
import re

import requests

from . import config


class LLMError(RuntimeError):
    pass


MOCK_POST = {
    "hook": "I failed the exam twice before this arrived.",
    "body": (
        "The first attempt, I studied the wrong 40% of the material.\n\n"
        "The second, I knew the content but ran out of time on the labs.\n\n"
        "So for attempt three I stopped collecting courses and started building. "
        "One messy project per week, broken on purpose, fixed by hand.\n\n"
        "This badge is not proof I know everything. It is proof I stopped quitting at attempt two."
    ),
    "cta": "What is the one skill you learned by failing at it first?",
    "hashtags": ["certification", "learning", "career", "growth"],
}

MOCK_REPLY = {
    "reaction": "celebrate",
    "reply": (
        "This is the part most people skip: the second attempt is where the real learning happens. "
        "Congrats on pushing through it."
    ),
}

MOCK_COMMENT = {
    "reaction": "insightful",
    "reply": (
        "The detail about testing in production before the migration is the whole post. "
        "We did the same and cut rollback time by more than half."
    ),
}

MOCK_STYLE = """## Learned style rules

- Opens with a short, blunt sentence that states a failure or a number.
- Uses one-sentence paragraphs separated by blank lines.
- Names specific tools, times and numbers instead of adjectives.
- Never uses "thrilled", "humbled", "excited to announce".
- Ends with a direct question aimed at the reader's own experience.
"""


MOCK_COACH = {
    "score": 4,
    "beats": {
        "hook": {"ok": False, "quote": "I am excited to announce", "note": "Announcement opener; nothing at stake."},
        "stakes": {"ok": False, "quote": "", "note": "No cost or risk anywhere."},
        "turn": {"ok": False, "quote": "", "note": "No moment where something changed."},
        "proof": {"ok": False, "quote": "gained many skills", "note": "Vague; no number, tool or timeframe."},
        "invite": {"ok": False, "quote": "", "note": "No question; the post just stops."},
    },
    "strengths": ["Topic is clear in the first line."],
    "fixes": ["Replace the opener with the moment before the result.", "Name one tool and one timeframe."],
    "rewrite": "",
}


def _mock(messages) -> str:
    system = messages[0]["content"] if messages else ""
    task = ""
    m = re.search(r"TASK=(\w+)", system)
    if m:
        task = m.group(1)

    if task == "STYLE":
        return MOCK_STYLE
    if task == "COACH":
        return json.dumps(MOCK_COACH)
    if task == "STRUCTURE":
        return """## Structural patterns

- Opens with a loss or a number, not a claim.
- Second line contradicts the first, creating tension.
- Proof arrives as a cost (revenue, time), never as a credential.
- Ends without a moral; the implication is left to the reader.
"""
    if task == "REPLY":
        return json.dumps(MOCK_REPLY)
    if task == "COMMENT":
        return json.dumps(MOCK_COMMENT)
    if task in ("CERT", "POST"):
        return json.dumps(MOCK_POST)
    return "Mock output."


def _extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LLMError(f"Model did not return JSON:\n{text[:400]}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model returned invalid JSON ({exc}):\n{text[:400]}") from exc


def chat(messages, *, json_mode: bool = False, temperature: float = 0.7, max_tokens: int = 900) -> str:
    if config.MOCK:
        return _mock(messages)

    payload = {
        "model": config.MODEL,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_ctx": config.NUM_CTX,
            "num_predict": max_tokens,
        },
    }
    if json_mode:
        payload["format"] = "json"

    try:
        resp = requests.post(f"{config.OLLAMA_URL}/api/chat", json=payload, timeout=300)
    except requests.RequestException as exc:
        raise LLMError(
            "Cannot reach Ollama at "
            f"{config.OLLAMA_URL}.\n"
            "Install it:  curl -fsSL https://ollama.com/install.sh | sh\n"
            f"Then:        ollama pull {config.MODEL}\n"
            "Or test the tool without a model:  LK_MOCK=1 lk ..."
        ) from exc

    if resp.status_code == 404:
        raise LLMError(
            f"Model '{config.MODEL}' is not installed. Run: ollama pull {config.MODEL}"
        )
    if resp.status_code >= 400:
        body = resp.text[:300]
        if "llama-server binary not found" in body:
            raise LLMError(
                "Ollama is installed but its model runner is missing, so no model can\n"
                "load. This happens when an Ollama upgrade is interrupted.\n"
                "  Fix:  curl -fsSL https://ollama.com/install.sh | sh\n"
                "  Then: lk doctor --live\n"
                "(Your models are kept; only the program is reinstalled.)"
            )
        raise LLMError(f"Ollama error {resp.status_code}: {body}")

    data = resp.json()
    content = (data.get("message") or {}).get("content", "")
    if not content:
        raise LLMError(f"Empty response from Ollama: {data}")
    return content


def chat_json(messages, *, temperature: float = 0.7, max_tokens: int = 900) -> dict:
    return _extract_json(chat(messages, json_mode=True, temperature=temperature, max_tokens=max_tokens))


def live_check() -> tuple[bool, str]:
    """Actually load the model with a one-token request. Slow but truthful."""
    if config.MOCK:
        return True, "mock mode"
    payload = {
        "model": config.MODEL,
        "messages": [{"role": "user", "content": "ping"}],
        "stream": False,
        "options": {"num_predict": 1, "num_ctx": 512},
    }
    try:
        resp = requests.post(f"{config.OLLAMA_URL}/api/chat", json=payload, timeout=180)
    except requests.RequestException as exc:
        return False, f"cannot reach Ollama: {exc}"
    if resp.status_code == 200:
        return True, "model loaded and answered"
    body = resp.text[:400]
    if "llama-server binary not found" in body:
        return False, (
            "Ollama's model runner is missing (interrupted upgrade).\n"
            "  Fix:  curl -fsSL https://ollama.com/install.sh | sh\n"
            "  Then: lk doctor --live"
        )
    return False, f"Ollama error {resp.status_code}: {body}"


def health() -> dict:
    """Used by `lk doctor`."""
    out = {"url": config.OLLAMA_URL, "model": config.MODEL, "mock": config.MOCK}
    try:
        resp = requests.get(f"{config.OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        names = [m.get("name", "") for m in resp.json().get("models", [])]
        out["server"] = "up"
        out["installed"] = names
        out["model_ready"] = any(n == config.MODEL or n.startswith(config.MODEL) for n in names)
    except Exception as exc:  # noqa: BLE001
        out["server"] = "down"
        out["error"] = str(exc)
        out["model_ready"] = False
    return out
