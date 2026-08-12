"""Strength canonicalization across data sources.

The same product's strength is spelled differently in every dataset:

    NDC Directory   ACTIVE_NUMERATOR_STRENGTH=".05"  ACTIVE_INGRED_UNIT="mg/d"
    NDC Directory   "14" + "ug/d"                    (Menostar — unit differs!)
    Orange Book     "0.05MG/24HR"
    Orange Book     "0.1% (0.25GM/PACKET)"           (gels)
    Orange Book     "1.53MG/SPRAY"
    Orange Book     "0.5MG **Federal Register determination that product
                     was not discontinued or withdrawn ...**"  (suffix!)
    RxNorm          "0.00208 MG/HR"                  (never used for joins)

This module reduces each spelling to a canonical string so that equality
means "same strength". Canonical kinds:

    UG24H:<n>       rate products — micrograms per 24 hours
    UG:<n>          mass per discrete unit (tablet, spray actuation)
    PCT:<p>;G:<g>   concentration % with per-packet/actuation grams
    RAW:<text>      anything unrecognized — normalized text, safe inequality

All arithmetic is exact ``Decimal``; floats never appear.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_FR_SUFFIX_MARKER = " **"

_NUMBER = r"\d+(?:\.\d+)?|\.\d+"


def strip_fr_suffix(strength: str) -> str:
    """Remove the '**Federal Register determination ...**' annotation.

    2,408 Orange Book rows carry this marker inside the Strength field.
    """
    idx = strength.find(_FR_SUFFIX_MARKER)
    if idx != -1:
        return strength[:idx].rstrip()
    return strength.strip()


def _fmt(value: Decimal) -> str:
    """Exponent-free canonical rendering ('50', '0.1', never '5E+1')."""
    text = format(value.normalize(), "f")
    return text


def _to_decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def normalize_ndc_strength(numerator: str, unit: str) -> str:
    """Canonicalize an NDC Directory (numerator, unit) strength pair."""
    value = _to_decimal(numerator.strip())
    unit_norm = unit.strip().lower()
    if value is None:
        return _raw(f"{numerator} {unit}")

    # Per-day release rates (patches): mg/d, ug/d (mcg synonym tolerated).
    if unit_norm in {"mg/d", "mg/day", "mg/24hr"}:
        return f"UG24H:{_fmt(value * 1000)}"
    if unit_norm in {"ug/d", "ug/day", "mcg/d", "mcg/day", "ug/24hr", "mcg/24hr"}:
        return f"UG24H:{_fmt(value)}"

    # Mass per discrete unit: tablets ("1 mg/1"), sprays ("1.53 mg/1").
    if unit_norm in {"mg/1", "mg"}:
        return f"UG:{_fmt(value * 1000)}"
    if unit_norm in {"ug/1", "ug", "mcg/1", "mcg"}:
        return f"UG:{_fmt(value)}"

    # Concentration with carrier mass: gels (".25 mg/.25g", "1 mg/g").
    match = re.fullmatch(rf"mg/({_NUMBER})?g", unit_norm)
    if match is not None:
        grams = _to_decimal(match.group(1)) if match.group(1) else Decimal(1)
        if grams is not None and grams != 0:
            fraction_pct = value / (grams * 1000) * 100
            return f"PCT:{_fmt(fraction_pct)};G:{_fmt(grams)}"

    return _raw(f"{numerator} {unit}")


def normalize_ob_strength(strength: str) -> str:
    """Canonicalize an Orange Book Strength string."""
    text = strip_fr_suffix(strength).upper()
    # 'EQ 0.05MG BASE/24HR' style: measurement expressed as base equivalent.
    text = re.sub(r"^EQ\s+", "", text)
    text = text.replace(" BASE", "")
    text = text.strip()

    # Rate: 0.05MG/24HR, 14MCG/24HR
    match = re.fullmatch(rf"({_NUMBER})\s*(MG|MCG|UG)/24\s*HR", text)
    if match is not None:
        value = _to_decimal(match.group(1))
        if value is not None:
            if match.group(2) == "MG":
                value *= 1000
            return f"UG24H:{_fmt(value)}"

    # Concentration with per-packet/actuation mass: 0.1% (0.25GM/PACKET)
    match = re.fullmatch(
        rf"({_NUMBER})%\s*\(({_NUMBER})\s*GM?/(?:PACKET|ACTIVATION|POUCH)\)", text
    )
    if match is not None:
        pct = _to_decimal(match.group(1))
        grams = _to_decimal(match.group(2))
        if pct is not None and grams is not None:
            return f"PCT:{_fmt(pct)};G:{_fmt(grams)}"

    # Mass per discrete dose: 1.53MG/SPRAY, 0.5MG, 25MCG
    match = re.fullmatch(rf"({_NUMBER})\s*(MG|MCG|UG)(?:/SPRAY)?", text)
    if match is not None:
        value = _to_decimal(match.group(1))
        if value is not None:
            if match.group(2) == "MG":
                value *= 1000
            return f"UG:{_fmt(value)}"

    return _raw(text)


def _raw(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.strip().upper())
    return f"RAW:{normalized}"


def strengths_match(a: str | None, b: str | None) -> bool:
    """Whether two canonical strengths assert the same strength.

    Equality of canonical strings is the whole test. Unparsed spellings
    (RAW:) therefore match only on exact normalized text — conservative
    by construction, since two sources rarely spell an unparsed strength
    identically by accident.
    """
    if a is None or b is None:
        return False
    return a == b
