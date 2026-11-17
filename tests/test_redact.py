import pytest

from agent.redact import assert_clean, mask


@pytest.mark.parametrize("iban", [
    "NL91ABNA0417164300",            # no spaces
    "NL91 ABNA 0417 1643 00",        # with spaces
    "nl91abna0417164300",            # lower case
    "DE89 3704 0044 0532 0130 00",   # German
    "BE68 5390 0754 7034",           # Belgian, ends on a full group of four
])
def test_iban_is_masked(iban):
    assert mask(f"Mijn rekening is {iban}.") == ("Mijn rekening is [IBAN].", ["IBAN"])


def test_word_after_an_iban_is_kept():
    assert mask("NL91 ABNA 0417 1643 00 bedankt")[0] == "[IBAN] bedankt"
    assert mask("BE68 5390 0754 7034 niet gebruiken")[0] == "[IBAN] niet gebruiken"


@pytest.mark.parametrize("card", [
    "4111111111111111", "4111 1111 1111 1111", "4111-1111-1111-1111", "3782 822463 10005",
])
def test_card_is_masked(card):
    assert mask(f"Kaart: {card}, graag.") == ("Kaart: [CARD], graag.", ["CARD"])


def test_two_numbers_in_one_text():
    masked, kinds = mask("IBAN NL91ABNA0417164300 of kaart 4111 1111 1111 1111.")
    assert masked == "IBAN [IBAN] of kaart [CARD]."
    assert kinds == ["CARD", "IBAN"]


def test_two_ibans_close_together():
    assert mask("NL91 ABNA 0417 1643 00 en BE68 5390 0754 7034")[0] == "[IBAN] en [IBAN]"


def test_a_week_number_is_not_an_iban():
    text = "Rooster wk12 voor de hele maand graag aanpassen"
    assert mask(text) == (text, [])


def test_an_iban_soon_after_a_week_number_is_still_masked():
    assert mask("wk12 roosters voor de NL91 ABNA 0417 1643 00")[0] == "wk12 roosters voor de [IBAN]"


@pytest.mark.parametrize("text", [
    "Bel me op +31 6 12345678",
    "Plus kost €6 per actieve medewerker per maand",
    "De link is 60 minuten geldig",
    "iOS 16 en Android 10",
    "Ontvangen op 2026-10-05T09:02:00+00:00",
])
def test_normal_text_is_untouched(text):
    assert mask(text) == (text, [])


def test_assert_clean():
    assert_clean("Nothing to see here, 60 minutes.")
    with pytest.raises(ValueError):
        assert_clean("card 4111 1111 1111 1111")
