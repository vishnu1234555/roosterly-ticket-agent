import json

import httpx

from agent.decide import decide_ticket
from agent.llm import LLM
from agent.prompts import SUPPORT_CHECK_PROMPT, Faq

FAQ = Faq.load()
TICKET = {"id": "X1", "channel": "email", "customer_plan": "Basis", "subject": "Nieuwe collega",
          "body": "Hallo, hoe nodig ik een nieuwe collega uit in de app? Groetjes, Sanne"}
GOOD_REPLY = ("Hoi Sanne,\n\nGa naar Team → Medewerker toevoegen, vul naam, e-mailadres en contracturen in "
              "en klik op Uitnodigen.\n\nGroet,\nRoosterly Support")


def form(**changes) -> dict:
    fields = dict(language="nl", category="question", priority="P4", faq_ids=["F02"], covers_all=True,
                  flags=[], spam_or_empty=False, proposed_action="reply", reason="How-to answered by F02.",
                  summary_en="Wants to invite a new colleague.", draft_reply=GOOD_REPLY, handoff_note="",
                  confidence=0.9)
    fields.update(changes)
    return fields


SUPPORTED = '{"supported": true, "unsupported": []}'


def fake_llm(settings, answers, seen=None, support=SUPPORTED) -> LLM:
    """A fake model: the support check gets `support`, other JSON calls get the next answer
    from the list, and the back-translation gets fixed text."""
    answers = iter(answers)

    def handler(request):
        body = json.loads(request.content)
        if seen is not None:
            seen.append(body)
        if body["messages"][0]["content"] == SUPPORT_CHECK_PROMPT:
            content = support
        elif "response_format" in body:
            content = next(answers)
        else:
            content = "Hi Sanne, go to Team ..."
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 20}})

    return LLM(settings, transport=httpx.MockTransport(handler), sleep=lambda seconds: None)


def test_a_good_reply_is_sent_as_a_reply(settings):
    decision = decide_ticket(TICKET, FAQ, fake_llm(settings, [json.dumps(form())]))
    assert decision.action == "reply"
    assert decision.body["draft_reply"] == GOOD_REPLY
    assert decision.log["back_translation"].startswith("Hi Sanne")
    assert "subject" not in decision.log and "body" not in decision.log


def test_a_reply_with_unsupported_statements_goes_to_a_human(settings):
    support = '{"supported": false, "unsupported": ["The export runs on Thursday."]}'
    decision = decide_ticket(TICKET, FAQ, fake_llm(settings, [json.dumps(form())], support=support))
    assert decision.action == "handoff"
    assert decision.log["checks"]["support"] == ["The export runs on Thursday."]
    assert "help centre does not" in decision.body["reason"]


def test_a_made_up_link_turns_the_reply_into_a_handoff(settings):
    bad = form(draft_reply=GOOD_REPLY + "\nMeer info: www.roosterly.nl/hulp")
    decision = decide_ticket(TICKET, FAQ, fake_llm(settings, [json.dumps(bad)]))
    assert decision.action == "handoff"
    assert "fact fence" in decision.body["reason"]
    assert decision.body["handoff_note"].startswith("Wants:")


def test_payment_details_are_masked_before_the_model_sees_them(settings):
    seen = []
    ticket = dict(TICKET, body="Graag terugbetalen op NL91 ABNA 0417 1643 00.")
    decide_ticket(ticket, FAQ, fake_llm(settings, [json.dumps(form(proposed_action="handoff"))], seen))
    sent_to_model = json.dumps(seen[0])
    assert "[IBAN]" in sent_to_model
    assert "0417" not in sent_to_model


def test_invalid_output_twice_goes_to_a_human(settings):
    decision = decide_ticket(TICKET, FAQ, fake_llm(settings, ["not json", "still not json"]))
    assert decision.action == "handoff"
    assert decision.usage.calls == 2
