"""ndcres command-line interface.

Commands (built out across the implementation phases):

    ndcres normalize <ndc>          NDC spelling analysis and normalization
    ndcres refresh [--source ...]   fetch + ingest public datasets
    ndcres resolve <ndc>            ranked substitutable alternatives
    ndcres explain <ndc_a> <ndc_b>  why two NDCs are / are not equivalent
    ndcres signal <ndc>             supply-stress indicators
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import __version__
from .ndc import NdcError, ndc11_to_hipaa, parse_ndc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ndcres",
        description=(
            "NDC Equivalence Resolver — offline therapeutic-equivalence and "
            "supply-stress lookup over public FDA/NLM/CMS data. Informational "
            "only; never medical advice."
        ),
    )
    parser.add_argument("--version", action="version", version=f"ndcres {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    normalize = subparsers.add_parser(
        "normalize", help="parse an NDC and show its 11-digit normalization(s)"
    )
    normalize.add_argument("ndc", help="an NDC in any accepted spelling")

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


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "normalize":
        return cmd_normalize(args.ndc)
    raise AssertionError("unreachable: argparse enforces a known command")


if __name__ == "__main__":
    raise SystemExit(main())
