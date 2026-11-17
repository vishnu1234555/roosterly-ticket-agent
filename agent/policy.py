"""The final action, decided by plain code from the model's form.
No network and no model here, so every rule has a unit test.
Code may turn a reply into a handoff, never the reverse."""
from __future__ import annotations

from dataclasses import dataclass

from agent.prompts import Form

ALWAYS_HUMAN = (
    "refund_or_dispute", "cancel_or_contract_change", "personal_data_request",
    "security_incident", "legal_threat", "threat_to_leave",
)


@dataclass(frozen=True)
class Decision:
    action: str          # "reply", "handoff" or "close"
    override: str = ""   # why code changed the model's proposal; empty if it did not


def decide_action(form: Form, detected_language: str, tripwires: list[str], threshold: float) -> Decision:
    """The rules, in order. The first one that matches wins."""
    proposed = form.proposed_action
    if proposed == "handoff":
        return Decision("handoff")

    human_flags = [flag for flag in ALWAYS_HUMAN if flag in form.flags]
    if human_flags:
        return Decision("handoff", "client rule: " + ", ".join(human_flags))
    if tripwires:
        return Decision("handoff", "tripwire words for: " + ", ".join(tripwires))
    if "prompt_injection" in form.flags:
        return Decision("handoff", "the ticket tries to give the agent orders")
    if form.confidence < threshold:
        return Decision("handoff", f"confidence {form.confidence:.2f} is under {threshold}")

    if form.spam_or_empty:
        return Decision("close", "" if proposed == "close" else "the model marked it spam or empty")
    if proposed == "close":
        return Decision("handoff", "the model proposed close but did not mark it spam or empty")

    # From here on, the model proposed a reply.
    if not form.faq_ids:
        return Decision("handoff", "no help-centre entry answers it")
    if not form.covers_all:
        return Decision("handoff", "the help centre answers only part of it")
    if form.language == "other":
        return Decision("handoff", "the language is not Dutch, English or German")
    if detected_language not in ("unknown", form.language):
        return Decision("handoff", f"the language check says {detected_language}, the model says {form.language}")
    if not form.draft_reply.strip():
        return Decision("handoff", "the model wrote no reply")
    return Decision("reply")
