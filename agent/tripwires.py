"""Words that always send a ticket to a human, in Dutch, English and German.

A safety net for when the model misses one of the client's always-human topics.
They run on the original (masked) ticket text, because a translation can lose a word.
Each line is a regular expression; \\w* means "any word ending".
"""
from __future__ import annotations

import re

_TOPICS: dict[str, list[str]] = {
    "refund_or_dispute": [
        r"terugbeta+l\w*", r"geld terug", r"restitutie\w*", r"terugstort\w*", r"teruggestort", r"creditnota",
        r"betwist\w*", r"(?:onterecht|ten onrechte)\w* (?:afgeschreven|gefactureerd|in rekening)",
        r"dubbel (?:betaald|afgeschreven|gefactureerd)",
        r"refund\w*", r"money back", r"charged twice", r"double charged", r"overcharged", r"chargeback",
        r"dispute (?:a |the |this )?(?:charge|invoice|payment)",
        r"rückerstatt\w*", r"erstattung\w*", r"geld zurück", r"doppelt (?:abgebucht|berechnet)",
    ],
    "cancel_or_contract_change": [
        r"opzeg\w*", r"opgezegd", r"(?:abonnement|contract|account) (?:stopzetten|be[eë]indigen|annuleren|opheffen)",
        r"downgrad\w*", r"pauzer\w*",
        r"cancel (?:my|our|the) (?:subscription|account|contract|plan)",
        r"terminate (?:my|our|the) (?:subscription|account|contract)",
        r"kündig\w*", r"vertrag (?:beenden|auflösen)", r"abo\w* (?:beenden|stornieren)",
    ],
    "personal_data_request": [
        r"inzageverzoek\w*", r"recht op (?:inzage|vergetelheid|verwijdering)",
        r"(?:verwijder|wis) (?:al )?(?:mijn|onze|zijn|haar) (?:persoons)?gegevens", r"gegevens (?:laten )?verwijderen",
        r"delete (?:my|our|his|her|all) (?:personal )?data", r"right to (?:be forgotten|erasure)",
        r"subject access", r"auskunftsersuchen", r"(?:meine|unsere|seine|ihre) daten löschen",
    ],
    "security_incident": [
        r"gehackt", r"hack\w*", r"datalek\w*", r"phishing",
        r"onbekende (?:login|inlog\w*)", r"verdacht\w* (?:login|inlog\w*|activiteit)",
        r"breach\w*", r"data leak\w*", r"unauthori[sz]ed", r"suspicious (?:login|activity)",
        r"datenleck\w*", r"unbefugt\w*", r"verdächtig\w* (?:login|anmeldung|aktivität)",
    ],
    "legal_threat": [
        r"advocaat", r"juridische (?:stappen|actie)", r"rechtszaak", r"naar de rechter", r"ingebrekestelling",
        r"dagvaard\w*", r"aansprakelijk (?:stellen|gesteld)", r"autoriteit persoonsgegevens",
        r"lawyer", r"attorney", r"legal action", r"lawsuit", r"(?:will|going to|we'll|i'll) sue", r"(?:to|in) court",
        r"anwalt", r"rechtsanwalt", r"verklag\w*", r"rechtliche schritte", r"vor gericht",
    ],
    "threat_to_leave": [
        r"overstap\w* naar (?:een )?ander\w*", r"andere (?:aanbieder|leverancier|tool|app)",
        r"(?:naar|bij) (?:een |de )?concurrent\w*", r"(?:we|wij|ik) (?:gaan|stoppen) (?:weg|met roosterly)",
        r"switch\w* to (?:another|a different|a competitor)", r"competitor\w*", r"leav\w* roosterly",
        r"look(?:ing)? elsewhere",
        r"anbieter wechseln", r"konkurren\w*", r"wechseln zu (?:einem )?anderen",
    ],
}

_PATTERNS = {
    topic: re.compile(r"(?<!\w)(?:" + "|".join(words) + r")(?!\w)", re.IGNORECASE)
    for topic, words in _TOPICS.items()
}


def find(text: str) -> list[str]:
    """The always-human topics whose words appear in the text."""
    return [topic for topic, pattern in _PATTERNS.items() if pattern.search(text)]
