"""Market-wide sweep goldens (SPEC §10).

The load-bearing pin is COHERENCE: a sweep row's members must equal the
legal class resolve computes (seed+T1+T2) for a member seed — one
verdict engine, two entry points, zero drift. The universal invariants
(verdict↔fingerprint mapping, no sample/discontinued members) are pinned
over EVERY swept class, which is stronger than any single planted row.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ndcres.db import connect
from ndcres.ingest import refresh
from ndcres.signals import (
    VERDICT_CONSTRAINT,
    VERDICT_FDA_LISTED,
    VERDICT_MIXED,
    VERDICT_QUIET,
)
from ndcres.sweep import enumerate_classes, latest_sweep_id, persist_sweep, run_sweep

FIXTURES = Path(__file__).parent / "fixtures" / "full"

ESTRADIOL_KEY = ("ESTRADIOL", "SYSTEM;TRANSDERMAL")


def _estradiol_anchor_class(result_classes):  # type: ignore[no-untyped-def]
    for row in result_classes:
        if (
            row.ingredient_set == "ESTRADIOL"
            and row.te_code == "AB1"
            and row.df_route.startswith("SYSTEM")
        ):
            return row
    raise AssertionError("anchor AB1 estradiol class missing from sweep")


class TestSweepGoldens:
    def test_anchor_class_reads_constraint_without_fda_listing(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        result = run_sweep(loaded_conn)
        row = _estradiol_anchor_class(result.classes)
        assert row.assessment.verdict == VERDICT_CONSTRAINT
        assert row.assessment.fda_listed_members == 0
        assert row.assessment.fingerprints >= 2

    def test_sweep_members_equal_resolves_legal_class(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        from ndcres.resolve import resolve

        eq_class = next(
            c
            for c in enumerate_classes(loaded_conn)
            if c.ingredient_set == "ESTRADIOL"
            and c.te_code == "AB1"
            and c.df_route.startswith("SYSTEM")
        )
        resolution = resolve(loaded_conn, "0378-4642-26")
        legal = set()
        if resolution.seed_annotation and resolution.seed_annotation.dims.ndc11:
            legal.add(resolution.seed_annotation.dims.ndc11)
        for tier in ("T1", "T2"):
            for annotated in resolution.tiers.get(tier, []):
                if annotated.dims.ndc11:
                    legal.add(annotated.dims.ndc11)
        assert set(eq_class.members) == legal

    def test_verdict_ladder_holds_for_every_class(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        result = run_sweep(loaded_conn)
        assert result.classes
        for row in result.classes:
            a = row.assessment
            if a.fda_listed_members > 0:
                assert a.verdict == VERDICT_FDA_LISTED, row
            elif a.fingerprints >= 2:
                assert a.verdict == VERDICT_CONSTRAINT, row
            elif a.fingerprints == 1:
                assert a.verdict == VERDICT_MIXED, row
            else:
                assert a.verdict == VERDICT_QUIET, row

    def test_fda_listed_class_still_reports_fingerprints(
        self, tmp_path: Path
    ) -> None:
        # With the synthetic estradiol shortage loaded (the real full
        # fixture mirrors reality: zero estradiol records), the class
        # verdict short-circuits to fda-listed — but the independent-
        # evidence count must STILL be reported: the listed-but-quiet
        # gap list depends on it.
        import shutil

        conn = connect(tmp_path / "t.db")
        refresh(conn, from_dir=FIXTURES)
        synthetic_dir = tmp_path / "synthetic"
        synthetic_dir.mkdir()
        shutil.copy(
            FIXTURES.parent / "shortages_synthetic_estradiol.json",
            synthetic_dir / "shortages.json",
        )
        refresh(conn, sources=("shortage",), from_dir=synthetic_dir)
        result = run_sweep(conn)
        listed = [
            row
            for row in result.classes
            if row.assessment.verdict == VERDICT_FDA_LISTED
        ]
        assert listed, "synthetic shortage produced no fda-listed class"
        anchor = _estradiol_anchor_class(result.classes)
        assert anchor.assessment.verdict == VERDICT_FDA_LISTED
        # The estradiol class has ≥2 independent fingerprints in the
        # fixtures — the short-circuit must not zero them out.
        assert anchor.assessment.fingerprints >= 2

    def test_no_member_is_sample_or_discontinued_excluded(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        for eq_class in enumerate_classes(loaded_conn):
            placeholders = ",".join("?" for _ in eq_class.members)
            samples = loaded_conn.execute(
                f"SELECT count(*) FROM package WHERE ndc11 IN ({placeholders})"
                " AND sample_package = 1",
                eq_class.members,
            ).fetchone()[0]
            assert samples == 0, eq_class
            assert eq_class.marketed_count > 0, eq_class

    def test_enumeration_is_deterministic(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        first = enumerate_classes(loaded_conn)
        second = enumerate_classes(loaded_conn)
        assert first == second
        for eq_class in first:
            assert eq_class.rep_ndc11 in eq_class.members


class TestSweepPersistence:
    def test_append_only_two_runs(self, fresh_conn: sqlite3.Connection) -> None:
        refresh(fresh_conn, from_dir=FIXTURES)
        first_id = persist_sweep(fresh_conn, run_sweep(fresh_conn))
        second_id = persist_sweep(fresh_conn, run_sweep(fresh_conn))
        assert second_id == first_id + 1
        assert latest_sweep_id(fresh_conn) == second_id
        runs = fresh_conn.execute("SELECT count(*) FROM sweep_run").fetchone()[0]
        assert runs == 2
        per_run = fresh_conn.execute(
            "SELECT sweep_id, count(*) AS n FROM sweep_class GROUP BY sweep_id"
        ).fetchall()
        assert len(per_run) == 2
        assert per_run[0]["n"] == per_run[1]["n"] > 0

    def test_history_survives_a_refresh(
        self, fresh_conn: sqlite3.Connection
    ) -> None:
        refresh(fresh_conn, from_dir=FIXTURES)
        sweep_id = persist_sweep(fresh_conn, run_sweep(fresh_conn))
        refresh(fresh_conn, from_dir=FIXTURES)  # mirror tables wiped+rebuilt
        survived = fresh_conn.execute(
            "SELECT count(*) FROM sweep_class WHERE sweep_id = ?", (sweep_id,)
        ).fetchone()[0]
        assert survived > 0
        assert latest_sweep_id(fresh_conn) == sweep_id

    def test_persisted_rows_round_trip_the_assessment(
        self, fresh_conn: sqlite3.Connection
    ) -> None:
        refresh(fresh_conn, from_dir=FIXTURES)
        result = run_sweep(fresh_conn)
        sweep_id = persist_sweep(fresh_conn, result)
        anchor = _estradiol_anchor_class(result.classes)
        stored = fresh_conn.execute(
            """
            SELECT * FROM sweep_class
            WHERE sweep_id = ? AND ingredient_set = 'ESTRADIOL'
              AND te_code = 'AB1' AND df_route LIKE 'SYSTEM%'
            """,
            (sweep_id,),
        ).fetchone()
        assert stored is not None
        assert stored["verdict"] == anchor.assessment.verdict
        assert stored["fingerprints"] == anchor.assessment.fingerprints
        assert stored["rep_ndc11"] == anchor.rep_ndc11
        assert stored["surveyed_count"] == anchor.assessment.surveyed_count
