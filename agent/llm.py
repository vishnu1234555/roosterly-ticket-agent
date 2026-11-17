"""The only file that talks to the model. Any OpenAI-compatible chat API works (Groq by default):
change LLM_BASE_URL, LLM_MODEL and LLM_API_KEY in .env to switch provider."""
from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from agent import config
from agent.config import Settings

log = logging.getLogger(__name__)
FormT = TypeVar("FormT", bound=BaseModel)


class ModelFailed(Exception):
    """The model gave no valid form, even after one retry. The ticket goes to a human."""


class ProviderUnavailable(Exception):
    """The provider is down, out of quota, or asks us to wait too long. Stop the run; tickets stay open."""


class ProviderConfigError(Exception):
    """Wrong key, model name or address. Stop the run; nothing is sent."""


class _BadOutput(Exception):
    """The provider itself rejected the model's output as invalid JSON."""


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: Usage) -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens

    def cost_usd(self) -> float:
        return (
            self.input_tokens * config.PRICE_INPUT_PER_M + self.output_tokens * config.PRICE_OUTPUT_PER_M
        ) / 1_000_000


class LLM:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.model = settings.llm_model
        self._reasoning_effort = settings.llm_reasoning_effort
        self._sleep = sleep
        self._client = httpx.Client(
            base_url=settings.llm_base_url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=config.LLM_TIMEOUT,
            transport=transport,
        )

    def form(self, system: str, user: str, form_type: type[FormT], usage: Usage) -> FormT:
        """Ask for a JSON object and validate it. One retry with the error, then ModelFailed."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        for attempt in (1, 2):
            try:
                text = self._chat(messages, usage, json_mode=True)
                return form_type.model_validate_json(_strip_code_fence(text))
            except ValidationError as error:
                problem = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": f"That JSON does not match the form ({problem}). "
                                                "Return only the corrected JSON object."},
                ]
            except _BadOutput:
                problem = "not valid JSON"
            log.warning("Model output failed validation (attempt %d): %s", attempt, problem[:200])
        raise ModelFailed("no valid form after one retry")

    def text(self, system: str, user: str, usage: Usage) -> str:
        """A plain text answer, for example a translation."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        return self._chat(messages, usage, json_mode=False).strip()

    def _chat(self, messages: list[dict], usage: Usage, json_mode: bool) -> str:
        body: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": config.LLM_MAX_TOKENS,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort

        wait, errors, rate_limits = config.FIRST_WAIT, 0, 0
        while True:
            try:
                response = self._client.post("/chat/completions", json=body)
            except httpx.TransportError as error:  # a timeout or a broken connection
                errors += 1
                log.warning("Model call failed (%s), try %d", type(error).__name__, errors)
            else:
                status = response.status_code
                if status == 200:
                    data = response.json()
                    usage.calls += 1
                    usage.input_tokens += data.get("usage", {}).get("prompt_tokens", 0)
                    usage.output_tokens += data.get("usage", {}).get("completion_tokens", 0)
                    return data["choices"][0]["message"].get("content") or ""
                if status == 429:
                    rate_limits += 1
                    retry_after = _retry_after(response)
                    if retry_after > config.LLM_LONGEST_WAIT or rate_limits > 20:
                        raise ProviderUnavailable(f"rate limited, asked to wait {retry_after:.0f}s (daily limit?)")
                    log.info("Model rate limit: waiting %.1fs", retry_after)
                    self._sleep(retry_after)
                    continue
                if status == 400 and "json_validate_failed" in response.text:
                    raise _BadOutput()
                if status in (400, 401, 403, 404, 413, 422):
                    raise ProviderConfigError(f"model API answered {status}: {response.text[:300]}")
                errors += 1
                log.warning("Model API answered %d, try %d", status, errors)
            if errors >= config.LLM_RETRIES:
                raise ProviderUnavailable(f"model API failed {errors} times in a row")
            self._sleep(wait + random.uniform(0, 0.25))
            wait = min(wait * 2, config.MAX_WAIT)


def _retry_after(response: httpx.Response) -> float:
    try:
        return float(response.headers.get("retry-after", "5"))
    except ValueError:
        return 5.0


def _strip_code_fence(text: str) -> str:
    """Some models wrap JSON in ```json ... ``` even in JSON mode."""
    match = re.fullmatch(r"\s*```(?:json)?\s*(.*?)\s*```\s*", text, re.DOTALL)
    return match.group(1) if match else text
