"""Class-level supply assessment — the shortage-triangulation view.

The motivating case: FDA's shortage list stays empty while a real
shortage runs. The class assessment must surface the constraint from
independent public evidence: class price drift + survey dropouts +
falling dispensed volume + recalls.
"""

import sqlite3
from pathlib import Path

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

    def test_fda_listed_dominates(self, tmp_path: Path) -> None:
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

    def test_demand_surge_is_a_constraint_fingerprint(
        self, fresh_conn: sqlite3.Connection
    ) -> None:
        # The 2026 estradiol reality: volume UP 76% YoY (demand surge)
        # with price drift — a strain fingerprint, worded as such.
        from conftest import FULL

        from ndcres.ingest import refresh

        refresh(fresh_conn, from_dir=FULL)
        with fresh_conn:
            run_id = fresh_conn.execute(
                "SELECT max(run_id) AS r FROM source_run"
            ).fetchone()["r"]
            for (year, quarter, units) in [(2025, 2, 10000.0), (2026, 2, 18000.0)]:
                fresh_conn.execute(
                    "INSERT OR REPLACE INTO sdud "
                    "(ndc11, year, quarter, units, prescriptions, state_rows, run_id) "
                    "VALUES ('00555088602', ?, ?, ?, 0, 1, ?)",
                    (year, quarter, units, run_id),
                )
        assessment = class_supply_assessment(fresh_conn, ("00555088602",))
        assert assessment.volume_change_pct == pytest.approx(0.80)
        joined = " ".join(assessment.lines)
        assert "demand surge" in joined

    def test_web_payload_carries_the_assessment(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        from ndcres.provenance import source_refs
        from ndcres.serialize import resolution_dict

        payload = resolution_dict(
            resolve(loaded_conn, "0378-4642-26"), sources=source_refs(loaded_conn)
        )
        assessment = payload["class_assessment"]
        assert assessment is not None
        assert assessment["verdict"] == VERDICT_CONSTRAINT
        assert assessment["lines"]


ESTRADIOL_KEY = ("ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:50", "AB1")


def _plant_snapshots(conn: sqlite3.Connection, deltas: list[tuple[str, str, str | None, str | None]]) -> None:
    """Two membership runs + planted vanish deltas (ndc11, change, last_end_marketing, last_ob_type)."""
    with conn:
        conn.execute(
            "INSERT INTO ndc_membership_run (snapshot_date, present_count, "
            "appeared_count, vanished_count, is_baseline) VALUES "
            "('2026-08-01', 100, 0, 0, 1)"
        )
        conn.execute(
            "INSERT INTO ndc_membership_run (snapshot_date, present_count, "
            "appeared_count, vanished_count, is_baseline) VALUES "
            "('2026-08-08', 98, 0, 2, 0)"
        )
        conn.executemany(
            "INSERT INTO ndc_membership_delta (snapshot_date, ndc11, change, "
            "last_end_marketing, last_ob_type, ingredient_set, df_route, "
            "strength_norm, te_code) VALUES ('2026-08-08', ?, ?, ?, ?, ?, ?, ?, ?)",
            [(n, c, em, ob, *ESTRADIOL_KEY) for (n, c, em, ob) in deltas],
        )


class TestDropoutDisambiguation:
    def test_end_marketed_dropout_counts_as_discontinued_not_dropout(
        self, tmp_path: Path
    ) -> None:
        # Planted defect: end-market a member that ALSO vanished from
        # the price survey — it must move to discontinued_members and
        # leave BOTH dropout terms.
        from conftest import FULL
        from ndcres.db import connect
        from ndcres.ingest import refresh

        conn = connect(tmp_path / "t.db")
        refresh(conn, from_dir=FULL)
        from ndcres.resolve import resolve

        resolution = resolve(conn, "0378-4642-26")
        base = resolution.class_assessment
        assert base is not None and base.discontinued_members == 0
        member = "65162099308"  # Dotti — surveyed in fixtures
        with conn:
            conn.execute(
                "UPDATE package SET end_marketing = '2026-06-30' WHERE ndc11 = ?",
                (member,),
            )
        after = resolve(conn, "0378-4642-26").class_assessment
        assert after is not None
        assert after.discontinued_members == 1
        assert after.surveyed_count == base.surveyed_count - 1
        assert any("end-marketed" in line for line in after.lines)

    def test_still_marketed_dropout_still_fires(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        # Regression pin: the fixture's planted still-marketed NADAC
        # dropout keeps counting (the 97%-valid case must not be lost
        # to the discontinuation fix).
        from ndcres.signals import class_supply_assessment

        assessment = class_supply_assessment(
            loaded_conn,
            ("00378464226", "65162099308", "00781714483", "70710119308",
             "66758014783"),
        )
        assert assessment.surveyed_count > 0


class TestDirectoryExitAxis:
    def test_fires_on_planted_silent_exits(self, tmp_path: Path) -> None:
        from conftest import FULL
        from ndcres.db import connect
        from ndcres.ingest import refresh
        from ndcres.signals import class_supply_assessment

        conn = connect(tmp_path / "t.db")
        refresh(conn, from_dir=FULL)
        _plant_snapshots(
            conn,
            [
                ("00378464299", "vanished", None, "RX"),
                ("65162099399", "vanished", None, "RX"),
            ],
        )
        assessment = class_supply_assessment(
            conn, ("00378464226",), class_key=ESTRADIOL_KEY
        )
        assert assessment.directory_exits == 2
        assert assessment.directory_exit_fired
        assert any("vanished from the weekly NDC directory" in line
                   for line in assessment.lines)

    def test_end_marketed_vanish_never_fires(self, tmp_path: Path) -> None:
        # The axis's whole point: a formally end-marketed exit is
        # discontinuation, not a silent supply exit.
        from conftest import FULL
        from ndcres.db import connect
        from ndcres.ingest import refresh
        from ndcres.signals import class_supply_assessment

        conn = connect(tmp_path / "t.db")
        refresh(conn, from_dir=FULL)
        _plant_snapshots(
            conn,
            [
                ("00378464299", "vanished", "2026-06-30", "RX"),
                ("65162099399", "vanished", None, "DISCN"),
            ],
        )
        assessment = class_supply_assessment(
            conn, ("00378464226",), class_key=ESTRADIOL_KEY
        )
        assert assessment.directory_exits == 0
        assert not assessment.directory_exit_fired

    def test_none_without_two_snapshots_and_never_counts(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        from ndcres.signals import class_supply_assessment

        with_key = class_supply_assessment(
            loaded_conn, ("00378464226",), class_key=ESTRADIOL_KEY
        )
        without_key = class_supply_assessment(loaded_conn, ("00378464226",))
        assert with_key.directory_exits is None
        assert not with_key.directory_exit_fired
        # The un-computable axis contributes NOTHING to the tally.
        assert with_key.fingerprints == without_key.fingerprints
        assert any("accumulating" in line for line in with_key.lines)

    def test_payload_carries_axis_count(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        from ndcres.serialize import class_assessment_dict
        from ndcres.signals import FINGERPRINT_AXES, class_supply_assessment

        payload = class_assessment_dict(
            class_supply_assessment(loaded_conn, ("00378464226",))
        )
        assert payload["fingerprint_axes"] == FINGERPRINT_AXES == 5


class TestDropoutRecencyBound:
    def test_ancient_departures_are_not_dropouts(self, tmp_path: Path) -> None:
        # Planted defect: a member whose last survey appearance is YEARS
        # old must be treated like never-surveyed — otherwise the axis's
        # meaning silently depends on how much NADAC history is ingested
        # (the confound the 5-axis re-review caught on live data).
        from conftest import FULL
        from ndcres.db import connect
        from ndcres.ingest import refresh
        from ndcres.signals import class_supply_assessment

        conn = connect(tmp_path / "t.db")
        refresh(conn, from_dir=FULL)
        member = "65162099308"  # Dotti — surveyed in fixtures
        base = class_supply_assessment(conn, ("00378464226", member))
        with conn:
            # Push the member's entire survey presence 5 years back.
            conn.execute(
                "UPDATE nadac SET as_of_last = '2021-01-01', "
                "as_of_first = '2020-01-01' WHERE ndc11 = ?",
                (member,),
            )
        bounded = class_supply_assessment(conn, ("00378464226", member))
        assert bounded.surveyed_count == base.surveyed_count - 1
        assert bounded.dropout_members == base.dropout_members
