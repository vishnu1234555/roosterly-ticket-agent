import pytest

from agent.tripwires import find


@pytest.mark.parametrize("text, topic", [
    ("Ik wil mijn abonnement opzeggen.", "cancel_or_contract_change"),
    ("Kunnen we die maand terugbetaald krijgen?", "refund_or_dispute"),
    ("Ik schakel mijn advocaat in.", "legal_threat"),
    ("Iemand heeft ons account gehackt!", "security_incident"),
    ("Please delete my personal data.", "personal_data_request"),
    ("We stappen over naar een andere aanbieder.", "threat_to_leave"),
    ("Ich möchte kündigen.", "cancel_or_contract_change"),
])
def test_finds_the_topic(text, topic):
    assert topic in find(text)


@pytest.mark.parametrize("text", [
    "Hoe vul ik de contracturen in voor een nieuwe medewerker?",
    "Waar vind ik Instellingen → Juridisch?",
    "Hoe kan een medewerker een dienst ruilen?",
    "Hoe stap ik over naar Plus?",
])
def test_an_ordinary_how_to_trips_nothing(text):
    assert find(text) == []
