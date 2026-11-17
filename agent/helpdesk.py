"""Every HTTP call to the Nordavo helpdesk. Call spacing, retries and error handling live here."""
from __future__ import annotations

import logging
import random
import time
from collections import Counter
from typing import Any, Callable

import httpx

from agent import config
from agent.config import Settings

log = logging.getLogger(__name__)


class HelpdeskError(Exception):
    """A 4xx answer other than 409 and 429: a bug on our side. Never retried."""


class AlreadyHandled(Exception):
    """409: the ticket was already handled. Never retried."""


class UnknownOutcome(Exception):
    """A send timed out or the connection broke: the decision may or may not be saved."""


class HelpdeskUnavailable(Exception):
    """503s or network errors on every try."""


class Helpdesk:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = httpx.Client(
            base_url=settings.helpdesk_url,
            headers={
                "Authorization": f"Bearer {settings.helpdesk_key}",
                "X-Candidate-Email": settings.candidate_email,
            },
            timeout=config.HTTP_TIMEOUT,
            transport=transport,
        )
        self._name = settings.candidate_name
        self._sleep = sleep
        self._clock = clock
        self._last_call = float("-inf")
        self.stats: Counter[str] = Counter()  # attempts, retries_503, waits_429, timeouts

    def status(self) -> dict:
        headers = {"X-Candidate-Name": self._name} if self._name else None
        return self._request("GET", "/status", headers=headers)

    def examples(self) -> list[dict]:
        data = self._request("GET", "/examples")
        return data if isinstance(data, list) else data.get("examples", [])

    def list_open(self) -> list[dict]:
        """All open tickets. Follows next_cursor and collects every page before returning."""
        tickets: list[dict] = []
        cursor, seen = None, set()
        while True:
            params = {"limit": 10, "status": "open"}
            if cursor:
                params["cursor"] = cursor
            page = self._request("GET", "/tickets", params=params)
            tickets.extend(page.get("tickets", []))
            cursor = page.get("next_cursor")
            if not cursor or cursor in seen:
                return tickets
            seen.add(cursor)

    def is_handled(self, ticket_id: str) -> bool:
        """The server's open list is the only record of what is handled."""
        return all(ticket.get("id") != ticket_id for ticket in self.list_open())

    def send(self, ticket_id: str, action: str, body: dict) -> str:
        """POST one decision. Checks the ticket before every try, so a customer never gets two answers.
        Returns 'sent', 'skipped_already_handled' or 'confirmed_after_timeout'."""
        timed_out = False
        for _ in range(3):
            if self.is_handled(ticket_id):
                return "confirmed_after_timeout" if timed_out else "skipped_already_handled"
            try:
                self._request("POST", f"/tickets/{ticket_id}/{action}", json=body)
                return "sent"
            except UnknownOutcome:
                timed_out = True
                log.warning("%s: no answer to the send; checking the ticket before any retry", ticket_id)
        raise HelpdeskUnavailable(f"the send for {ticket_id} timed out 3 times")

    def reset(self) -> dict:
        return self._request("POST", "/practice/reset")

    def _wait_for_slot(self) -> None:
        """Keep calls at least 1 / CALLS_PER_SECOND seconds apart."""
        gap = 1 / config.CALLS_PER_SECOND - (self._clock() - self._last_call)
        if gap > 0:
            self._sleep(gap)
        self._last_call = self._clock()

    def _request(self, method: str, path: str, *, params: dict | None = None,
                 json: dict | None = None, headers: dict | None = None) -> Any:
        wait, errors, rate_limits = config.FIRST_WAIT, 0, 0
        while True:
            self._wait_for_slot()
            self.stats["attempts"] += 1
            try:
                response = self._client.request(method, path, params=params, json=json, headers=headers)
            except httpx.TransportError as error:
                self.stats["timeouts"] += 1
                if method == "POST":
                    raise UnknownOutcome(f"{method} {path}: {type(error).__name__}") from error
                errors += 1
                log.warning("%s %s: %s, try %d", method, path, type(error).__name__, errors)
            else:
                status = response.status_code
                if status < 300:
                    return response.json() if response.content else {}
                if status == 409:
                    raise AlreadyHandled(f"{method} {path}")
                if status == 429:
                    rate_limits += 1
                    if rate_limits > 10:
                        raise HelpdeskUnavailable(f"{method} {path}: rate limited 10 times in a row")
                    self.stats["waits_429"] += 1
                    self._sleep(_retry_after(response))
                    continue
                if status != 503:
                    raise HelpdeskError(f"{method} {path} answered {status}: {response.text[:300]}")
                errors += 1
                self.stats["retries_503"] += 1
                log.info("%s %s: 503, try %d", method, path, errors)
            if errors >= config.HTTP_RETRIES:
                raise HelpdeskUnavailable(f"{method} {path} failed {errors} times")
            self._sleep(wait + random.uniform(0, 0.1))
            wait = min(wait * 2, config.MAX_WAIT)


def _retry_after(response: httpx.Response) -> float:
    try:
        return float(response.headers.get("retry-after", "1"))
    except ValueError:
        return 1.0
