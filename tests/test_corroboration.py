"""Corroborations (SPEC §12): citation-only, never verdict-affecting."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from ndcres.corroboration import (
    CORROBORATIONS,
    SOURCE_LABELS,
    Corroboration,
    CorroborationSource,
    corroborations_for,
)
from ndcres.db import connect
from ndcres.gaps import gap_report, worksheet
from ndcres.ingest import refresh
from ndcres.sweep import persist_sweep, run_sweep

FIXTURES = Path(__file__).parent / "fixtures" / "full"


@pytest.fixture()
def swept_conn(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "t.db")
    refresh(conn, from_dir=FIXTURES)
    persist_sweep(conn, run_sweep(conn))
    return conn


class TestCuratedEntries:
    def test_entry_shapes(self) -> None:
        for entry in CORROBORATIONS:
            assert len(entry.class_key) == 4
            assert entry.class_key[0] == entry.class_key[0].upper()
            assert entry.sources, entry.class_key
            for source in entry.sources:
                assert source.source in SOURCE_LABELS, source.source
                assert source.url.startswith("https://"), source.url
                assert re.match(r"^\d{4}-\d{2}-\d{2}$", source.accessed)
                assert source.note
                assert "confirmed" not in source.note.lower()

    def test_no_duplicate_class_keys(self) -> None:
        keys = [entry.class_key for entry in CORROBORATIONS]
        assert len(keys) == len(set(keys))

    def test_lookup_misses_cleanly(self) -> None:
        assert corroborations_for(("NOPE", "X;Y", "UG:1", "AA")) == ()


class TestCitationOnlyPin:
    def test_corroboration_never_alters_verdict_or_rank(
        self, swept_conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Planted defect: a fake corroboration on EVERY class must leave
        # the gap report byte-identical — corroborations annotate, never
        # rank or verdict.
        before = gap_report(swept_conn)
        fake = CorroborationSource(
            source="ashp",
            url="https://example.invalid/fake",
            accessed="2026-08-14",
            note="planted",
        )
        import ndcres.corroboration as corroboration_module

        monkeypatch.setattr(
            corroboration_module,
            "corroborations_for",
            lambda key: (fake,),
        )
        after = gap_report(swept_conn)
        assert before == after

    def test_gap_payload_carries_corroborations(
        self, swept_conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from ndcres.provenance import source_refs
        from ndcres.serialize import gap_report_dict
        import ndcres.serialize as serialize_module

        fake = CorroborationSource(
            source="au-tga",
            url="https://example.invalid/tga",
            accessed="2026-08-14",
            note="also listed",
        )
        import ndcres.corroboration as corroboration_module

        monkeypatch.setattr(
            corroboration_module, "corroborations_for", lambda key: (fake,)
        )
        payload = gap_report_dict(
            gap_report(swept_conn), sources=source_refs(swept_conn), limit=5
        )
        entry = payload["unlisted_constraints"][0]
        assert entry["corroborated_by"] == [
            {
                "source": "au-tga",
                "url": "https://example.invalid/tga",
                "accessed": "2026-08-14",
                "note": "also listed",
            }
        ]


class TestWorksheet:
    def test_worksheet_matches_report_ordering(
        self, swept_conn: sqlite3.Connection
    ) -> None:
        report = gap_report(swept_conn)
        rows = worksheet(swept_conn, 10)
        assert len(rows) == min(10, len(report.unlisted_constraints))
        for row, entry in zip(rows, report.unlisted_constraints):
            assert row["ingredient_set"] == entry.ingredient_set
            assert row["te_code"] == entry.te_code
            assert row["rep_ndc11"] == entry.rep_ndc11

    def test_worksheet_rows_are_checkable(
        self, swept_conn: sqlite3.Connection
    ) -> None:
        rows = worksheet(swept_conn, 5)
        assert rows
        for row in rows:
            assert row["slug"]
            assert row["generic_names"] or row["brand_names"]
            assert row["labelers"]
            for url in row["ob_urls"]:
                assert url.startswith("https://www.accessdata.fda.gov/")

    def test_worksheet_is_deterministic(
        self, swept_conn: sqlite3.Connection
    ) -> None:
        assert worksheet(swept_conn, 10) == worksheet(swept_conn, 10)
