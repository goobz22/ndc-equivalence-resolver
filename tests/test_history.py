"""Forward archive (SPEC §10.2): append-only, integrity-guarded.

The archive is the only copy of data no upstream source will replay
(weekly sweep verdicts + FDA-list snapshots), so every failure mode
here must REFUSE loudly rather than risk a clobber-upload of a damaged
or regressed file.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ndcres.db import connect
from ndcres.history import (
    append_sweep_to_history,
    normalize_drug_name,
    open_history,
    snapshot_fda_list,
)
from ndcres.ingest import refresh
from ndcres.sweep import persist_sweep, run_sweep

FIXTURES = Path(__file__).parent / "fixtures" / "full"


@pytest.fixture()
def main_conn(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "main.db")
    refresh(conn, from_dir=FIXTURES)
    return conn


class TestFdaListSnapshot:
    def test_snapshot_records_current_list(
        self, main_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        history = open_history(tmp_path / "hist.db")
        new_rows = snapshot_fda_list(main_conn, history)
        assert new_rows > 0
        stored = history.execute(
            "SELECT count(*) FROM fda_list_history"
        ).fetchone()[0]
        assert stored == new_rows

    def test_same_snapshot_date_dedupes(
        self, main_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        history = open_history(tmp_path / "hist.db")
        first = snapshot_fda_list(main_conn, history)
        second = snapshot_fda_list(main_conn, history)
        assert first > 0 and second == 0

    def test_snapshot_date_is_dataset_relative(
        self, main_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        history = open_history(tmp_path / "hist.db")
        snapshot_fda_list(main_conn, history)
        snap_date = history.execute(
            "SELECT DISTINCT snapshot_date FROM fda_list_history"
        ).fetchall()
        fetch_date = main_conn.execute(
            "SELECT max(fetched_at) AS f FROM source_run WHERE source='shortage'"
        ).fetchone()["f"][:10]
        assert [row["snapshot_date"] for row in snap_date] == [fetch_date]

    def test_no_shortage_ingest_fails_loudly(self, tmp_path: Path) -> None:
        empty = connect(tmp_path / "empty.db")
        history = open_history(tmp_path / "hist.db")
        with pytest.raises(RuntimeError, match="refresh first"):
            snapshot_fda_list(empty, history)

    def test_snapshot_into_the_main_db_itself_works(
        self, main_conn: sqlite3.Connection
    ) -> None:
        # The CLI records locally by passing the same connection twice.
        assert snapshot_fda_list(main_conn, main_conn) > 0

    def test_name_normalization(self) -> None:
        assert normalize_drug_name("  Estradiol   Transdermal\tSystem ") == (
            "ESTRADIOL TRANSDERMAL SYSTEM"
        )


class TestSweepArchive:
    def test_appends_assign_fresh_ids(
        self, main_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        history = open_history(tmp_path / "hist.db")
        sweep_id = persist_sweep(main_conn, run_sweep(main_conn))
        first = append_sweep_to_history(main_conn, history, sweep_id)
        # A second runner's db would restart ids at 1 — the archive must
        # keep both runs distinct regardless.
        second = append_sweep_to_history(main_conn, history, sweep_id)
        assert second == first + 1
        runs = history.execute("SELECT count(*) FROM sweep_run").fetchone()[0]
        assert runs == 2
        rows = history.execute(
            "SELECT sweep_id, count(*) AS n FROM sweep_class GROUP BY sweep_id"
        ).fetchall()
        assert len(rows) == 2 and rows[0]["n"] == rows[1]["n"] > 0

    def test_missing_sweep_refuses(
        self, main_conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        history = open_history(tmp_path / "hist.db")
        with pytest.raises(RuntimeError, match="no sweep_run"):
            append_sweep_to_history(main_conn, history, 999)

    def test_corrupt_archive_refuses_at_open(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.db"
        good = connect(bad)
        good.close()
        # Damage the file: overwrite a page in the middle.
        data = bytearray(bad.read_bytes())
        if len(data) > 5000:
            data[4096:4200] = b"\x00" * 104
        bad.write_bytes(bytes(data))
        with pytest.raises((RuntimeError, sqlite3.DatabaseError)):
            open_history(bad)


class TestSchemaShim:
    def test_old_archive_gains_columns_via_shim(self, tmp_path: Path) -> None:
        # A pre-5-axis archive (sweep_class without the new columns)
        # must gain them on open, with old rows honestly NULL.
        import sqlite3 as raw_sqlite

        old = tmp_path / "old.db"
        bare = raw_sqlite.connect(old)
        bare.executescript(
            """
            CREATE TABLE sweep_run (
              sweep_id INTEGER PRIMARY KEY AUTOINCREMENT, run_date TEXT NOT NULL,
              started_at TEXT NOT NULL, nadac_horizon TEXT,
              class_count INTEGER NOT NULL, fda_listed_count INTEGER NOT NULL,
              constraint_count INTEGER NOT NULL, mixed_count INTEGER NOT NULL,
              quiet_count INTEGER NOT NULL, elapsed_seconds REAL NOT NULL,
              code_version TEXT NOT NULL
            );
            CREATE TABLE sweep_class (
              sweep_id INTEGER NOT NULL, ingredient_set TEXT NOT NULL,
              df_route TEXT NOT NULL, strength_norm TEXT NOT NULL,
              te_code TEXT NOT NULL, rep_ndc11 TEXT NOT NULL,
              member_count INTEGER NOT NULL, marketed_count INTEGER NOT NULL,
              surveyed_count INTEGER NOT NULL, fda_listed_members INTEGER NOT NULL,
              drift_pct REAL, drift_fired INTEGER NOT NULL,
              dropout_members INTEGER NOT NULL, dropout_ratio REAL,
              volume_change_pct REAL, volume_quarter TEXT,
              recalls INTEGER NOT NULL, fingerprints INTEGER NOT NULL,
              verdict TEXT NOT NULL,
              PRIMARY KEY (sweep_id, ingredient_set, df_route, strength_norm, te_code)
            );
            INSERT INTO sweep_run VALUES (1, '2026-08-01', 'x', NULL, 1, 0, 1, 0, 0, 1.0, '0.1.0');
            INSERT INTO sweep_class VALUES (1, 'ESTRADIOL', 'SYSTEM;TRANSDERMAL',
              'UG24H:50', 'AB1', '00378464226', 5, 5, 5, 0, 0.2, 1, 0, 0.0,
              0.7, '2026Q1', 2, 3, 'evidence-consistent-with-supply-constraint');
            """
        )
        bare.commit()
        bare.close()
        conn = open_history(old)
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(sweep_class)")
        }
        assert {"discontinued_members", "directory_exits",
                "directory_exit_fired"} <= columns
        row = conn.execute("SELECT * FROM sweep_class").fetchone()
        assert row["discontinued_members"] is None  # honest: never measured
        assert row["verdict"] == "evidence-consistent-with-supply-constraint"
