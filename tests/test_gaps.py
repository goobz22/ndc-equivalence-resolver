"""Gap report goldens (SPEC §12)."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from ndcres.db import connect
from ndcres.gaps import GapError, gap_report
from ndcres.ingest import refresh
from ndcres.signals import VERDICT_CONSTRAINT, VERDICT_FDA_LISTED
from ndcres.sweep import persist_sweep, run_sweep

FIXTURES = Path(__file__).parent / "fixtures" / "full"
SYNTHETIC_SHORTAGE = (
    Path(__file__).parent / "fixtures" / "shortages_synthetic_estradiol.json"
)


@pytest.fixture()
def swept_conn(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "t.db")
    refresh(conn, from_dir=FIXTURES)
    persist_sweep(conn, run_sweep(conn))
    return conn


class TestGapReport:
    def test_estradiol_leads_the_unlisted_list(
        self, swept_conn: sqlite3.Connection
    ) -> None:
        report = gap_report(swept_conn)
        assert report.unlisted_constraints
        top = report.unlisted_constraints[0]
        assert top.ingredient_set == "ESTRADIOL"
        assert top.fda_listed_members == 0
        assert top.fingerprints >= 2

    def test_partition_is_clean(self, swept_conn: sqlite3.Connection) -> None:
        report = gap_report(swept_conn)
        for entry in report.unlisted_constraints:
            assert entry.verdict == VERDICT_CONSTRAINT
            assert entry.fda_listed_members == 0
        for entry in report.fda_listed:
            assert entry.verdict == VERDICT_FDA_LISTED
        quiet_set = {
            (e.ingredient_set, e.df_route, e.strength_norm, e.te_code)
            for e in report.listed_but_quiet
        }
        listed_set = {
            (e.ingredient_set, e.df_route, e.strength_norm, e.te_code)
            for e in report.fda_listed
        }
        assert quiet_set <= listed_set
        for entry in report.listed_but_quiet:
            assert entry.fingerprints == 0

    def test_ranking_is_deterministic_and_ordered(
        self, swept_conn: sqlite3.Connection
    ) -> None:
        first = gap_report(swept_conn)
        second = gap_report(swept_conn)
        assert first == second
        fingerprints = [e.fingerprints for e in first.unlisted_constraints]
        assert fingerprints == sorted(fingerprints, reverse=True)

    def test_counts_match_the_run_summary(
        self, swept_conn: sqlite3.Connection
    ) -> None:
        report = gap_report(swept_conn)
        assert len(report.unlisted_constraints) == report.counts["constraint"]
        assert len(report.fda_listed) == report.counts["fda_listed"]

    def test_no_sweep_is_a_loud_error(self, tmp_path: Path) -> None:
        conn = connect(tmp_path / "empty.db")
        refresh(conn, from_dir=FIXTURES)
        with pytest.raises(GapError, match="run `ndcres sweep`"):
            gap_report(conn)

    def test_fda_listed_class_moves_lists_when_listed(
        self, tmp_path: Path
    ) -> None:
        conn = connect(tmp_path / "t.db")
        refresh(conn, from_dir=FIXTURES)
        synthetic_dir = tmp_path / "synthetic"
        synthetic_dir.mkdir()
        shutil.copy(SYNTHETIC_SHORTAGE, synthetic_dir / "shortages.json")
        refresh(conn, sources=("shortage",), from_dir=synthetic_dir)
        persist_sweep(conn, run_sweep(conn))
        report = gap_report(conn)
        listed_estradiol = [
            e for e in report.fda_listed if e.ingredient_set == "ESTRADIOL"
        ]
        assert listed_estradiol, "estradiol must move to fda_listed when listed"
        assert all(
            e.ingredient_set != "ESTRADIOL" or e.te_code != "AB1"
            for e in report.unlisted_constraints
        )

    def test_payload_carries_provenance(
        self, swept_conn: sqlite3.Connection
    ) -> None:
        from ndcres.provenance import source_refs
        from ndcres.serialize import gap_report_dict

        payload = gap_report_dict(
            gap_report(swept_conn), sources=source_refs(swept_conn), limit=10
        )
        assert payload["sources"] and payload["disclaimer"]
        assert payload["totals"]["unlisted_constraints"] >= len(
            payload["unlisted_constraints"]
        )
        assert "never a confirmed shortage" in payload["note"]
