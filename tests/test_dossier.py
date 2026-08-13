"""Evidence dossier (SPEC §11).

The load-bearing pin is operator decision #4: the PUBLIC case study
contains only claims derivable from ingested data — enforced here as a
URL allowlist over the rendered markdown (the only links permitted are
the ingested sources' own registry pages and this repository), plus the
language-discipline scan.
"""

from __future__ import annotations

import re
import sqlite3

import pytest

from ndcres.dossier import (
    EXTERNAL_REFERENCES,
    build_dossier,
    dossier_dict,
    dossier_exhibits,
    dossier_markdown,
)
from ndcres.provenance import SOURCE_REGISTRY
from ndcres.resolve import ResolveError

ANCHOR = "0378-4642-26"
_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")

ALLOWED_PREFIXES = tuple(
    identity["url"] for identity in SOURCE_REGISTRY.values()
) + ("https://github.com/goobz22/ndc-equivalence-resolver",)


class TestPublicCaseStudy:
    def test_builds_for_the_anchor(self, loaded_conn: sqlite3.Connection) -> None:
        dossier = build_dossier(loaded_conn, ANCHOR)
        assert dossier.class_key[0] == "ESTRADIOL"
        assert dossier.class_key[3] == "AB1"
        assert dossier.members
        assert dossier.nadac_series
        assert dossier.sdud_trend

    def test_public_markdown_is_ingested_data_only(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        markdown = dossier_markdown(build_dossier(loaded_conn, ANCHOR))
        for url in _URL_RE.findall(markdown):
            assert url.startswith(ALLOWED_PREFIXES), (
                f"public case study contains a non-ingested-source URL: {url}"
            )

    def test_every_section_carries_a_vintage(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        markdown = dossier_markdown(build_dossier(loaded_conn, ANCHOR))
        for heading in ("The class", "FDA shortage list", "Acquisition-cost",
                        "Dispensed volume", "Recalls"):
            match = re.search(rf"## {re.escape(heading)}[^\n]*", markdown)
            assert match is not None, heading
            assert "fetched" in match.group(0), (
                f"section {heading!r} lacks its vintage stamp"
            )

    def test_language_discipline(self, loaded_conn: sqlite3.Connection) -> None:
        markdown = dossier_markdown(build_dossier(loaded_conn, ANCHOR))
        assert "shortage confirmed" not in markdown.lower()
        assert "evidence consistent with" in markdown.lower()
        assert "not medical advice" in markdown.lower()
        assert "Reproduce this" in markdown

    def test_absence_reads_lagging_never_available(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        # The real fixture slice has NO estradiol shortage records — the
        # dossier must render absence as lagging-list language.
        markdown = dossier_markdown(build_dossier(loaded_conn, ANCHOR))
        assert "No entry for any of the" in markdown
        assert "absence is not availability" in markdown.lower()

    def test_deterministic(self, loaded_conn: sqlite3.Connection) -> None:
        first = dossier_markdown(build_dossier(loaded_conn, ANCHOR))
        second = dossier_markdown(build_dossier(loaded_conn, ANCHOR))
        assert first == second


class TestExhibitPack:
    def test_structure_and_separation(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        exhibits = dossier_exhibits(build_dossier(loaded_conn, ANCHOR))
        assert "Requested action" in exhibits
        assert "Statement of grounds" in exhibits
        assert "21 CFR 10.30" in exhibits
        assert "NOT pipeline data" in exhibits
        assert "lawyer" in exhibits.lower()
        # External references appear ONLY after the separation banner.
        banner = exhibits.index("NOT pipeline data")
        for ref in EXTERNAL_REFERENCES:
            assert exhibits.index(ref.url) > banner

    def test_external_refs_carry_access_dates(self) -> None:
        for ref in EXTERNAL_REFERENCES:
            assert re.match(r"\d{4}-\d{2}-\d{2}$", ref.accessed), ref.label
            assert ref.url.startswith("https://"), ref.label


class TestDossierPayload:
    def test_dict_carries_provenance_and_disclaimer(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        payload = dossier_dict(build_dossier(loaded_conn, ANCHOR))
        assert payload["sources"] and payload["disclaimer"]
        assert payload["assessment"]["verdict_language"]
        assert payload["members"]

    def test_unrated_seed_fails_helpfully(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        # Divigel (gel, no TE-rated class shared with the patch family)
        # either resolves without an eq_group or errors — never a bogus
        # dossier. Use an NDC known to lack a TE-rated group.
        row = loaded_conn.execute(
            """
            SELECT k.ndc11 FROM package k
            JOIN product p USING (ndc9)
            WHERE p.ob_link_status = 'no-application' LIMIT 1
            """
        ).fetchone()
        assert row is not None
        with pytest.raises(ResolveError):
            build_dossier(loaded_conn, row["ndc11"])
