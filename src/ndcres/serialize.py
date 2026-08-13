"""Single home for JSON-shaped serialization of resolver output.

Both the CLI (--json) and the web API emit these exact structures — the
shape must never fork between surfaces.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from .explain import REASON_LANGUAGE, TIER_LANGUAGE, Explanation
from .provenance import ob_application_url
from .resolve import Annotated, Resolution
from .search import SearchHit
from .signals import ClassAssessment, SignalReport

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


def class_assessment_dict(assessment: ClassAssessment) -> dict[str, Any]:
    payload = dataclasses.asdict(assessment)
    # Serializers emit JSON-native types only: asdict preserves tuple
    # fields as tuples, which compare unequal to the lists a JSON
    # round-trip produces (caught by the CLI↔web parity test).
    payload["lines"] = list(payload["lines"])
    return payload


def resolution_dict(
    resolution: Resolution, *, sources: SourceRefs
) -> dict[str, Any]:
    return {
        "seed": annotated_dict(resolution.seed_annotation)
        if resolution.seed_annotation
        else None,
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
