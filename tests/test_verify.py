from agent.prompts import Faq
from agent.verify import check_fence, check_reply

FAQ = Faq.load()
INVOICES = FAQ.text(["F06"])


def test_fence_passes_a_correct_reply():
    reply = ("Hoi Anouk,\n\nJe facturen staan onder Instellingen → Abonnement → Facturen. "
             "Ze worden op de 1e van elke maand gemaild.\n\nGroet,\nRoosterly Support")
    assert check_fence(reply, INVOICES, "") == []


def test_fence_passes_the_english_meaning_in_brackets():
    reply = "Go to Instellingen → Abonnement → Facturen (Settings → Subscription → Invoices)."
    assert check_fence(reply, INVOICES, "") == []


def test_fence_fails_on_a_made_up_link():
    assert check_fence("Kijk op www.roosterly.nl/facturen.", INVOICES, "") == ["link www.roosterly.nl/facturen"]


def test_fence_fails_on_a_made_up_number():
    assert check_fence("Facturen worden op de 5e gemaild.", INVOICES, "") == ["number 5"]


def test_fence_fails_on_a_changed_menu_name():
    assert check_fence("Ga naar Instellingen → Facturatie.", INVOICES, "") == ["menu step instellingen > facturatie"]


def test_fence_fails_on_a_made_up_email():
    assert check_fence("Mail ons op support@roosterly.nl.", INVOICES, "") == ["email support@roosterly.nl"]


def test_a_number_from_the_customer_is_allowed():
    prices = FAQ.text(["F05"])
    assert check_fence("Voor 12 medewerkers betaal je €6 per medewerker per maand.", prices,
                       "We hebben 12 medewerkers.") == []


def test_step_numbers_are_ignored():
    reply = "1. Ga naar Instellingen → Abonnement.\n2. Klik op Facturen."
    assert check_fence(reply, INVOICES, "") == []


def test_reply_language_check():
    dutch = "Hoi, je kunt de facturen vinden onder Instellingen. Ze worden op de 1e van de maand gemaild. Groet"
    assert check_reply(dutch, "nl", INVOICES, "").language_ok
    english = "Hi, you can find the invoices under Instellingen. They are emailed on the 1st of the month."
    assert not check_reply(english, "nl", INVOICES, "").language_ok
