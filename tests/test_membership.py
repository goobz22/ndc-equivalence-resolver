"""Directory-membership snapshots (SPEC §10.3).

The load-bearing pin: a vanished NDC's delta row carries its LAST-SIGHT
state (marketing status, OB type, class key) — the current database no
longer holds the row, so reading current state would find nothing. The
mutation fixture (ndc_v2 removes Evamist entirely) is the planted case.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from conftest import FULL, NDC_V2

from ndcres.db import connect
from ndcres.ingest import refresh
from ndcres.membership import (
    copy_recent_deltas,
    membership_snapshot_count,
    snapshot_membership,
)

EVAMIST_NDC9 = "005742067"


def _set_ndc_fetch_date(conn: sqlite3.Connection, day: str) -> None:
    """Simulate a later weekly run: snapshot dates are dataset-relative
    (the ndc source_run fetch date), and both fixture refreshes happen
    on the same wall-clock day in tests."""
    conn.execute(
        "UPDATE source_run SET fetched_at = ? WHERE run_id = "
        "(SELECT max(run_id) FROM source_run WHERE source = 'ndc')",
        (f"{day}T00:00:00Z",),
    )
    conn.commit()


@pytest.fixture()
def week_one(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "main.db")
    refresh(conn, from_dir=FULL)
    _set_ndc_fetch_date(conn, "2026-08-01")
    return conn


class TestBaseline:
    def test_first_run_is_baseline_with_no_delta_rows(
        self, week_one: sqlite3.Connection, tmp_path: Path
    ) -> None:
        history = connect(tmp_path / "hist.db")
        snapshot = snapshot_membership(week_one, history)
        assert snapshot.is_baseline
        assert snapshot.appeared == 0 and snapshot.vanished == 0
        assert snapshot.present > 0
        deltas = history.execute(
            "SELECT count(*) FROM ndc_membership_delta"
        ).fetchone()[0]
        assert deltas == 0
        state = history.execute(
            "SELECT count(*) FROM ndc_membership_state"
        ).fetchone()[0]
        assert state == snapshot.present

    def test_state_carries_class_keys_for_te_rated_members(
        self, week_one: sqlite3.Connection, tmp_path: Path
    ) -> None:
        history = connect(tmp_path / "hist.db")
        snapshot_membership(week_one, history)
        anchor = history.execute(
            "SELECT * FROM ndc_membership_state WHERE ndc11 = '00378464226'"
        ).fetchone()
        assert anchor is not None
        assert anchor["ingredient_set"] == "ESTRADIOL"
        assert anchor["te_code"] == "AB1"
        assert anchor["ob_type"] == "RX"

    def test_no_ndc_ingest_refuses_loudly(self, tmp_path: Path) -> None:
        empty = connect(tmp_path / "empty.db")
        history = connect(tmp_path / "hist.db")
        with pytest.raises(RuntimeError, match="refresh first"):
            snapshot_membership(empty, history)


class TestDeltas:
    def _two_weeks(
        self, week_one: sqlite3.Connection, tmp_path: Path
    ) -> tuple[sqlite3.Connection, sqlite3.Connection, dict[str, str | None]]:
        history = connect(tmp_path / "hist.db")
        snapshot_membership(week_one, history)
        # Capture Evamist's state BEFORE it vanishes — the whole point.
        prior = {
            row["ndc11"]: row["ob_type"]
            for row in history.execute(
                "SELECT ndc11, ob_type FROM ndc_membership_state "
                "WHERE ndc11 LIKE ? || '%'",
                (EVAMIST_NDC9,),
            )
        }
        assert prior, "Evamist packages missing from the baseline state"
        refresh(week_one, sources=("ndc",), from_dir=NDC_V2)
        _set_ndc_fetch_date(week_one, "2026-08-08")
        return week_one, history, prior

    def test_vanished_row_carries_prior_state(
        self, week_one: sqlite3.Connection, tmp_path: Path
    ) -> None:
        conn, history, prior = self._two_weeks(week_one, tmp_path)
        snapshot = snapshot_membership(conn, history)
        assert not snapshot.is_baseline
        assert snapshot.vanished >= len(prior)
        for ndc11, ob_type in prior.items():
            row = history.execute(
                "SELECT * FROM ndc_membership_delta "
                "WHERE ndc11 = ? AND change = 'vanished'",
                (ndc11,),
            ).fetchone()
            assert row is not None, f"{ndc11} vanish not recorded"
            # The current db has NO row for this NDC anymore — the delta
            # could only have been stamped from the state table.
            assert row["last_ob_type"] == ob_type
            gone = conn.execute(
                "SELECT count(*) FROM package WHERE ndc11 = ?", (ndc11,)
            ).fetchone()[0]
            assert gone == 0
        # State no longer holds the vanished rows.
        remaining = history.execute(
            "SELECT count(*) FROM ndc_membership_state WHERE ndc11 LIKE ? || '%'",
            (EVAMIST_NDC9,),
        ).fetchone()[0]
        assert remaining == 0

    def test_same_snapshot_date_is_idempotent(
        self, week_one: sqlite3.Connection, tmp_path: Path
    ) -> None:
        conn, history, _ = self._two_weeks(week_one, tmp_path)
        first = snapshot_membership(conn, history)
        deltas_before = history.execute(
            "SELECT count(*) FROM ndc_membership_delta"
        ).fetchone()[0]
        second = snapshot_membership(conn, history)
        assert second == first
        deltas_after = history.execute(
            "SELECT count(*) FROM ndc_membership_delta"
        ).fetchone()[0]
        assert deltas_after == deltas_before
        assert membership_snapshot_count(history) == 2

    def test_deltas_copy_into_the_main_db_within_window(
        self, week_one: sqlite3.Connection, tmp_path: Path
    ) -> None:
        conn, history, _ = self._two_weeks(week_one, tmp_path)
        snapshot_membership(conn, history)
        fresh_main = connect(tmp_path / "fresh.db")
        copied = copy_recent_deltas(history, fresh_main)
        assert copied > 0
        runs = fresh_main.execute(
            "SELECT count(*) FROM ndc_membership_run"
        ).fetchone()[0]
        assert runs == 2  # baseline + delta run rows both within window
        # Idempotent re-copy.
        assert copy_recent_deltas(history, fresh_main) == copied
        local_deltas = fresh_main.execute(
            "SELECT count(*) FROM ndc_membership_delta"
        ).fetchone()[0]
        assert local_deltas == copied

    def test_empty_history_copies_nothing(self, tmp_path: Path) -> None:
        history = connect(tmp_path / "hist.db")
        main = connect(tmp_path / "main.db")
        assert copy_recent_deltas(history, main) == 0
