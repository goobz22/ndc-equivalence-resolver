"""Single home for JSON-shaped serialization of resolver output.

Both the CLI (--json) and the web API emit these exact structures — the
shape must never fork between surfaces.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from .explain import REASON_LANGUAGE, TIER_LANGUAGE, Explanation
from .gaps import GapEntry, GapReport
from .provenance import ob_application_url
from .resolve import Annotated, Resolution
from .search import SearchHit
from .signals import VERDICT_CONSTRAINT, ClassAssessment, SignalReport
from .sweep import SweepClassRow, SweepResult

# The per-source refs map produced by provenance.source_refs(conn).
# Every payload carries one (SPEC §9) — CLI and web both pass it in, so
# the parity pin keeps the surfaces identical.
SourceRefs = dict[str, dict[str, Any]]

DISCLAIMER = (
    "ndcres surfaces supply-chain equivalence facts from public FDA/NLM/CMS "
    "data. It is not medical advice; substitution decisions belong to your "
    "pharmacist and prescriber."
)


def annotated_dict(annotated: Annotated) -> dict[str, Any]:
    dims = annotated.dims
    return {
        "ndc11": dims.ndc11,
        "ndc_as_filed": dims.package_ndc_filed,
        "name": dims.proprietary_name,
        "name_suffix": dims.proprietary_suffix,
        "labeler": dims.labeler_name,
        "application": dims.appl_display,
        "te_code": dims.te_code,
        "ob_heading": dims.ob_heading,
        "ob_type": dims.ob_type,
        "strength": dims.strength_norm,
        "schedule": dims.schedule,
        "schedule_confidence": dims.schedule_confidence,
        "schedule_conflict": dims.schedule_conflict,
        "pack_count": dims.pack_count,
        "pack_unit": dims.pack_unit,
        "marketed": dims.marketed,
        "tier": annotated.result.tier,
        "reasons": list(annotated.result.reasons),
        "reason_language": {
            reason: REASON_LANGUAGE.get(reason, reason)
            for reason in annotated.result.reasons
        },
        "nadac_per_unit": annotated.nadac_price,
        "nadac_effective_date": annotated.nadac_effective,
        "nadac_last_seen": annotated.nadac_as_of_last,
        "shortage_statuses": list(annotated.shortage_statuses),
        "stress_score": annotated.stress_score,
        "stress_evidence": list(annotated.stress_evidence),
        # Deep citation link: the Orange Book page for this application —
        # the primary source of the TE claim shown on the same card.
        "application_url": ob_application_url(dims.appl_display),
    }


def search_hit_dict(hit: SearchHit) -> dict[str, Any]:
    return {
        "ndc9": hit.ndc9,
        # The representative package — kept under the key "ndc11" so
        # result links resolve directly.
        "ndc11": hit.rep_ndc11,
        "ndc_as_filed": hit.ndc_as_filed,
        "name": hit.name,
        "name_suffix": hit.name_suffix,
        "generic_name": hit.generic_name,
        "labeler": hit.labeler,
        "dosage_form": hit.dosage_form,
        "form_family": hit.form_family,
        "strength": hit.strength,
        "te_code": hit.te_code,
        "marketed": hit.marketed,
        "package_count": hit.package_count,
    }


def search_results_dict(
    query: str, hits: tuple[SearchHit, ...], *, sources: SourceRefs
) -> dict[str, Any]:
    return {
        "query": query,
        "results": [search_hit_dict(hit) for hit in hits],
        "sources": sources,
        "disclaimer": DISCLAIMER,
    }


def gap_entry_dict(entry: GapEntry) -> dict[str, Any]:
    from .corroboration import corroborations_for

    payload = dataclasses.asdict(entry)
    payload["corroborated_by"] = [
        dataclasses.asdict(source)
        for source in corroborations_for(
            (
                entry.ingredient_set,
                entry.df_route,
                entry.strength_norm,
                entry.te_code,
            )
        )
    ]
    return payload


def gap_report_dict(
    report: GapReport, *, sources: SourceRefs, limit: int = 100
) -> dict[str, Any]:
    return {
        "sweep": {
            "sweep_id": report.sweep_id,
            "run_date": report.run_date,
            "nadac_horizon": report.nadac_horizon,
            "class_count": report.class_count,
            "counts": dict(report.counts),
        },
        "unlisted_constraints": [
            gap_entry_dict(e) for e in report.unlisted_constraints[:limit]
        ],
        "fda_listed": [gap_entry_dict(e) for e in report.fda_listed[:limit]],
        "listed_but_quiet": [
            gap_entry_dict(e) for e in report.listed_but_quiet[:limit]
        ],
        "totals": {
            "unlisted_constraints": len(report.unlisted_constraints),
            "fda_listed": len(report.fda_listed),
            "listed_but_quiet": len(report.listed_but_quiet),
        },
        "note": (
            "Verdicts are inferences from independent public datasets - "
            "evidence consistent with a constraint, never a confirmed "
            "shortage and never a statement of availability. The FDA list "
            "is manufacturer-self-reported and lagging; these lists measure "
            "the gap between it and the public evidence."
        ),
        "sources": sources,
        "disclaimer": DISCLAIMER,
    }


def sweep_class_row_dict(row: SweepClassRow) -> dict[str, Any]:
    return {
        "ingredient_set": row.ingredient_set,
        "df_route": row.df_route,
        "strength_norm": row.strength_norm,
        "te_code": row.te_code,
        "rep_ndc11": row.rep_ndc11,
        "member_count": row.member_count,
        "marketed_count": row.marketed_count,
        "assessment": class_assessment_dict(row.assessment),
    }


def sweep_summary_dict(
    result: SweepResult, *, sources: SourceRefs
) -> dict[str, Any]:
    top_constraints = sorted(
        (row for row in result.classes if row.assessment.verdict == VERDICT_CONSTRAINT),
        key=lambda row: (
            -row.assessment.fingerprints,
            -row.assessment.surveyed_count,
            -row.member_count,
            row.ingredient_set,
        ),
    )[:25]
    return {
        "run_date": result.run_date,
        "started_at": result.started_at,
        "nadac_horizon": result.nadac_horizon,
        "class_count": len(result.classes),
        "counts": dict(result.counts),
        "top_constraint_classes": [
            sweep_class_row_dict(row) for row in top_constraints
        ],
        "note": (
            "Verdicts are inferences from independent public datasets - "
            "evidence consistent with a constraint, never a confirmed "
            "shortage and never a statement of availability."
        ),
        "sources": sources,
        "disclaimer": DISCLAIMER,
    }


def class_assessment_dict(assessment: ClassAssessment) -> dict[str, Any]:
    payload = dataclasses.asdict(assessment)
    # Serializers emit JSON-native types only: asdict preserves tuple
    # fields as tuples, which compare unequal to the lists a JSON
    # round-trip produces (caught by the CLI↔web parity test).
    payload["lines"] = list(payload["lines"])
    return payload


def _class_ref(resolution: Resolution) -> dict[str, Any] | None:
    """The seed's canonical class address, when it has a TE-rated class."""
    from .classpage import class_slug

    seed = resolution.seed_annotation
    if seed is None or seed.dims.eq_group is None:
        return None
    ingredient_set, df_route, strength_norm, te_code = seed.dims.eq_group
    return {
        "slug": class_slug(ingredient_set, df_route, strength_norm, te_code),
        "ingredient_set": ingredient_set,
        "df_route": df_route,
        "strength_norm": strength_norm,
        "te_code": te_code,
    }


def resolution_dict(
    resolution: Resolution, *, sources: SourceRefs
) -> dict[str, Any]:
    return {
        "seed": annotated_dict(resolution.seed_annotation)
        if resolution.seed_annotation
        else None,
        "class_ref": _class_ref(resolution),
        "seed_status": resolution.seed_status,
        "notes": list(resolution.notes),
        "class_assessment": class_assessment_dict(resolution.class_assessment)
        if resolution.class_assessment
        else None,
        "tiers": {
            tier: [annotated_dict(a) for a in members]
            for tier, members in resolution.tiers.items()
        },
        "tier_language": TIER_LANGUAGE,
        "excluded": [annotated_dict(a) for a in resolution.excluded],
        "sources": sources,
        "disclaimer": DISCLAIMER,
    }


def explanation_dict(
    explanation: Explanation, *, sources: SourceRefs
) -> dict[str, Any]:
    return {
        "verdict": explanation.verdict.tier,
        "verdict_language": TIER_LANGUAGE[explanation.verdict.tier],
        "reasons": [
            {"code": reason, "language": REASON_LANGUAGE.get(reason, reason)}
            for reason in explanation.verdict.reasons
        ],
        "dimensions": [dataclasses.asdict(line) for line in explanation.lines],
        "left": {"ndc11": explanation.left.ndc11, "name": explanation.left.proprietary_name},
        "right": {"ndc11": explanation.right.ndc11, "name": explanation.right.proprietary_name},
        "sources": sources,
        "disclaimer": DISCLAIMER,
    }


def signal_dict(report: SignalReport, *, sources: SourceRefs) -> dict[str, Any]:
    return {
        "ndc11": report.ndc11,
        "stress_score": report.score,
        "survey_horizon": report.survey_horizon,
        "components": [dataclasses.asdict(c) for c in report.components],
        "note": (
            "The score is a documented heuristic over public signals. It "
            "infers supply stress; it never states availability."
        ),
        "sources": sources,
        "disclaimer": DISCLAIMER,
    }
