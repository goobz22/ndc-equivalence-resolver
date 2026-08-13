"""Class-level supply assessment — the shortage-triangulation view.

The motivating case: FDA's shortage list stays empty while a real
shortage runs. The class assessment must surface the constraint from
independent public evidence: class price drift + survey dropouts +
falling dispensed volume + recalls.
"""

import sqlite3

import pytest

from ndcres.resolve import resolve
from ndcres.signals import (
    VERDICT_CONSTRAINT,
    VERDICT_FDA_LISTED,
    VERDICT_QUIET,
    class_supply_assessment,
)


class TestIngestOfNewSources:
    def test_sdud_aggregates_states_and_skips_suppressed(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT units, prescriptions, state_rows FROM sdud "
            "WHERE ndc11 = '00378464226' AND year = 2025 AND quarter = 2"
        ).fetchone()
        assert row["units"] == pytest.approx(80000.0)  # CA + TX summed
        assert row["state_rows"] == 2
        # 2026Q2 exists despite the suppressed WY row (skipped, not summed).
        collapsed = loaded_conn.execute(
            "SELECT units FROM sdud "
            "WHERE ndc11 = '00378464226' AND year = 2026 AND quarter = 2"
        ).fetchone()
        assert collapsed["units"] == pytest.approx(56000.0)

    def test_enforcement_indexed_by_product_ndc(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        row = loaded_conn.execute(
            "SELECT classification, status FROM enforcement "
            "WHERE ndc9 = '003784642'"
        ).fetchone()
        assert row["classification"] == "Class II"
        assert row["status"] == "Ongoing"

    def test_enforcement_without_ndc_is_kept_unindexed(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        count = loaded_conn.execute(
            "SELECT count(*) AS n FROM enforcement WHERE ndc9 IS NULL"
        ).fetchone()["n"]
        assert count == 1


class TestAssessment:
    def test_estradiol_class_shows_constraint_without_fda_listing(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        resolution = resolve(loaded_conn, "0378-4642-26")
        assessment = resolution.class_assessment
        assert assessment is not None
        # FDA's list is silent — and the verdict still finds the constraint.
        assert assessment.fda_listed_members == 0
        assert assessment.verdict == VERDICT_CONSTRAINT
        # The three independent fingerprints:
        assert assessment.drift_fired  # class price +22.5% (fixture)
        assert assessment.volume_change_pct is not None
        assert assessment.volume_change_pct == pytest.approx(-0.30, abs=0.01)
        assert assessment.recalls >= 1
        # And the evidence lines say why, citing the lagging-list caveat.
        joined = " ".join(assessment.lines)
        assert "manufacturer-self-reported" in joined
        assert "class acquisition cost" in joined
        assert "dispensed volume" in joined

    def test_fda_listed_dominates(self, tmp_path) -> None:  # type: ignore[no-untyped-def]
        from test_signals import TestShortage

        conn = TestShortage._conn_with_synthetic_shortage(tmp_path)
        resolution = resolve(conn, "0378-4642-26")
        assert resolution.class_assessment is not None
        assert resolution.class_assessment.verdict == VERDICT_FDA_LISTED

    def test_quiet_class_reads_quiet_not_available(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        # The oral tablet class: flat price, no volume data, no recalls.
        assessment = class_supply_assessment(loaded_conn, ("00555088602",))
        assert assessment.verdict == VERDICT_QUIET
        assert "NOT a statement of availability" in assessment.verdict_language

    def test_assessment_members_are_the_legal_class(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        resolution = resolve(loaded_conn, "0378-4642-26")
        assessment = resolution.class_assessment
        assert assessment is not None
        # seed + the four fixture T1 members.
        assert assessment.member_count == 5

    def test_web_payload_carries_the_assessment(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        from ndcres.serialize import resolution_dict

        payload = resolution_dict(resolve(loaded_conn, "0378-4642-26"))
        assessment = payload["class_assessment"]
        assert assessment is not None
        assert assessment["verdict"] == VERDICT_CONSTRAINT
        assert assessment["lines"]
