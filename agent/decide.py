"""Steps 2 to 5 for one ticket: mask it, ask the model, let code decide, check a reply.
run.py and the eval both use this, so the eval measures the real agent. Nothing is sent here."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from agent import config, language, tripwires, verify
from agent.llm import LLM, ModelFailed, ProviderUnavailable, Usage
from agent.policy import Decision, decide_action
from agent.prompts import Faq, Form, system_prompt, ticket_message
from agent.redact import assert_clean, mask

log = logging.getLogger(__name__)


@dataclass
class TicketDecision:
    action: str   # "reply", "handoff" or "close"
    body: dict    # what is sent to the helpdesk
    log: dict     # fields for the log line: no subject and no body
    usage: Usage = field(default_factory=Usage)


def decide_ticket(ticket: dict, faq: Faq, llm: LLM) -> TicketDecision:
    subject, subject_kinds = mask(ticket.get("subject") or "")
    body, body_kinds = mask(ticket.get("body") or "")
    payment_kinds = sorted(set(subject_kinds + body_kinds))
    plan = ticket.get("customer_plan") or "unknown"
    channel = ticket.get("channel") or "unknown"
    text = f"{subject}\n{body}"
    detected = language.detect(text)
    trips = tripwires.find(text)
    usage = Usage()
    facts = {"ticket_id": ticket.get("id"), "channel": channel, "customer_plan": plan,
             "detected_language": detected, "tripwires": trips, "payment_kinds_found": payment_kinds}

    try:
        form = llm.form(system_prompt(faq), ticket_message(subject, body, plan, channel), Form, usage)
    except ModelFailed:
        log.warning("%s: no valid form from the model, so it goes to a human", ticket.get("id"))
        return _model_failed(facts, detected, usage)

    form.faq_ids = [faq_id for faq_id in form.faq_ids if faq_id in faq.entries]
    decision = decide_action(form, detected, trips, config.CONFIDENCE_THRESHOLD)
    checks, english = None, None
    if decision.action == "reply":
        result = verify.check_reply(form.draft_reply, form.language, faq.text(form.faq_ids), text)
        checks = result.as_log()
        if not result.passed:
            decision = Decision("handoff", "the reply failed its checks: " + result.failures())
        else:
            english = _back_translation(llm, form.draft_reply, usage)

    post = _post_body(form, decision, detected, facts)
    assert_clean(json.dumps(post, ensure_ascii=False))
    log_fields = {
        **facts,
        "language": post["language"], "category": post["category"], "priority": post["priority"],
        "action": decision.action, "model_action": form.proposed_action, "override": decision.override or None,
        "faq_ids": form.faq_ids, "flags": form.flags, "confidence": form.confidence, "reason": post["reason"],
        "checks": checks, "back_translation": english,
        "llm": _llm_fields(llm, usage),
    }
    return TicketDecision(decision.action, post, log_fields, usage)


def _post_body(form: Form, decision: Decision, detected: str, facts: dict) -> dict:
    """The JSON body for the helpdesk."""
    if form.language != "other":
        lang = form.language
    else:  # the API only takes nl, en or de: use the closest one, and the reason says so
        lang = detected if detected != "unknown" else "en"
    reason = form.reason.strip()
    if decision.override:
        reason = f"Changed to {decision.action} by a rule: {decision.override[:200]}. Model: {_first_sentence(reason)}"
    body = {"language": lang, "category": form.category, "priority": form.priority,
            "reason": reason, "confidence": round(form.confidence, 2)}
    if decision.action == "reply":
        body["draft_reply"] = form.draft_reply.strip()
    elif decision.action == "handoff":
        body["handoff_note"] = _handoff_note(form, decision, facts)
    return body


def _handoff_note(form: Form, decision: Decision, facts: dict) -> str:
    """The model's note when it chose the handoff itself. When code overrode a reply, code writes
    the note from the form, so no second model call is needed."""
    if not decision.override and form.handoff_note.strip():
        note = form.handoff_note.strip()
    else:
        faq_ids = ", ".join(form.faq_ids) or "none"
        next_step = f"answer it; {faq_ids} may cover part of it." if form.faq_ids else "answer it; the help centre does not cover it."
        note = (
            f"Wants: {form.summary_en.strip() or 'see the ticket'}\n"
            f"Why human: {decision.override or form.reason.strip()}\n"
            f"Facts: plan {facts['customer_plan']}, channel {facts['channel']}, language {form.language}, "
            f"FAQ entries {faq_ids}.\n"
            f"Next step: {next_step}"
        )
    if facts["payment_kinds_found"]:
        note += f"\nNote: the customer shared payment details ({', '.join(facts['payment_kinds_found'])}). They were masked."
    return note


def _model_failed(facts: dict, detected: str, usage: Usage) -> TicketDecision:
    reason = "The model gave no valid decision twice, so a human checks this ticket."
    note = (
        "Wants: unknown; the model could not read this ticket.\n"
        "Why human: the model gave no valid answer twice.\n"
        f"Facts: plan {facts['customer_plan']}, channel {facts['channel']}.\n"
        "Next step: read the ticket and answer it."
    )
    post = {"language": detected if detected != "unknown" else "nl", "category": "other", "priority": "P3",
            "reason": reason, "handoff_note": note, "confidence": 0.0}
    log_fields = {**facts, "language": post["language"], "category": "other", "priority": "P3",
                  "action": "handoff", "model_action": None, "override": "model failed", "faq_ids": [],
                  "flags": [], "confidence": 0.0, "reason": reason, "checks": None, "back_translation": None,
                  "llm": {"model": None, "prompt_version": config.PROMPT_VERSION, "calls": usage.calls,
                          "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}}
    return TicketDecision("handoff", post, log_fields, usage)


def _back_translation(llm: LLM, reply: str, usage: Usage) -> str | None:
    try:
        return verify.back_translate(llm, reply, usage)
    except (ModelFailed, ProviderUnavailable) as error:  # the log loses the translation; the reply still goes
        log.warning("Back-translation failed: %s", error)
        return None


def _llm_fields(llm: LLM, usage: Usage) -> dict:
    return {"model": llm.model, "prompt_version": config.PROMPT_VERSION, "calls": usage.calls,
            "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}


def _first_sentence(text: str) -> str:
    end = text.find(". ")
    return text if end == -1 else text[: end + 1]
