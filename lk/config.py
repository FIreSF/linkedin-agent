"""Configuration, loaded from .env (no external deps)."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DRAFTS = ROOT / "drafts"
ENV_FILE = ROOT / ".env"


def _load_env() -> None:
    """Minimal .env parser. Existing environment variables win."""
    if not ENV_FILE.exists():
        return
    for raw in ENV_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_env()


def get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def set_value(key: str, value: str) -> None:
    """Update one key in .env, preserving everything else."""
    lines = ENV_FILE.read_text().splitlines() if ENV_FILE.exists() else []
    out, found = [], False
    for line in lines:
        if line.strip().startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(out) + "\n")
    os.environ[key] = value


OLLAMA_URL = get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL = get("LK_MODEL", "qwen2.5:7b")
NUM_CTX = int(get("LK_NUM_CTX", "8192") or 8192)
MOCK = get("LK_MOCK", "0") in ("1", "true", "yes")

NAME = get("LK_NAME", "the author")
ROLE = get("LK_ROLE", "")
AUDIENCE = get("LK_AUDIENCE", "people in my network")

# Safety rails
QUIET_START = get("LK_QUIET_START", "22")
QUIET_END = get("LK_QUIET_END", "8")
MAX_REPLIES_PER_DAY = int(get("LK_MAX_REPLIES_PER_DAY", "5") or 5)
REPLY_SPACING_S = int(get("LK_REPLY_SPACING_S", "360") or 360)
WATCH_POLL_S = int(get("LK_WATCH_POLL_S", "900") or 900)
REQUIRE_APPROVAL = get("LK_REQUIRE_APPROVAL", "1") not in ("0", "false", "no", "off")
