"""Provenance layer (SPEC §9): every payload names its sources.

The walk test is the enforcement for the operator's rule — "wherever we
give data, give a source URL back to where the data was gotten from" —
and for INV-18.3 (the disclaimer accompanies every payload).
"""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from ndcres.explain import explain
from ndcres.ingest import SOURCES
from ndcres.provenance import (
    SOURCE_REGISTRY,
    ob_application_url,
    rxnav_url,
    source_refs,
)
from ndcres.resolve import resolve
from ndcres.search import search
from ndcres.serialize import (
    explanation_dict,
    resolution_dict,
    search_results_dict,
    signal_dict,
)
from ndcres.signals import signal_report

ANCHOR = "0378-4642-26"


def _walk_payload(payload: dict[str, Any]) -> list[str]:
    """Return the provenance defects in one payload (empty = clean)."""
    problems: list[str] = []
    sources = payload.get("sources")
    if not isinstance(sources, dict) or not sources:
        problems.append("payload has no sources map")
        return problems
    for key in SOURCES:
        ref = sources.get(key)
        if ref is None:
            problems.append(f"source {key!r} missing from the map")
            continue
        for field in ("name", "publisher", "url", "license"):
            if not ref.get(field):
                problems.append(f"source {key!r} lacks {field!r}")
        if not ref.get("fetched_at"):
            problems.append(f"source {key!r} lacks fetched_at (never ingested?)")
    if not payload.get("disclaimer"):
        problems.append("payload has no disclaimer")
    return problems


class TestRegistry:
    def test_every_ingest_source_has_identity(self) -> None:
        assert set(SOURCES) <= set(SOURCE_REGISTRY)

    def test_derived_tables_have_identity_too(self) -> None:
        assert "link" in SOURCE_REGISTRY and "search" in SOURCE_REGISTRY

    def test_refs_merge_live_run_state(self, loaded_conn: sqlite3.Connection) -> None:
        refs = source_refs(loaded_conn)
        for key in SOURCES:
            assert refs[key]["fetched_at"], key
            assert refs[key]["url"].startswith("https://"), key


class TestDeepLinks:
    def test_anda_deep_link(self) -> None:
        url = ob_application_url("ANDA201675")
        assert url == (
            "https://www.accessdata.fda.gov/scripts/cder/ob/results_product.cfm"
            "?Appl_Type=A&Appl_No=201675"
        )

    def test_nda_deep_link_pads_to_six(self) -> None:
        url = ob_application_url("NDA20538")
        assert url is not None and url.endswith("Appl_Type=N&Appl_No=020538")

    def test_garbage_and_none_yield_none(self) -> None:
        assert ob_application_url(None) is None
        assert ob_application_url("OTC monograph") is None
        assert rxnav_url(None) is None

    def test_rxnav_link(self) -> None:
        assert rxnav_url("205756") == (
            "https://mor.nlm.nih.gov/RxNav/search?searchBy=RXCUI&searchTerm=205756"
        )


class TestEveryPayloadCarriesProvenance:
    def test_resolution_payload(self, loaded_conn: sqlite3.Connection) -> None:
        payload = resolution_dict(
            resolve(loaded_conn, ANCHOR), sources=source_refs(loaded_conn)
        )
        assert _walk_payload(payload) == []

    def test_explanation_payload(self, loaded_conn: sqlite3.Connection) -> None:
        payload = explanation_dict(
            explain(loaded_conn, ANCHOR, "65162-993-08"),
            sources=source_refs(loaded_conn),
        )
        assert _walk_payload(payload) == []

    def test_signal_payload(self, loaded_conn: sqlite3.Connection) -> None:
        payload = signal_dict(
            signal_report(loaded_conn, "00378464226"),
            sources=source_refs(loaded_conn),
        )
        assert _walk_payload(payload) == []

    def test_search_payload(self, loaded_conn: sqlite3.Connection) -> None:
        payload = search_results_dict(
            "estradiol",
            search(loaded_conn, "estradiol"),
            sources=source_refs(loaded_conn),
        )
        assert _walk_payload(payload) == []

    def test_the_walker_actually_fails_on_stripped_provenance(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        # Planted defect: an instrument that cannot fail proves nothing.
        payload = resolution_dict(
            resolve(loaded_conn, ANCHOR), sources=source_refs(loaded_conn)
        )
        stripped = dict(payload)
        del stripped["sources"]
        assert _walk_payload(stripped) != []
        no_disclaimer = dict(payload)
        no_disclaimer["disclaimer"] = ""
        assert _walk_payload(no_disclaimer) != []
        gutted = dict(payload)
        gutted["sources"] = {
            k: {**v, "url": ""} for k, v in payload["sources"].items()
        }
        assert _walk_payload(gutted) != []


class TestApplicationDeepLinkOnRows:
    def test_anchor_row_links_to_its_orange_book_page(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        payload = resolution_dict(
            resolve(loaded_conn, ANCHOR), sources=source_refs(loaded_conn)
        )
        seed = payload["seed"]
        assert seed is not None
        assert seed["application_url"] is not None
        assert "accessdata.fda.gov" in seed["application_url"]
        assert "Appl_No=201675" in seed["application_url"]
