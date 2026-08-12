"""PACKAGEDESCRIPTION parsing.

FDA package descriptions are slash-separated nesting levels, e.g.:

    8 POUCH in 1 CARTON (0378-4642-26)  / 1 PATCH in 1 POUCH (0378-4642-16)  / 3.5 d in 1 PATCH
    4 PATCH in 1 CARTON (50419-451-04)  / 7 d in 1 PATCH (50419-451-01)
    8 POUCH in 1 CARTON (65162-993-08)  / 1 d in 1 POUCH (65162-993-04)
    56 SPRAY in 1 VIAL, MULTI-DOSE (0574-2067-27)
    1 BOTTLE, PUMP in 1 CARTON (21922-015-40)  / 50 g in 1 BOTTLE, PUMP
    100 TABLET in 1 BOTTLE (0555-0886-02)

Observed quirks (verified against the 2026-08-12 directory): the
parenthesized inner NDC is optional; separators carry irregular double
spaces; some rows have trailing spaces; the wear-duration level
("3.5 d in 1 PATCH" / "7 d in 1 PATCH") appears in only some patterns —
and "1 d in 1 POUCH" appears in Amneal rows where it does NOT describe
wear duration, so only the 3.5-day and 7-day values are treated as
schedule evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Units that measure quantity rather than count discrete sellable items.
_MEASURE_UNITS = {"d", "g", "gm", "kg", "mg", "ml", "l"}

_LEVEL_PATTERN = re.compile(
    r"^\s*(?P<count>\d+(?:\.\d+)?|\.\d+)\s+"
    r"(?P<unit>.+?)\s+in\s+1\s+"
    r"(?P<container>[^()]+?)\s*"
    r"(?:\((?P<ndc>[\d-]+)\)\s*)?$"
)

_WEAR_HOURS_BY_DAYS = {Decimal("3.5"): 84.0, Decimal("7"): 168.0}


@dataclass(frozen=True)
class PackageLevel:
    count: Decimal
    unit: str
    container: str
    inner_ndc: str | None


@dataclass(frozen=True)
class PackageInfo:
    """Parsed package facts.

    ``pack_count`` is None when the outermost quantity is a measure
    (grams, liters) or the description resisted parsing — resolvers must
    tolerate that. ``wear_hours`` is set only from the verified wear
    values (3.5 d → 84, 7 d → 168).
    """

    pack_count: int | None
    pack_unit: str | None
    wear_hours: float | None
    levels: tuple[PackageLevel, ...]


def parse_package_description(description: str | None) -> PackageInfo:
    if not description or not description.strip():
        return PackageInfo(None, None, None, ())

    levels: list[PackageLevel] = []
    for chunk in description.split("/"):
        chunk = chunk.strip()
        if not chunk:
            continue
        match = _LEVEL_PATTERN.match(chunk)
        if match is None:
            continue
        try:
            count = Decimal(match.group("count"))
        except InvalidOperation:  # pragma: no cover - pattern guarantees digits
            continue
        levels.append(
            PackageLevel(
                count=count,
                unit=match.group("unit").strip(),
                container=match.group("container").strip(),
                inner_ndc=match.group("ndc"),
            )
        )

    pack_count, pack_unit = _sellable_count(levels)
    return PackageInfo(
        pack_count=pack_count,
        pack_unit=pack_unit,
        wear_hours=_wear_hours(levels),
        levels=tuple(levels),
    )


def _sellable_count(levels: list[PackageLevel]) -> tuple[int | None, str | None]:
    """Multiply countable nesting levels until a measure unit terminates.

    "8 POUCH in 1 CARTON / 1 PATCH in 1 POUCH / 3.5 d in 1 PATCH" → 8.
    "2 POUCH in 1 CARTON / 4 PATCH in 1 POUCH" → 8.
    "1 BOTTLE, PUMP in 1 CARTON / 50 g in 1 BOTTLE, PUMP" → 1.
    ".21 L in 1 CYLINDER" → None (measure-dispensed).
    """
    total: Decimal | None = None
    unit: str | None = None
    for level in levels:
        unit_word = level.unit.split(",")[0].strip().lower()
        if unit_word in _MEASURE_UNITS:
            break
        total = level.count if total is None else total * level.count
        unit = level.unit
    if total is None:
        return None, None
    if total != total.to_integral_value():
        return None, None
    return int(total), unit


def _wear_hours(levels: list[PackageLevel]) -> float | None:
    for level in levels:
        if level.unit.strip().lower() == "d":
            hours = _WEAR_HOURS_BY_DAYS.get(level.count)
            if hours is not None and level.container.split(",")[0].strip().upper() in {
                "PATCH",
                "SYSTEM",
                "FILM",
            }:
                return hours
    return None
