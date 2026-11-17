"""Guess the language (nl, en or de) by counting very common words.
'unknown' means no opinion: too few common words, or two languages too close."""
from __future__ import annotations

import re

_COMMON = {
    "nl": set(
        "de het een en ik je jij wij niet van voor met op dat zijn hoe wat kan kunnen graag mijn onze ons "
        "bij naar ook maar als geen wel heb hebben u uw bedankt groet groeten hoi goedemorgen goedemiddag "
        "alvast dank zou moet wordt worden deze dit".split()
    ),
    "en": set(
        "the a and i you not of for with on that this are how what can please my our to it have do does "
        "hello hi thanks thank regards be but no would should your there from".split()
    ),
    "de": set(
        "der das ein eine und ich sie wir nicht ist von für mit auf dass sind kann bitte mein unser zu im "
        "es haben danke grüße gruß freundlichen guten uns auch aber kein bei können möchte wird werden "
        "ihr ihre sehr".split()
    ),
}
_WORD = re.compile(r"[^\W\d_]+")  # a run of letters, in any alphabet


def detect(text: str, min_hits: int = 3) -> str:
    """Return 'nl', 'en', 'de' or 'unknown'."""
    words = _WORD.findall(text.lower())
    counts = sorted(
        ((sum(word in common for word in words), lang) for lang, common in _COMMON.items()), reverse=True
    )
    (top, lang), (second, _) = counts[0], counts[1]
    if top < min_hits or top < 2 * second:
        return "unknown"
    return lang
