"""Settings from .env, and every tuning number in one place."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

# Helpdesk calls
CALLS_PER_SECOND = 4      # the helpdesk allows 5 a second; stay under it
HTTP_RETRIES = 5          # tries for a 503 or a network error
FIRST_WAIT = 0.5          # seconds before the first retry; doubles after each one
MAX_WAIT = 8.0            # the wait never grows past this
HTTP_TIMEOUT = 15.0       # seconds for one helpdesk call

# Model calls
LLM_TIMEOUT = 90.0        # seconds for one model call
LLM_RETRIES = 4           # tries for a server error or a network error
LLM_MAX_TOKENS = 2000     # room for the answer, and for hidden reasoning
LLM_LONGEST_WAIT = 60.0   # a longer Retry-After means a daily limit: stop the run

# Decisions
CONFIDENCE_THRESHOLD = 0.75
PROMPT_VERSION = "v1"

# Cost in USD per million tokens (Groq, openai/gpt-oss-120b). Check the price page before quoting.
PRICE_INPUT_PER_M = 0.15
PRICE_OUTPUT_PER_M = 0.60

REQUIRED = ("HELPDESK_URL", "HELPDESK_KEY", "CANDIDATE_EMAIL", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")


@dataclass(frozen=True)
class Settings:
    helpdesk_url: str
    helpdesk_key: str = field(repr=False)  # repr=False: printing the settings never shows a key
    candidate_email: str
    candidate_name: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str = field(repr=False)
    llm_reasoning_effort: str


def _get(name: str) -> str:
    return os.getenv(name, "").strip()


def load_settings() -> Settings:
    """Read .env. Stop with a clear message if a value is missing."""
    load_dotenv(ROOT / ".env")
    missing = [name for name in REQUIRED if not _get(name)]
    if missing:
        raise SystemExit(f"Missing in .env: {', '.join(missing)}. Copy .env.example to .env and fill it in.")
    return Settings(
        helpdesk_url=_get("HELPDESK_URL").rstrip("/"),
        helpdesk_key=_get("HELPDESK_KEY"),
        candidate_email=_get("CANDIDATE_EMAIL"),
        candidate_name=_get("CANDIDATE_NAME"),
        llm_base_url=_get("LLM_BASE_URL").rstrip("/"),
        llm_model=_get("LLM_MODEL"),
        llm_api_key=_get("LLM_API_KEY"),
        llm_reasoning_effort=_get("LLM_REASONING_EFFORT"),
    )
