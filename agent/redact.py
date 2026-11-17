"""Mask payment details (IBANs and card numbers) before text goes to the model, the helpdesk or a log."""
from __future__ import annotations

import re

# IBAN: 2 letters, 2 digits, then 11 to 30 letters or digits. Spaces allowed. Any letter case.
_IBAN = re.compile(r"\b[A-Za-z]{2}\d{2}(?: ?[A-Za-z0-9]){11,30}\b")
# Card: 13 to 19 digits, with a space or a dash allowed between digits.
_CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")
_SHORTEST_IBAN = 15  # Norway; every other country's IBAN is longer


def _iban_part(found: str) -> str | None:
    """The IBAN pattern can run on into the words after an IBAN ('... 00 bedankt').
    Keep parts until the IBAN is long enough and a plain word starts; the rest is given back.
    Returns the IBAN, or None if it does not look like one (too short, or too few digits)."""
    kept: list[str] = []
    for part in found.split(" "):
        if len("".join(kept)) >= _SHORTEST_IBAN and part.isalpha():
            break
        kept.append(part)
    iban = " ".join(kept)
    digits = sum(char.isdigit() for char in iban[4:])
    return iban if len(iban.replace(" ", "")) >= _SHORTEST_IBAN and digits >= 8 else None


def _mask_ibans(text: str, kinds: set[str]) -> str:
    """Replace each IBAN with [IBAN]. After each one, look again right where it ended,
    because the words given back may hold the start of the next IBAN."""
    out, position = [], 0
    while match := _IBAN.search(text, position):
        iban = _iban_part(match.group(0))
        if iban is None:  # not an IBAN here; look again from the next character
            out.append(text[position:match.start() + 1])
            position = match.start() + 1
            continue
        kinds.add("IBAN")
        out.append(text[position:match.start()] + "[IBAN]")
        position = match.start() + len(iban)
    out.append(text[position:])
    return "".join(out)


def mask(text: str) -> tuple[str, list[str]]:
    """Return the text with [IBAN] and [CARD] in place of payment details, and the kinds found.
    It masks on shape alone: a wrong mask costs little, a missed number breaks a client rule."""
    kinds: set[str] = set()
    text = _mask_ibans(text, kinds)
    text, cards = _CARD.subn("[CARD]", text)
    if cards:
        kinds.add("CARD")
    return text, sorted(kinds)


def assert_clean(text: str) -> None:
    """Raise if a payment pattern is still in text that is about to be sent or logged."""
    kinds = mask(text)[1]
    if kinds:
        raise ValueError(f"payment detail ({', '.join(kinds)}) in outgoing text")
