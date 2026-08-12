"""Application-schedule derivation.

Dosing schedule (twice-weekly vs once-weekly) is clinically load-bearing
for transdermal products but exists as no structured field in any FDA
dataset. It is derived here from independent evidence sources, ranked by
confidence, with every finding recorded so the resolver can cite its
reasoning and flag conflicts. Verified evidence sources:

1. ``rxnorm-scd``  RxNorm concept names lead with the wear duration:
                   "84 HR estradiol ... Transdermal System" (84 h = 3.5 d
                   = twice-weekly), "168 HR ..." = once-weekly.
2. ``pack-wear``   Package descriptions sometimes carry "3.5 d in 1
                   PATCH" / "7 d in 1 PATCH".
3. ``nadac-desc``  NADAC descriptions encode "(2/WK)" / "(1/WK)".
4. ``brand-map``   Explicit name markers ("(Twice-Weekly)") and a curated
                   brand table (see label citations inline).
5. ``pack-count``  8-count cartons are twice-weekly, 4-count once-weekly
                   — a convention of the estradiol transdermal family
                   only, hence the ``patch`` form-family scope guard.

Within a TE equivalence group the resolver additionally inherits the
group's schedule (``te-group-inherited``) — same heading + strength + TE
code implies the same product design; that logic lives in resolve, not
here, because it requires group context.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

TWICE_WEEKLY = "2/wk"
ONCE_WEEKLY = "1/wk"

_RUNG_ORDER = ("rxnorm-scd", "pack-wear", "nadac-desc", "brand-map", "pack-count")

# Curated brand → schedule map. Sources: DailyMed labels, checked 2026-08-12:
#   Vivelle-Dot / Minivelle / Lyllana / Dotti — "twice weekly (every 3 to 4 days)"
#   Alora / Vivelle / Esclim / Estraderm — historical twice-weekly patches (DISCN)
#   Climara — "applied once weekly"; Menostar — once-weekly; FemPatch — once-weekly (DISCN)
_BRAND_SCHEDULE: dict[str, str] = {
    "VIVELLE-DOT": TWICE_WEEKLY,
    "VIVELLE": TWICE_WEEKLY,
    "MINIVELLE": TWICE_WEEKLY,
    "LYLLANA": TWICE_WEEKLY,
    "DOTTI": TWICE_WEEKLY,
    "ALORA": TWICE_WEEKLY,
    "ESCLIM": TWICE_WEEKLY,
    "ESTRADERM": TWICE_WEEKLY,
    "CLIMARA": ONCE_WEEKLY,
    "MENOSTAR": ONCE_WEEKLY,
    "FEMPATCH": ONCE_WEEKLY,
}

_SCD_HOURS = re.compile(r"^(\d+(?:\.\d+)?)\s*HR\b")

_HOURS_TO_SCHEDULE = {84.0: TWICE_WEEKLY, 168.0: ONCE_WEEKLY}


@dataclass(frozen=True)
class ScheduleEvidence:
    rung: str
    value: str
    detail: str


@dataclass(frozen=True)
class ScheduleResult:
    value: str | None
    confidence: str | None  # the rung that decided the value
    conflict: bool
    evidence: tuple[ScheduleEvidence, ...]


def derive_schedule(
    *,
    rx_scd_name: str | None = None,
    wear_hours: float | None = None,
    nadac_descriptions: Sequence[str] = (),
    proprietary_name: str | None = None,
    proprietary_suffix: str | None = None,
    pack_count: int | None = None,
    form_family: str | None = None,
) -> ScheduleResult:
    """Derive the application schedule from all available evidence."""
    findings: list[ScheduleEvidence] = []

    if rx_scd_name:
        match = _SCD_HOURS.match(rx_scd_name.strip())
        if match is not None:
            hours = float(match.group(1))
            value = _HOURS_TO_SCHEDULE.get(hours)
            if value is not None:
                findings.append(
                    ScheduleEvidence(
                        rung="rxnorm-scd",
                        value=value,
                        detail=f"RxNorm concept name leads with {match.group(1)} HR: {rx_scd_name!r}",
                    )
                )

    if wear_hours is not None:
        value_or_none = _HOURS_TO_SCHEDULE.get(wear_hours)
        if value_or_none is not None:
            findings.append(
                ScheduleEvidence(
                    rung="pack-wear",
                    value=value_or_none,
                    detail=f"package description declares a {wear_hours:g}-hour wear duration",
                )
            )

    for description in nadac_descriptions:
        upper = description.upper()
        if "(2/WK)" in upper:
            findings.append(
                ScheduleEvidence(
                    rung="nadac-desc",
                    value=TWICE_WEEKLY,
                    detail=f"NADAC description {description!r} carries (2/WK)",
                )
            )
            break
        if "(1/WK)" in upper:
            findings.append(
                ScheduleEvidence(
                    rung="nadac-desc",
                    value=ONCE_WEEKLY,
                    detail=f"NADAC description {description!r} carries (1/WK)",
                )
            )
            break

    brand_evidence = _brand_evidence(proprietary_name, proprietary_suffix)
    if brand_evidence is not None:
        findings.append(brand_evidence)

    if form_family == "patch" and pack_count in (4, 8):
        value = TWICE_WEEKLY if pack_count == 8 else ONCE_WEEKLY
        findings.append(
            ScheduleEvidence(
                rung="pack-count",
                value=value,
                detail=f"{pack_count}-count carton heuristic (estradiol transdermal convention)",
            )
        )

    if not findings:
        return ScheduleResult(value=None, confidence=None, conflict=False, evidence=())

    findings.sort(key=lambda e: _RUNG_ORDER.index(e.rung))
    chosen = findings[0]
    conflict = any(e.value != chosen.value for e in findings)
    return ScheduleResult(
        value=chosen.value,
        confidence=chosen.rung,
        conflict=conflict,
        evidence=tuple(findings),
    )


def _brand_evidence(
    proprietary_name: str | None, proprietary_suffix: str | None
) -> ScheduleEvidence | None:
    combined = " ".join(
        part for part in (proprietary_name, proprietary_suffix) if part
    ).upper()
    if not combined:
        return None

    if re.search(r"\bTWICE[- ]WEEKLY\b", combined):
        return ScheduleEvidence(
            rung="brand-map",
            value=TWICE_WEEKLY,
            detail=f"name marker 'Twice-Weekly' in {combined!r}",
        )
    if re.search(r"\bONCE[- ]WEEKLY\b", combined):
        return ScheduleEvidence(
            rung="brand-map",
            value=ONCE_WEEKLY,
            detail=f"name marker 'Once-Weekly' in {combined!r}",
        )

    for brand, value in _BRAND_SCHEDULE.items():
        if re.search(rf"\b{re.escape(brand)}\b", combined):
            return ScheduleEvidence(
                rung="brand-map",
                value=value,
                detail=f"curated brand map: {brand} is {value} (DailyMed label)",
            )
    return None
