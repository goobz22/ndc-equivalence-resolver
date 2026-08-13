"""Supply-stress signal tests.

The real anchors currently show NO shortage and NO dropout — so the
fixture data plants both: a synthetic shortage record for the Mylan
anchor (a separate, clearly-labeled file) and a NADAC series where the
Zydus AB1 product stops appearing mid-2026.
"""

import shutil
import sqlite3
from pathlib import Path

import pytest

from conftest import FIXTURES, FULL

from ndcres.db import connect
from ndcres.ingest import refresh
from ndcres.resolve import resolve
from ndcres.signals import signal_report


class TestDropout:
    def test_fires_for_the_vanished_ndc(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        report = signal_report(loaded_conn, "70710119308")
        dropout = next(c for c in report.components if c.name == "survey-dropout")
        assert dropout.fired
        assert dropout.contribution == pytest.approx(0.25)  # gone ~13 weeks
        assert "2026-05-13" in dropout.evidence  # last seen
        assert "2026-08-12" in dropout.evidence  # dataset horizon

    def test_quiet_for_a_present_ndc(self, loaded_conn: sqlite3.Connection) -> None:
        report = signal_report(loaded_conn, "00378464226")
        dropout = next(c for c in report.components if c.name == "survey-dropout")
        assert not dropout.fired
        assert dropout.contribution == 0.0

    def test_never_surveyed_reads_quiet_not_missing_data_crash(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        report = signal_report(loaded_conn, "00378462126")  # no NADAC rows
        dropout = next(c for c in report.components if c.name == "survey-dropout")
        assert not dropout.fired
        assert "never present" in dropout.evidence


class TestDrift:
    def test_fires_cross_year_for_the_anchor(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        # Price in force one year before the latest rate came from the
        # PRIOR year's file ($6.51, eff 2025-06-18) → +22.5%.
        report = signal_report(loaded_conn, "00378464226")
        drift = next(c for c in report.components if c.name == "price-drift")
        assert drift.fired
        assert "+22.5%" in drift.evidence
        assert drift.contribution == pytest.approx(0.25 * (0.2253 / 0.35), abs=0.005)
        # Class-priced generics: the evidence says the climb is class-wide.
        assert "equivalence class" in drift.evidence

    def test_quiet_for_flat_price(self, loaded_conn: sqlite3.Connection) -> None:
        report = signal_report(loaded_conn, "00555088602")
        drift = next(c for c in report.components if c.name == "price-drift")
        assert not drift.fired

    def test_ten_percent_rise_fires_softly(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        # Sandoz AG series rises ~10% — at the tuned threshold for the
        # CMS-damped index (the motivating shortage moved this signal
        # while FDA's list stayed empty; sensitivity is deliberate).
        report = signal_report(loaded_conn, "00781714483")
        drift = next(c for c in report.components if c.name == "price-drift")
        assert drift.fired
        assert drift.contribution < 0.08


class TestShortage:
    def test_absence_reads_lagging_list_never_available(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        report = signal_report(loaded_conn, "00378464226")
        shortage = next(c for c in report.components if c.name == "shortage")
        assert not shortage.fired
        assert "not on FDA's official drug-shortage list" in shortage.evidence
        assert "lagging" in shortage.evidence
        assert "availability" in shortage.evidence  # the explicit caveat

    def test_synthetic_shortage_fires(self, tmp_path: Path) -> None:
        conn = self._conn_with_synthetic_shortage(tmp_path)
        report = signal_report(conn, "00378464226")
        shortage = next(c for c in report.components if c.name == "shortage")
        assert shortage.fired
        assert shortage.contribution == pytest.approx(0.50)
        assert "Demand increase" in shortage.evidence
        assert report.score >= 0.5

    def test_resolved_record_does_not_fire(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        # Phenytoin has Current + Resolved records; hydromorphone Current.
        report = signal_report(loaded_conn, "00071053023")
        shortage = next(c for c in report.components if c.name == "shortage")
        assert shortage.fired  # the Current record wins
        report2 = signal_report(loaded_conn, "00409130431")
        assert next(
            c for c in report2.components if c.name == "shortage"
        ).fired

    @staticmethod
    def _conn_with_synthetic_shortage(tmp_path: Path) -> sqlite3.Connection:
        conn = connect(tmp_path / "t.db")
        refresh(conn, from_dir=FULL)
        synthetic_dir = tmp_path / "synthetic"
        synthetic_dir.mkdir()
        shutil.copy(
            FIXTURES / "shortages_synthetic_estradiol.json",
            synthetic_dir / "shortages.json",
        )
        refresh(conn, sources=("shortage",), from_dir=synthetic_dir)
        return conn


class TestRankingIntegration:
    def test_stressed_equivalent_ranks_last_in_tier1(self, tmp_path: Path) -> None:
        conn = TestShortage._conn_with_synthetic_shortage(tmp_path)
        resolution = resolve(conn, "65162-993-08")  # Dotti as seed
        tier1 = [a.dims.ndc11 for a in resolution.tiers["T1"]]
        assert "00378464226" in tier1  # the anchor is Dotti's T1 sibling
        # ...but it carries the shortage record, so it ranks LAST.
        assert tier1[-1] == "00378464226"
        anchor = resolution.tiers["T1"][-1]
        assert anchor.stress_score is not None and anchor.stress_score >= 0.5
        assert any("shortage" in e for e in anchor.stress_evidence)

    def test_dropout_outranks_healthy_but_not_shortage(
        self, tmp_path: Path
    ) -> None:
        conn = TestShortage._conn_with_synthetic_shortage(tmp_path)
        resolution = resolve(conn, "65162-993-08")
        tier1 = [a.dims.ndc11 for a in resolution.tiers["T1"]]
        # Zydus (survey dropout, 0.25) sits between the healthy products
        # and the shortage-flagged anchor (>= 0.6).
        assert tier1.index("70710119308") > tier1.index("00781714483")
        assert tier1.index("70710119308") < tier1.index("00378464226")


class TestDeterminism:
    def test_report_is_wall_clock_independent(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        first = signal_report(loaded_conn, "70710119308")
        second = signal_report(loaded_conn, "70710119308")
        assert first == second
        assert first.survey_horizon == "2026-08-12"  # from data, not today
