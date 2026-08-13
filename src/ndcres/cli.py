"""ndcres command-line interface.

    ndcres normalize <ndc>            NDC spelling analysis
    ndcres refresh [--source ...]     fetch + ingest public datasets
    ndcres resolve <ndc> [--json]     ranked substitutable alternatives
    ndcres explain <ndc_a> <ndc_b>    why two NDCs are / are not equivalent
    ndcres signal <ndc>               supply-stress indicators (P3b)

Informational only — never medical advice. Tier 2+ results always carry
prescriber-authorization language.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .db import connect
from .explain import REASON_LANGUAGE, TIER_LANGUAGE, Explanation
from .ndc import NdcError, ndc11_to_hipaa, parse_ndc
from .resolve import Annotated, Resolution, ResolveError

_DISCLAIMER = (
    "ndcres surfaces supply-chain equivalence facts from public FDA/NLM/CMS "
    "data. It is not medical advice; substitution decisions belong to your "
    "pharmacist and prescriber."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ndcres",
        description=(
            "NDC Equivalence Resolver — offline therapeutic-equivalence and "
            "supply-stress lookup over public FDA/NLM/CMS data. "
            + _DISCLAIMER
        ),
    )
    parser.add_argument("--version", action="version", version=f"ndcres {__version__}")
    parser.add_argument(
        "--db", type=Path, default=None, help="database path (default ~/.ndcres/ndcres.db)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser(
        "normalize", help="parse an NDC and show its 11-digit normalization(s)"
    )
    normalize.add_argument("ndc", help="an NDC in any accepted spelling")

    refresh = subparsers.add_parser(
        "refresh", help="fetch and ingest the public datasets"
    )
    refresh.add_argument(
        "--source",
        action="append",
        choices=["all", "ndc", "orangebook", "rxnorm", "nadac", "shortage"],
        help="source(s) to refresh (default: all)",
    )
    refresh.add_argument(
        "--from-dir",
        type=Path,
        default=None,
        help="ingest pre-downloaded files from this directory instead of fetching",
    )
    refresh.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="where downloads land (default ~/.ndcres/raw)",
    )

    resolve_cmd = subparsers.add_parser(
        "resolve", help="ranked substitutable alternatives for an NDC"
    )
    resolve_cmd.add_argument("ndc", help="an NDC in any accepted spelling")
    resolve_cmd.add_argument("--json", action="store_true", dest="as_json")

    explain_cmd = subparsers.add_parser(
        "explain", help="why two NDCs are (or are not) equivalent"
    )
    explain_cmd.add_argument("ndc_a")
    explain_cmd.add_argument("ndc_b")
    explain_cmd.add_argument("--json", action="store_true", dest="as_json")

    return parser


def cmd_normalize(ndc_text: str) -> int:
    try:
        query = parse_ndc(ndc_text)
    except NdcError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if query.ambiguous:
        print(f"{query.raw} is ambiguous without hyphens; possible normalizations:")
        for candidate in query.candidates:
            print(f"  {candidate}  ({ndc11_to_hipaa(candidate)})")
        return 1
    ndc11 = query.ndc11
    shape = f" (as-filed shape {query.shape})" if query.shape else ""
    print(f"{query.raw}{shape} -> {ndc11}  ({ndc11_to_hipaa(ndc11)})")
    return 0


def cmd_refresh(
    db_path: Path | None,
    source_args: list[str] | None,
    from_dir: Path | None,
    data_dir: Path | None,
) -> int:
    from .ingest import SOURCES, refresh

    wanted: tuple[str, ...] | None = None
    if source_args and "all" not in source_args:
        wanted = tuple(dict.fromkeys(source_args))
    conn = connect(db_path)
    try:
        counts = refresh(conn, sources=wanted, from_dir=from_dir, data_dir=data_dir)
    except Exception as error:  # surface, don't stack-trace, for CLI use
        print(f"refresh failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    for source in (*SOURCES, "link"):
        if source in counts:
            print(f"  {source:<11} {counts[source]:>9,} rows")
    return 0


def _annotated_dict(annotated: Annotated) -> dict[str, Any]:
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
        "nadac_per_unit": annotated.nadac_price,
        "nadac_effective_date": annotated.nadac_effective,
        "nadac_last_seen": annotated.nadac_as_of_last,
        "shortage_statuses": list(annotated.shortage_statuses),
        "stress_score": annotated.stress_score,
    }


def _print_annotated(annotated: Annotated, indent: str = "    ") -> None:
    dims = annotated.dims
    name = dims.proprietary_name or "(unnamed)"
    if dims.proprietary_suffix:
        name += f" {dims.proprietary_suffix}"
    filed = dims.package_ndc_filed or (dims.ndc11 or dims.ndc9)
    bits: list[str] = []
    if dims.te_code:
        bits.append(f"TE {dims.te_code}")
    if dims.pack_count:
        bits.append(f"{dims.pack_count}-count")
    if dims.schedule:
        bits.append(dims.schedule)
    if annotated.nadac_price is not None:
        bits.append(
            f"NADAC ${annotated.nadac_price:.2f}/unit "
            f"(eff {annotated.nadac_effective}, seen {annotated.nadac_as_of_last})"
        )
    else:
        bits.append("no NADAC record")
    if annotated.shortage_statuses:
        bits.append(f"shortage: {', '.join(annotated.shortage_statuses)}")
    else:
        bits.append("no known shortage record")
    print(f"{indent}{filed}  {name} — {dims.labeler_name or '?'}")
    print(f"{indent}   {' · '.join(bits)}")
    if annotated.result.reasons:
        for reason in annotated.result.reasons:
            language = REASON_LANGUAGE.get(reason, reason)
            print(f"{indent}   [{reason}] {language}")


_TIER_HEADINGS = {
    "T1": "TIER 1 — direct substitutes (pharmacist-level swap in most states)",
    "T2": "TIER 2 — same drug, different package (quantity change on the script)",
    "T3": "TIER 3 — requires prescriber authorization",
    "T4": "TIER 4 — different delivery form (informational; clinical decision)",
}


def _print_resolution(resolution: Resolution) -> None:
    seed = resolution.seed
    seed_name = seed.proprietary_name or "(unnamed)"
    if seed.proprietary_suffix:
        seed_name += f" {seed.proprietary_suffix}"
    print(
        f"Seed: {seed.package_ndc_filed or seed.ndc11 or seed.ndc9}  "
        f"{seed_name} — {seed.labeler_name or '?'}"
    )
    if resolution.seed_annotation is not None:
        seed_annotation = resolution.seed_annotation
        te = seed.te_code or "no TE rating"
        schedule = seed.schedule or "unknown schedule"
        nadac = (
            f"NADAC ${seed_annotation.nadac_price:.2f}/unit "
            f"(seen {seed_annotation.nadac_as_of_last})"
            if seed_annotation.nadac_price is not None
            else "no NADAC record"
        )
        shortage = (
            f"shortage: {', '.join(seed_annotation.shortage_statuses)}"
            if seed_annotation.shortage_statuses
            else "no known shortage record"
        )
        print(f"      TE {te} · {schedule} · {nadac} · {shortage}")
    for note in resolution.notes:
        print(f"      note: {note}")
    print()

    for tier in ("T1", "T2", "T3", "T4"):
        members = resolution.tiers.get(tier, [])
        if not members:
            continue
        print(_TIER_HEADINGS[tier])
        if tier == "T3":
            print(
                "    These need a NEW or AMENDED prescription naming the "
                "product — ask the prescriber."
            )
        for annotated in members:
            _print_annotated(annotated)
        print()

    if resolution.excluded:
        print("Excluded (not current options):")
        for annotated in resolution.excluded:
            _print_annotated(annotated)
        print()
    print(_DISCLAIMER)


def cmd_resolve(db_path: Path | None, ndc_text: str, as_json: bool) -> int:
    from .resolve import resolve as run_resolve

    conn = connect(db_path)
    try:
        resolution = run_resolve(conn, ndc_text)
    except (NdcError, ResolveError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if as_json:
        payload = {
            "seed": _annotated_dict(resolution.seed_annotation)
            if resolution.seed_annotation
            else None,
            "seed_status": resolution.seed_status,
            "notes": list(resolution.notes),
            "tiers": {
                tier: [_annotated_dict(a) for a in members]
                for tier, members in resolution.tiers.items()
            },
            "excluded": [_annotated_dict(a) for a in resolution.excluded],
            "disclaimer": _DISCLAIMER,
        }
        print(json.dumps(payload, indent=2))
    else:
        _print_resolution(resolution)
    return 0


def _print_explanation(explanation: Explanation) -> None:
    left = explanation.left
    right = explanation.right
    print(
        f"Comparing {left.package_ndc_filed or left.ndc11 or left.ndc9} "
        f"({left.proprietary_name or '?'}) with "
        f"{right.package_ndc_filed or right.ndc11 or right.ndc9} "
        f"({right.proprietary_name or '?'})\n"
    )
    for line in explanation.lines:
        marker = {True: "=", False: "≠", None: "?"}[line.same]
        print(f"  [{marker}] {line.dimension}")
        print(f"      A: {line.left}")
        print(f"      B: {line.right}")
        print(f"      source: {line.source}")
    print()
    print(f"VERDICT: {TIER_LANGUAGE[explanation.verdict.tier]}")
    for reason in explanation.verdict.reasons:
        print(f"  [{reason}] {REASON_LANGUAGE.get(reason, reason)}")
    print()
    print(_DISCLAIMER)


def cmd_explain(db_path: Path | None, ndc_a: str, ndc_b: str, as_json: bool) -> int:
    from .explain import explain

    conn = connect(db_path)
    try:
        explanation = explain(conn, ndc_a, ndc_b)
    except (NdcError, ResolveError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if as_json:
        payload = {
            "verdict": explanation.verdict.tier,
            "verdict_language": TIER_LANGUAGE[explanation.verdict.tier],
            "reasons": [
                {"code": reason, "language": REASON_LANGUAGE.get(reason, reason)}
                for reason in explanation.verdict.reasons
            ],
            "dimensions": [dataclasses.asdict(line) for line in explanation.lines],
            "disclaimer": _DISCLAIMER,
        }
        print(json.dumps(payload, indent=2))
    else:
        _print_explanation(explanation)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "normalize":
        return cmd_normalize(args.ndc)
    if args.command == "refresh":
        return cmd_refresh(args.db, args.source, args.from_dir, args.data_dir)
    if args.command == "resolve":
        return cmd_resolve(args.db, args.ndc, args.as_json)
    if args.command == "explain":
        return cmd_explain(args.db, args.ndc_a, args.ndc_b, args.as_json)
    raise AssertionError("unreachable: argparse enforces a known command")


if __name__ == "__main__":
    raise SystemExit(main())
