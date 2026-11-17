import pytest

from agent.policy import decide_action, decide_priority
from agent.prompts import Form


def form(**changes) -> Form:
    """A good reply form; each test changes one thing."""
    fields = dict(
        language="nl", category="question", priority="P4", faq_ids=["F02"], covers_all=True, flags=[],
        spam_or_empty=False, proposed_action="reply", reason="How-to answered by F02.",
        summary_en="Wants to add an employee.", draft_reply="Hoi, ga naar Team → Medewerker toevoegen.",
        handoff_note="", confidence=0.9,
    )
    fields.update(changes)
    return Form(**fields)


def decide(f: Form, detected: str = "nl", trips: list[str] | None = None):
    return decide_action(f, detected, trips or [], threshold=0.75)


def test_a_good_reply_stays_a_reply():
    assert decide(form()).action == "reply"
    assert decide(form()).override == ""


def test_a_flag_beats_a_proposed_reply():
    result = decide(form(flags=["refund_or_dispute"]))
    assert result.action == "handoff"
    assert "refund_or_dispute" in result.override


def test_a_tripwire_beats_a_proposed_reply():
    assert decide(form(), trips=["legal_threat"]).action == "handoff"


def test_orders_in_the_ticket_mean_handoff():
    assert decide(form(flags=["prompt_injection"])).action == "handoff"


def test_code_never_turns_a_handoff_into_a_reply():
    assert decide(form(proposed_action="handoff")).action == "handoff"


def test_spam_is_closed():
    assert decide(form(spam_or_empty=True, proposed_action="close", faq_ids=[])).action == "close"


def test_spam_with_a_flag_goes_to_a_human():
    assert decide(form(spam_or_empty=True, proposed_action="close", flags=["legal_threat"])).action == "handoff"


def test_close_without_spam_goes_to_a_human():
    assert decide(form(proposed_action="close")).action == "handoff"


@pytest.mark.parametrize("changes, detected", [
    ({"faq_ids": []}, "nl"),                 # no FAQ entry answers it
    ({"covers_all": False}, "nl"),           # only part is answered
    ({"language": "other"}, "unknown"),      # not Dutch, English or German
    ({}, "en"),                              # the word count says English, the model says Dutch
    ({"confidence": 0.5}, "nl"),             # unsure
    ({"draft_reply": "  "}, "nl"),           # no reply text
])
def test_unsure_cases_go_to_a_human(changes, detected):
    assert decide(form(**changes), detected=detected).action == "handoff"


def test_unknown_language_check_is_no_disagreement():
    assert decide(form(), detected="unknown").action == "reply"


def test_security_or_legal_risk_is_always_p1():
    assert decide_priority(form(priority="P2", flags=["legal_threat"]), []) == "P1"
    assert decide_priority(form(priority="P3"), ["security_incident"]) == "P1"


def test_other_tickets_keep_the_model_priority():
    assert decide_priority(form(priority="P4", flags=["refund_or_dispute"]), []) == "P4"
