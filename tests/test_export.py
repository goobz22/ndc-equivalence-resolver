"""The web export artifact must serve from a read-only filesystem.

Serverless hosts mount the function bundle read-only. That imposes two
contracts, each pinned here because each was violated in production
(ndcres-api attempt 4, 2026-08-13 — every request 500'd with "unable to
open database file"):

  1. The ARTIFACT ships in rollback-journal mode. connect() creates
     databases in WAL mode and the flag persists in the file header; a
     WAL database cannot be opened read-only-filesystem because readers
     must create the -shm sidecar.
  2. The SERVING path opens read-only (connect_readonly) — the
     read-write connect() mkdirs, forces WAL, and runs DDL, none of
     which can happen on a read-only mount.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ndcres.db import connect_readonly
from ndcres.export import export_web_db


@pytest.fixture(scope="module")
def web_db_path(loaded_db_path: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    dest = tmp_path_factory.mktemp("export") / "web.db"
    export_web_db(loaded_db_path, dest)
    return dest


class TestArtifactReadOnlyContract:
    def test_artifact_is_rollback_journal_not_wal(self, web_db_path: Path) -> None:
        # File-format header, bytes 18-19: 1,1 = rollback journal,
        # 2,2 = WAL. https://www.sqlite.org/fileformat.html
        header = web_db_path.read_bytes()[18:20]
        assert header == b"\x01\x01", (
            f"web.db header journal bytes are {header!r} — a WAL-flagged "
            "artifact cannot be opened on a read-only filesystem"
        )

    def test_readonly_open_serves_rows(self, web_db_path: Path) -> None:
        conn = connect_readonly(web_db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM product").fetchone()[0]
            assert count > 0
        finally:
            conn.close()

    def test_immutable_open_serves_rows(self, web_db_path: Path) -> None:
        conn = connect_readonly(web_db_path, immutable=True)
        try:
            count = conn.execute("SELECT COUNT(*) FROM package").fetchone()[0]
            assert count > 0
        finally:
            conn.close()

    def test_readonly_blocks_writes(self, web_db_path: Path) -> None:
        conn = connect_readonly(web_db_path)
        try:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute("INSERT INTO meta (key, value) VALUES ('x', 'y')")
        finally:
            conn.close()

    def test_missing_database_fails_loudly(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            connect_readonly(tmp_path / "nope.db")


class TestSweepInTheExport:
    def test_export_ships_exactly_the_latest_sweep(
        self, loaded_db_path: Path, tmp_path: Path
    ) -> None:
        import shutil

        from ndcres.db import connect
        from ndcres.sweep import persist_sweep, run_sweep

        # Work on a copy — the session fixture db stays pristine.
        db_copy = tmp_path / "full.db"
        shutil.copy(loaded_db_path, db_copy)
        loaded_db_path = db_copy
        source = connect(loaded_db_path)
        first = persist_sweep(source, run_sweep(source))
        second = persist_sweep(source, run_sweep(source))
        assert second > first
        source.close()
        dest = tmp_path / "web.db"
        export_web_db(loaded_db_path, dest)
        web = connect_readonly(dest)
        try:
            runs = web.execute(
                "SELECT sweep_id FROM sweep_run"
            ).fetchall()
            assert [row["sweep_id"] for row in runs] == [second]
            classes = web.execute(
                "SELECT count(DISTINCT sweep_id) FROM sweep_class"
            ).fetchone()[0]
            assert classes == 1
        finally:
            web.close()


class TestSizeGate:
    def test_size_gate_refuses_oversized_artifact(
        self, loaded_db_path: Path, tmp_path: Path
    ) -> None:
        # INV-16.2 (closes the Phase-0 audit's OPEN row): a planted
        # 1KB gate must refuse the real artifact AND remove the
        # oversized file.
        from ndcres.export import export_web_db

        dest = tmp_path / "web.db"
        with pytest.raises(RuntimeError, match="over the"):
            export_web_db(loaded_db_path, dest, size_gate=1024)
        assert not dest.exists()


class TestMembershipWindowExport:
    def test_membership_tables_ship(
        self, loaded_db_path: Path, tmp_path: Path
    ) -> None:
        import shutil

        from ndcres.db import connect
        from ndcres.export import export_web_db

        db_copy = tmp_path / "full.db"
        shutil.copy(loaded_db_path, db_copy)
        conn = connect(db_copy)
        with conn:
            conn.execute(
                "INSERT INTO ndc_membership_run (snapshot_date, present_count,"
                " appeared_count, vanished_count, is_baseline)"
                " VALUES ('2026-08-01', 10, 0, 0, 1)"
            )
            conn.execute(
                "INSERT INTO ndc_membership_delta (snapshot_date, ndc11,"
                " change, last_ob_type) VALUES"
                " ('2026-08-08', '00000000001', 'vanished', 'RX')"
            )
        conn.close()
        dest = tmp_path / "web.db"
        export_web_db(db_copy, dest)
        web = connect_readonly(dest)
        try:
            runs = web.execute(
                "SELECT count(*) FROM ndc_membership_run"
            ).fetchone()[0]
            deltas = web.execute(
                "SELECT count(*) FROM ndc_membership_delta"
            ).fetchone()[0]
            assert runs == 1 and deltas == 1
        finally:
            web.close()
