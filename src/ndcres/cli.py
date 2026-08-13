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
import json
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .db import connect
from .explain import REASON_LANGUAGE, TIER_LANGUAGE, Explanation
from .ndc import NdcError, ndc11_to_hipaa, parse_ndc
from .resolve import Annotated, Resolution, ResolveError
from .serialize import (
    DISCLAIMER as _DISCLAIMER,
    explanation_dict,
    resolution_dict,
    signal_dict,
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
        choices=[
            "all", "ndc", "orangebook", "rxnorm", "nadac", "shortage",
            "sdud", "enforcement",
        ],
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

    signal_cmd = subparsers.add_parser(
        "signal", help="supply-stress indicators for one NDC"
    )
    signal_cmd.add_argument("ndc")
    signal_cmd.add_argument("--json", action="store_true", dest="as_json")

    sweep_cmd = subparsers.add_parser(
        "sweep",
        help="assess EVERY equivalence class and append the results "
        "(the market-wide supply picture)",
    )
    sweep_cmd.add_argument("--json", action="store_true", dest="as_json")

    search_cmd = subparsers.add_parser(
        "search", help="find products by name, strength, form, or NDC fragment"
    )
    search_cmd.add_argument(
        "query", nargs="+", help='e.g. "estradiol .05" or "dotti" or 0378-4642'
    )
    search_cmd.add_argument("--limit", type=int, default=25)
    search_cmd.add_argument("--json", action="store_true", dest="as_json")

    export_cmd = subparsers.add_parser(
        "export", help="produce a trimmed read-only database for web serving"
    )
    export_cmd.add_argument(
        "--web", action="store_true", required=True, help="web-serving export"
    )
    export_cmd.add_argument("--out", type=Path, required=True)

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
        bits.append("not on FDA shortage list")
    print(f"{indent}{filed}  {name} - {dims.labeler_name or '?'}")
    print(f"{indent}   {' | '.join(bits)}")
    if annotated.stress_score:
        print(
            f"{indent}   supply-stress {annotated.stress_score:.2f} "
            "(heuristic, not availability)"
        )
        for evidence in annotated.stress_evidence:
            print(f"{indent}     - {evidence}")
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
        f"{seed_name} - {seed.labeler_name or '?'}"
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
            else "not on FDA shortage list"
        )
        print(f"      TE {te} | {schedule} | {nadac} | {shortage}")
        if seed_annotation.stress_score:
            print(
                f"      SUPPLY-STRESS {seed_annotation.stress_score:.2f} "
                "(heuristic, not availability)"
            )
            for evidence in seed_annotation.stress_evidence:
                print(f"        - {evidence}")
    for note in resolution.notes:
        print(f"      note: {note}")

    assessment = resolution.class_assessment
    if assessment is not None:
        print()
        print(f"SUPPLY PICTURE for this drug's equivalence class ({assessment.member_count} products):")
        print(f"  >> {assessment.verdict_language}")
        for line in assessment.lines:
            print(f"     - {line}")
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
        from .provenance import source_refs

        print(
            json.dumps(
                resolution_dict(resolution, sources=source_refs(conn)), indent=2
            )
        )
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
        marker = {True: "=", False: "x", None: "?"}[line.same]
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
        from .provenance import source_refs

        print(
            json.dumps(
                explanation_dict(explanation, sources=source_refs(conn)), indent=2
            )
        )
    else:
        _print_explanation(explanation)
    return 0


def cmd_signal(db_path: Path | None, ndc_text: str, as_json: bool) -> int:
    from .resolve import resolve_input_ndc11
    from .signals import signal_report

    conn = connect(db_path)
    try:
        ndc11 = resolve_input_ndc11(conn, ndc_text)
    except (NdcError, ResolveError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    report = signal_report(conn, ndc11)
    if as_json:
        from .provenance import source_refs

        print(json.dumps(signal_dict(report, sources=source_refs(conn)), indent=2))
        return 0
    print(f"Supply-stress signals for {ndc11} ({ndc11_to_hipaa(ndc11)})")
    if report.survey_horizon:
        print(f"  NADAC survey horizon: {report.survey_horizon}")
    for component in report.components:
        flag = "FIRING" if component.fired else "quiet"
        print(f"  [{flag:>6}] {component.name} (+{component.contribution:.3f})")
        print(f"           {component.evidence}")
    print(f"  score: {report.score:.2f} of 1.00 (heuristic, not availability)")
    print()
    print(_DISCLAIMER)
    return 0


def cmd_sweep(db_path: Path | None, as_json: bool) -> int:
    from .provenance import source_refs
    from .serialize import sweep_summary_dict
    from .signals import VERDICT_CONSTRAINT
    from .sweep import persist_sweep, run_sweep

    conn = connect(db_path)
    result = run_sweep(conn)
    sweep_id = persist_sweep(conn, result)
    if as_json:
        payload = sweep_summary_dict(result, sources=source_refs(conn))
        payload["sweep_id"] = sweep_id
        print(json.dumps(payload, indent=2))
        return 0
    print(
        f"sweep #{sweep_id}: {len(result.classes)} equivalence classes "
        f"assessed in {result.elapsed_seconds:.1f}s "
        f"(NADAC horizon {result.nadac_horizon or 'n/a'})"
    )
    for verdict, count in sorted(result.counts.items()):
        print(f"  {count:>5}  {verdict}")
    constraints = sorted(
        (r for r in result.classes if r.assessment.verdict == VERDICT_CONSTRAINT),
        key=lambda r: (
            -r.assessment.fingerprints,
            -r.assessment.surveyed_count,
            -r.member_count,
            r.ingredient_set,
        ),
    )
    if constraints:
        print()
        print(
            "top unlisted constraint classes (independent evidence, no FDA "
            "listing):"
        )
        for row in constraints[:20]:
            strength = row.strength_norm or "?"
            print(
                f"  {row.assessment.fingerprints} fingerprints | "
                f"{row.ingredient_set} | {row.df_route} | {strength} | "
                f"TE {row.te_code} | {row.member_count} members | "
                f"rep {row.rep_ndc11}"
            )
    print()
    print(_DISCLAIMER)
    return 0


def cmd_search(
    db_path: Path | None, query_words: list[str], limit: int, as_json: bool
) -> int:
    from .search import search
    from .serialize import search_results_dict

    query = " ".join(query_words)
    conn = connect(db_path)
    hits = search(conn, query, limit=limit)
    if as_json:
        from .provenance import source_refs

        print(
            json.dumps(
                search_results_dict(query, hits, sources=source_refs(conn)),
                indent=2,
            )
        )
        return 0
    if not hits:
        print(f'no products match "{query}"')
        return 0
    print(f'{len(hits)} product(s) matching "{query}":')
    for hit in hits:
        display_name = " ".join(
            part for part in (hit.name, hit.name_suffix) if part
        ) or (hit.generic_name or "(unnamed)")
        status = "marketed" if hit.marketed else "not marketed"
        te_badge = f" TE:{hit.te_code}" if hit.te_code else ""
        strength = f" {hit.strength}" if hit.strength else ""
        # ASCII-only console output (Windows cp1252 renders anything else
        # as '?', per the repo-wide rule the other _print helpers follow).
        print(
            f"  {hit.ndc_as_filed:<14} {display_name}{strength}"
            f" - {hit.generic_name or '?'} | {hit.labeler or '?'}"
            f" | {hit.package_count} pkg | {status}{te_badge}"
        )
    print()
    print(_DISCLAIMER)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    # Windows consoles often run cp1252; upstream data carries characters
    # outside it (smart quotes in labeler names). Never crash over glyphs.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    if args.command == "normalize":
        return cmd_normalize(args.ndc)
    if args.command == "refresh":
        return cmd_refresh(args.db, args.source, args.from_dir, args.data_dir)
    if args.command == "resolve":
        return cmd_resolve(args.db, args.ndc, args.as_json)
    if args.command == "explain":
        return cmd_explain(args.db, args.ndc_a, args.ndc_b, args.as_json)
    if args.command == "signal":
        return cmd_signal(args.db, args.ndc, args.as_json)
    if args.command == "sweep":
        return cmd_sweep(args.db, args.as_json)
    if args.command == "search":
        return cmd_search(args.db, args.query, args.limit, args.as_json)
    if args.command == "export":
        from .db import default_db_path
        from .export import export_web_db

        source = args.db if args.db is not None else default_db_path()
        try:
            size = export_web_db(source, args.out)
        except RuntimeError as error:
            print(f"export failed: {error}", file=sys.stderr)
            return 1
        print(f"wrote {args.out} ({size / 1e6:.1f}MB)")
        return 0
    raise AssertionError("unreachable: argparse enforces a known command")


if __name__ == "__main__":
    raise SystemExit(main())
