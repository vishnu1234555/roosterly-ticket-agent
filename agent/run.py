"""Handle every open ticket once: python -m agent.run [--dry-run] [--limit N]

For each ticket: decide it (agent/decide.py), check it is still open, send, write one log line.
After the loop, tickets that failed get one more try. Exit code 1 if a ticket was left open."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from collections import Counter
from contextlib import contextmanager
from typing import Iterator

from agent.config import ROOT, Settings, load_settings
from agent.decide import TicketDecision, decide_ticket
from agent.helpdesk import AlreadyHandled, Helpdesk, HelpdeskError, HelpdeskUnavailable
from agent.llm import LLM, ProviderConfigError, ProviderUnavailable, Usage
from agent.logbook import Logbook
from agent.prompts import Faq

log = logging.getLogger("agent")
LOCK = ROOT / ".agent.lock"


@contextmanager
def run_lock() -> Iterator[None]:
    """Stop a second copy of the agent from running at the same time."""
    try:
        handle = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit(
            "Another run is going (.agent.lock exists). If none is, for example after a crash, "
            "delete .agent.lock and start again."
        ) from None
    os.write(handle, str(os.getpid()).encode())
    os.close(handle)
    try:
        yield
    finally:
        LOCK.unlink(missing_ok=True)


class Run:
    def __init__(self, helpdesk: Helpdesk, llm: LLM, faq: Faq, book: Logbook, dry_run: bool) -> None:
        self.helpdesk, self.llm, self.faq, self.book, self.dry_run = helpdesk, llm, faq, book, dry_run
        self.decisions: dict[str, TicketDecision] = {}  # kept, so a second try does not ask the model again
        self.usage = Usage()
        self.statuses: Counter[str] = Counter()
        self.actions: Counter[str] = Counter()
        self.overrides = 0

    def handle(self, ticket: dict, last_try: bool) -> bool:
        """Decide and send one ticket, and log it once it reaches a final state.
        Returns False if it failed and may get one more try."""
        ticket_id = ticket["id"]
        started = time.monotonic()
        http_before = self.helpdesk.stats.copy()
        decision = self.decisions.get(ticket_id)
        try:
            if decision is None:
                decision = decide_ticket(ticket, self.faq, self.llm)
                self.decisions[ticket_id] = decision
                self.usage.add(decision.usage)
            status = "dry_run" if self.dry_run else self.helpdesk.send(ticket_id, decision.action, decision.body)
        except AlreadyHandled:
            status = "conflict_409"
        except (ProviderUnavailable, ProviderConfigError):
            self.record(ticket_id, decision, "failed_left_open", started, http_before, "the model provider stopped the run")
            raise
        except Exception as error:  # one bad ticket must not stop the run
            log.warning("%s failed: %s: %s", ticket_id, type(error).__name__, error)
            if last_try:
                self.record(ticket_id, decision, "failed_left_open", started, http_before, f"{type(error).__name__}: {error}")
            return False
        self.record(ticket_id, decision, status, started, http_before)
        return True

    def record(self, ticket_id: str, decision: TicketDecision | None, status: str,
               started: float, http_before: Counter, error: str | None = None) -> None:
        """Write the ticket's one log line and count it for the summary."""
        self.statuses[status] += 1
        if decision is not None and status in ("sent", "confirmed_after_timeout", "dry_run"):
            self.actions[decision.action] += 1
            self.overrides += bool(decision.log.get("override"))
        line = dict(decision.log) if decision is not None else {"ticket_id": ticket_id}
        line.update(status=status, http=dict(self.helpdesk.stats - http_before),
                    latency_ms=round((time.monotonic() - started) * 1000))
        if error:
            line["error"] = error[:300]
        self.book.write(line)
        if decision is not None:
            log.info("%s: %s, %s, %s -> %s", ticket_id, decision.action, decision.body["category"],
                     decision.body["priority"], status)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Handle every open Roosterly ticket once.")
    parser.add_argument("--dry-run", action="store_true", help="decide, check and log, but send nothing")
    parser.add_argument("--limit", type=int, default=0, help="handle only the first N open tickets")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    settings = load_settings()
    with run_lock():
        try:
            return _run(settings, args.dry_run, args.limit)
        except KeyboardInterrupt:
            log.error("Stopped by you. Run the same command again: it continues with the tickets still open.")
            return 130
        except (HelpdeskError, HelpdeskUnavailable) as error:
            log.error("The helpdesk failed: %s", error)
            return 2


def _run(settings: Settings, dry_run: bool, limit: int) -> int:
    helpdesk, llm, faq = Helpdesk(settings), LLM(settings), Faq.load()
    book = Logbook("dryrun" if dry_run else "run")
    run = Run(helpdesk, llm, faq, book, dry_run)
    started = time.monotonic()

    log.info("Status before: %s", helpdesk.status())
    tickets = helpdesk.list_open()
    if limit:
        tickets = tickets[:limit]
    log.info("%d open tickets to handle%s", len(tickets), " (dry run: nothing is sent)" if dry_run else "")

    stopped = False
    try:
        failed = []
        for ticket in tickets:
            if not run.handle(ticket, last_try=dry_run):
                failed.append(ticket)
        if failed and not dry_run:
            log.info("One more try for %d tickets", len(failed))
            still_open = {ticket["id"] for ticket in helpdesk.list_open()}
            for ticket in failed:
                if ticket["id"] in still_open:
                    run.handle(ticket, last_try=True)
                else:
                    run.record(ticket["id"], run.decisions.get(ticket["id"]), "skipped_already_handled",
                               time.monotonic(), helpdesk.stats.copy())
    except (ProviderUnavailable, ProviderConfigError) as error:
        log.error("Stopped: %s. Tickets not handled yet stay open; run again later.", error)
        stopped = True

    decided = len(run.decisions)
    total = sum(run.actions.values())
    log.info("Done in %.0f s. Actions: %s. Handoff rate: %s. Changed by code: %d.",
             time.monotonic() - started, dict(run.actions),
             f"{run.actions['handoff'] / total:.0%}" if total else "n/a", run.overrides)
    log.info("Statuses: %s. Helpdesk calls: %s.", dict(run.statuses), dict(helpdesk.stats))
    if decided:
        log.info("Model: %d calls, %d input and %d output tokens, about $%.4f, so $%.4f per 100 tickets.",
                 run.usage.calls, run.usage.input_tokens, run.usage.output_tokens,
                 run.usage.cost_usd(), run.usage.cost_usd() / decided * 100)
    log.info("Log file: %s", book.path)
    if not dry_run:
        log.info("Status after: %s", helpdesk.status())
    return 1 if stopped or run.statuses["failed_left_open"] else 0


if __name__ == "__main__":
    sys.exit(main())
