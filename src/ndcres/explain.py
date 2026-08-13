"""Human-readable equivalence rationale between two NDCs.

Every line cites where its fact came from. The verdict quotes the Orange
Book preface rule when TE codes decide the outcome, because that rule -
"therapeutically equivalent only to other drugs coded with the same
three-character code under that heading" - is the load-bearing fact of
the whole tool.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .resolve import (
    Dims,
    ResolveError,
    TierResult,
    assign_tier,
    compute_dimensions,
    resolve_input_ndc11,
)

_PREFACE_RULE = (
    'Orange Book preface: "Drugs coded with a three-character code under a '
    "heading are considered therapeutically equivalent only to other drugs "
    'coded with the same three-character code under that heading."'
)

TIER_LANGUAGE = {
    "T1": (
        "DIRECT SUBSTITUTE - same therapeutic-equivalence subgroup, strength, "
        "and package size. A pharmacist can usually substitute this without "
        "contacting the prescriber (state rules vary)."
    ),
    "T2": (
        "SAME DRUG, DIFFERENT PACKAGE - therapeutically equivalent, but the "
        "prescription quantity must be adjusted. Ask the prescriber or "
        "pharmacist to adjust the quantity on the script."
    ),
    "T3": (
        "REQUIRES PRESCRIBER AUTHORIZATION - same medicine family, but NOT "
        "an automatic substitute. A prescriber must write a new or amended "
        "prescription naming this product."
    ),
    "T4": (
        "DIFFERENT DELIVERY FORM - same molecule by a different route or "
        "form. Informational only: switching is a clinical decision for the "
        "prescriber."
    ),
    "EXCLUDED": "NOT A CURRENT OPTION - see the reason noted.",
}

REASON_LANGUAGE = {
    "different-te-subgroup": (
        "The two products carry DIFFERENT therapeutic-equivalence codes, so "
        "the FDA has not rated them interchangeable. " + _PREFACE_RULE
    ),
    "different-schedule": (
        "The application schedules differ (e.g. twice-weekly vs once-weekly) "
        "- dosing and monthly quantity change."
    ),
    "different-strength": "The strengths differ - dose conversion required.",
    "no-te-code": (
        "The candidate has no therapeutic-equivalence rating in the Orange "
        "Book (single-source, unrated, or discontinued)."
    ),
    "not-in-orange-book": (
        "The candidate's application is not in the Orange Book (OTC "
        "monograph, unapproved, or biologic) - no TE evaluation exists."
    ),
    "seed-no-te-rating": (
        "The product you asked about has no therapeutic-equivalence rating, "
        "so nothing can be an automatic substitute for it."
    ),
    "schedule-unknown": (
        "The application schedule could not be derived for one side - "
        "treated as not substitutable rather than guessed."
    ),
    "pack-count-unknown": "The package count could not be parsed for one side.",
    "status-conflict": (
        "Marketing status conflicts between the NDC Directory and the "
        "Orange Book (refresh lag) - verify before relying on it."
    ),
    "discontinued-ob": "Discontinued per the Orange Book (Type DISCN).",
    "not-in-current-ndc-directory": (
        "Not listed in the current FDA NDC Directory - not currently "
        "marketed under this NDC."
    ),
    "sample-package": "A manufacturer sample package - not dispensed retail.",
    "different-form-family": "Different delivery form family.",
}


@dataclass(frozen=True)
class DimensionLine:
    dimension: str
    left: str
    right: str
    same: bool | None
    source: str


@dataclass(frozen=True)
class Explanation:
    left: Dims
    right: Dims
    verdict: TierResult
    lines: tuple[DimensionLine, ...]


def explain(conn: sqlite3.Connection, text_a: str, text_b: str) -> Explanation:
    dims_a = _dims_for(conn, text_a)
    dims_b = _dims_for(conn, text_b)
    verdict = assign_tier(dims_a, dims_b)

    lines = (
        DimensionLine(
            "active ingredient(s)",
            dims_a.ingredient_set or "?",
            dims_b.ingredient_set or "?",
            _same(dims_a.ingredient_set, dims_b.ingredient_set),
            "FDA NDC Directory, SUBSTANCENAME",
        ),
        DimensionLine(
            "delivery form family",
            dims_a.form_family or "?",
            dims_b.form_family or "?",
            _same(dims_a.form_family, dims_b.form_family),
            "curated map over NDC Directory dosage form + route",
        ),
        DimensionLine(
            "strength",
            dims_a.strength_norm or "?",
            dims_b.strength_norm or "?",
            _same(dims_a.strength_norm, dims_b.strength_norm),
            "NDC Directory strength, canonicalized (matches Orange Book spelling)",
        ),
        DimensionLine(
            "TE code (Orange Book)",
            _te_display(dims_a),
            _te_display(dims_b),
            (
                None
                if dims_a.eq_group is None or dims_b.eq_group is None
                else dims_a.eq_group == dims_b.eq_group
            ),
            "Orange Book products.txt via application-number join"
            + (
                " (Menostar application special-cased - NDC Directory files "
                "it under the wrong NDA)"
                if "special-case" in {dims_a.link_method, dims_b.link_method}
                else ""
            ),
        ),
        DimensionLine(
            "application schedule",
            _schedule_display(dims_a),
            _schedule_display(dims_b),
            (
                None
                if dims_a.schedule is None or dims_b.schedule is None
                else dims_a.schedule == dims_b.schedule
            ),
            "derived: RxNorm concept name / package wear duration / NADAC "
            "description / brand map",
        ),
        DimensionLine(
            "package size",
            _pack_display(dims_a),
            _pack_display(dims_b),
            (
                None
                if dims_a.pack_count is None or dims_b.pack_count is None
                else dims_a.pack_count == dims_b.pack_count
            ),
            "NDC Directory package description, parsed",
        ),
    )
    return Explanation(left=dims_a, right=dims_b, verdict=verdict, lines=lines)


def _dims_for(conn: sqlite3.Connection, text: str) -> Dims:
    ndc11 = resolve_input_ndc11(conn, text)
    package = conn.execute(
        "SELECT ndc9 FROM package WHERE ndc11 = ?", (ndc11,)
    ).fetchone()
    if package is not None:
        dims = compute_dimensions(conn, package["ndc9"], ndc11)
        if dims is not None:
            return dims
    dims = compute_dimensions(conn, ndc11[:9], None)
    if dims is not None:
        return dims
    raise ResolveError(f"NDC {ndc11} is unknown to this database")


def _same(a: object, b: object) -> bool | None:
    if a is None or b is None:
        return None
    return a == b


def _te_display(dims: Dims) -> str:
    if dims.te_code is None:
        return f"none ({dims.link_status or 'unlinked'})"
    heading = dims.ob_heading or "?"
    return f"{dims.te_code} under [{dims.ingredient_set}; {heading}] via {dims.appl_display}"


def _schedule_display(dims: Dims) -> str:
    if dims.schedule is None:
        return "unknown"
    conflict = ", CONFLICTING EVIDENCE" if dims.schedule_conflict else ""
    return f"{dims.schedule} (via {dims.schedule_confidence}{conflict})"


def _pack_display(dims: Dims) -> str:
    if dims.pack_count is None:
        return "?" if dims.ndc11 else "n/a (product-level query)"
    unit = (dims.pack_unit or "unit").lower()
    return f"{dims.pack_count} x {unit}"
