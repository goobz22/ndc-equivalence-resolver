"""Backtest harness (SPEC §13): parser, replay, and lead-time math."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ndcres.backtest.leadtime import (
    class_members_for_name,
    fingerprints_at,
    lead_time_report,
)
from ndcres.backtest.wayback import (
    EXPECTED_COLUMNS,
    LegacyRow,
    parse_legacy_csv,
    store_snapshot,
)

# Verbatim from the 2022-01-15 Wayback capture of Drugshortages.cfm
# (header spacing exactly as served).
LEGACY_HEADER = (
    "Generic Name,Company Name, Contact Info, Presentation, Type of Update,"
    "Date of Update, Availability Information, Related Information, "
    "Resolved Note, Reason for Shortage, Therapeutic Category, Status, "
    "Change Date, Date Discontinued, Initial Posting Date, "
    "Generic Name Note, Generic Name Link , Company Info Link, "
    "Availability Link, Related Info Link,   Resolved Note Link, "
    "Discontinued Note Link"
)
LEGACY_ROW = (
    '"Abacavir Sulfate and Lamivudine Tablets","Teva Pharmaceuticals",'
    '"800-545-8800","600 mg and 300 mg  (NDC 0093-5382-56)","New",'
    '"10/02/2020","","","","","Antiviral","To be Discontinued",'
    '"10/02/2020","10/02/2020","10/02/2020","","","","","","",""'
)


class TestLegacyCsvParser:
    def test_parses_the_real_shape(self) -> None:
        rows = parse_legacy_csv(f"{LEGACY_HEADER}\n{LEGACY_ROW}\n")
        assert len(rows) == 1
        row = rows[0]
        assert row.generic_name == "Abacavir Sulfate and Lamivudine Tablets"
        assert row.company == "Teva Pharmaceuticals"
        assert row.status == "To be Discontinued"
        assert row.initial_posting == "2020-10-02"
        assert row.update_date == "2020-10-02"

    def test_header_drift_fails_loudly(self) -> None:
        broken = LEGACY_HEADER.replace("Initial Posting Date", "Posted")
        with pytest.raises(RuntimeError, match="header drift"):
            parse_legacy_csv(f"{broken}\n{LEGACY_ROW}\n")

    def test_empty_snapshot_fails_loudly(self) -> None:
        with pytest.raises(RuntimeError, match="empty"):
            parse_legacy_csv("")

    def test_malformed_dates_become_none(self) -> None:
        row = LEGACY_ROW.replace('"10/02/2020","10/02/2020","10/02/2020"',
                                 '"10/02/2020","10/02/2020","pending"')
        parsed = parse_legacy_csv(f"{LEGACY_HEADER}\n{row}\n")
        assert parsed[0].initial_posting is None

    def test_expected_columns_are_the_pinned_legacy_set(self) -> None:
        assert "Generic Name" in EXPECTED_COLUMNS
        assert "Initial Posting Date" in EXPECTED_COLUMNS
        assert len(EXPECTED_COLUMNS) == 15


class TestSnapshotStorage:
    def test_store_dedupes_on_the_pk(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        rows = [
            LegacyRow(
                generic_name="Estradiol Transdermal System",
                company="X",
                status="Current",
                initial_posting="2021-05-01",
                update_date="2021-06-01",
            )
        ]
        first = store_snapshot(loaded_conn, "20210601000000", rows)
        second = store_snapshot(loaded_conn, "20210601000000", rows)
        assert first == 1 and second == 0
        stored = loaded_conn.execute(
            "SELECT snapshot_date, drug_name_norm FROM fda_list_history "
            "WHERE snapshot_source = 'wayback-cfm'"
        ).fetchone()
        assert stored["snapshot_date"] == "2021-06-01"
        assert stored["drug_name_norm"] == "ESTRADIOL TRANSDERMAL SYSTEM"


class TestNameMapping:
    def test_estradiol_name_maps_to_te_rated_classes(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        classes, members = class_members_for_name(
            loaded_conn, "ESTRADIOL TRANSDERMAL SYSTEM"
        )
        assert classes >= 3  # AB1 / AB2 / AB3 at minimum
        assert "00378464226" in members

    def test_unknown_name_maps_nowhere(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        classes, members = class_members_for_name(loaded_conn, "ZZQXV ELIXIR")
        assert classes == 0 and members == ()


class TestFingerprintReplay:
    def test_fires_at_the_fixture_horizon(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        _, members = class_members_for_name(
            loaded_conn, "ESTRADIOL TRANSDERMAL SYSTEM"
        )
        # At the dataset horizon the estradiol family shows the pattern.
        assert fingerprints_at(loaded_conn, members, "2026-08-13") >= 2

    def test_quiet_before_the_data_exists(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        _, members = class_members_for_name(
            loaded_conn, "ESTRADIOL TRANSDERMAL SYSTEM"
        )
        # Cutoff before any fixture NADAC/SDUD data: nothing can fire —
        # the replay must never leak post-cutoff information.
        assert fingerprints_at(loaded_conn, members, "2023-01-01") == 0

    def test_empty_members_zero(self, loaded_conn: sqlite3.Connection) -> None:
        assert fingerprints_at(loaded_conn, (), "2026-01-01") == 0


class TestLeadTimeReport:
    def test_report_over_planted_history(self, tmp_path: Path) -> None:
        # A fresh database: the report's first-posting semantics exclude
        # any drug whose posting history starts before `since`, so this
        # test must own its whole history (the shared session fixture
        # accumulates other tests' planted snapshots).
        from ndcres.db import connect
        from ndcres.ingest import refresh

        fixtures = Path(__file__).parent / "fixtures" / "full"
        conn = connect(tmp_path / "t.db")
        refresh(conn, from_dir=fixtures)
        store_snapshot(
            conn,
            "20260801000000",
            [
                LegacyRow(
                    generic_name="Estradiol Transdermal System",
                    company="Planted",
                    status="Current",
                    initial_posting="2026-06-01",
                    update_date="2026-07-01",
                ),
                LegacyRow(
                    generic_name="Zzqxv Elixir",
                    company="Planted",
                    status="Current",
                    initial_posting="2026-06-01",
                    update_date=None,
                ),
            ],
        )
        report = lead_time_report(conn, since="2026-01-01")
        assert report["listings_total"] >= 2
        assert report["listings_unmapped"] >= 1  # the elixir maps nowhere
        estradiol_cases = [
            case
            for case in report["cases"]
            if "ESTRADIOL" in case["drug"]
        ]
        assert estradiol_cases
        case = estradiol_cases[0]
        # By 2026-06 the fixture data already shows the pattern — the
        # replay must find it at (and before) the posting.
        assert case["fingerprints_at_posting"] >= 2
        assert case["lead_days"] > 0
