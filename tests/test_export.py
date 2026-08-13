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
