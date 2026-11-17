"""Checks on a draft reply before it may be sent. Any failed check turns the reply into a handoff.
These let you check a Dutch reply without reading Dutch."""
from __future__ import annotations

import re
from dataclasses import dataclass

from agent import language
from agent.llm import LLM, Usage
from agent.prompts import BACK_TRANSLATION_PROMPT
from agent.redact import mask

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_LINK = re.compile(r"(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s)\]\"'<>,]*)?", re.IGNORECASE)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
_STEP_NUMBER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)  # "1. " or "2) " at the start of a line
_MENU_STEP = re.compile(r"([^\W_]+)\s*(?:->|=>|→|»|>)\s*(?=([^\W_]+))")  # "Instellingen → Abonnement"


def _numbers(text: str) -> set[str]:
    """The numbers in a text. '4,00' and '4.00' count as '4'."""
    return {re.sub(r"[.,]0+$", "", number) for number in _NUMBER.findall(text)}


def _products(faq_numbers: set[str], ticket_numbers: set[str]) -> set[str]:
    """An FAQ number times a number from the customer's message, such as 6 x 25 = 150.
    A reply may use these, so a correct total is not taken for a made-up number."""
    products = set()
    for a in faq_numbers:
        for b in ticket_numbers:
            try:
                value = float(a.replace(",", ".")) * float(b.replace(",", "."))
                products.add(str(int(value)) if value.is_integer() else f"{value:.2f}")
            except ValueError:
                continue
    return products


def _menu_steps(text: str) -> set[tuple[str, str]]:
    """Pairs of menu names joined by an arrow, such as ('instellingen', 'abonnement')."""
    return {(first.lower(), second.lower()) for first, second in _MENU_STEP.findall(text)}


def check_fence(reply: str, faq_text: str, ticket_text: str) -> list[str]:
    """The fact fence: every email, link, number and menu step in the reply must appear in the
    cited FAQ entries. A number may also come from the customer's own message.
    Returns what failed; an empty list means the reply passed."""
    problems = []
    faq_lower = faq_text.lower()
    for email in _EMAIL.findall(reply):
        if email.lower() not in faq_lower:
            problems.append(f"email {email}")
    rest = _EMAIL.sub(" ", reply)
    for link in _LINK.findall(rest):
        link = link.rstrip(".,;:!?/")
        if link.lower() not in faq_lower:
            problems.append(f"link {link}")
    rest = _STEP_NUMBER.sub(" ", _LINK.sub(" ", rest))
    faq_numbers, ticket_numbers = _numbers(faq_text), _numbers(ticket_text)
    allowed = faq_numbers | ticket_numbers | _products(faq_numbers, ticket_numbers)
    for number in sorted(_numbers(rest) - allowed):
        problems.append(f"number {number}")
    for first, second in sorted(_menu_steps(reply) - _menu_steps(faq_text)):
        problems.append(f"menu step {first} > {second}")
    return problems


@dataclass(frozen=True)
class ReplyCheck:
    language_ok: bool
    fence_problems: list[str]
    payment_ok: bool

    @property
    def passed(self) -> bool:
        return self.language_ok and not self.fence_problems and self.payment_ok

    def failures(self) -> str:
        failed = []
        if not self.language_ok:
            failed.append("reply language")
        if self.fence_problems:
            failed.append("fact fence (" + "; ".join(self.fence_problems) + ")")
        if not self.payment_ok:
            failed.append("payment detail in the reply")
        return ", ".join(failed)

    def as_log(self) -> dict:
        return {"language": self.language_ok, "fence": self.fence_problems or "pass", "payment": self.payment_ok}


def check_reply(reply: str, expected_language: str, faq_text: str, ticket_text: str) -> ReplyCheck:
    return ReplyCheck(
        language_ok=language.detect(reply) in ("unknown", expected_language),
        fence_problems=check_fence(reply, faq_text, ticket_text),
        payment_ok=not mask(reply)[1],
    )


def back_translate(llm: LLM, reply: str, usage: Usage) -> str:
    """A separate model call that sees only the reply, so every reply can be read in English."""
    return llm.text(BACK_TRANSLATION_PROMPT, reply, usage)
