"""Therapeutic Equivalence (TE) code parsing.

Orange Book preface (46th ed.): "Drugs coded with a three-character code
under a heading are considered therapeutically equivalent only to other
drugs coded with the same three-character code under that heading."

A "heading" is (identical active ingredients, dosage form, route) — so a
TE code is meaningful only inside its heading, and the numeric subscript
is a hard partition boundary: AB1 is never substitutable with AB2, and
comparing subscripts across headings is meaningless.

A blank TE code means "no evaluation" (single-source, discontinued, or
unrated) — it must never be treated as a wildcard or grouped with other
blanks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TE_PATTERN = re.compile(r"^([AB][A-Z*]?)(\d*)$")


@dataclass(frozen=True)
class TECode:
    letter_class: str
    subscript: str

    @property
    def full(self) -> str:
        return f"{self.letter_class}{self.subscript}"

    @property
    def a_rated(self) -> bool:
        return self.letter_class.startswith("A")

    def __str__(self) -> str:
        return self.full


def parse_te_code(text: str | None) -> TECode | None:
    """Parse a TE code string; blank/None → None (no evaluation)."""
    if text is None:
        return None
    cleaned = text.strip().upper()
    if not cleaned:
        return None
    match = _TE_PATTERN.fullmatch(cleaned)
    if match is None:
        # Unknown spelling — preserve verbatim as a letter class with no
        # subscript so it can still be displayed, but never silently drop.
        return TECode(letter_class=cleaned, subscript="")
    return TECode(letter_class=match.group(1), subscript=match.group(2))
