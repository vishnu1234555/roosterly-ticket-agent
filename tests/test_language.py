import pytest

from agent.language import detect


@pytest.mark.parametrize("text, expected", [
    ("Hoe kan ik een nieuwe collega toevoegen aan het rooster? Alvast bedankt.", "nl"),
    ("How do I add a new colleague to the rota? Thanks in advance.", "en"),
    ("Wie kann ich einen neuen Kollegen hinzufügen? Ich habe es nicht gefunden. Danke!", "de"),
])
def test_detects_the_language(text, expected):
    assert detect(text) == expected


def test_short_text_is_unknown():
    assert detect("Wachtwoord vergeten") == "unknown"
