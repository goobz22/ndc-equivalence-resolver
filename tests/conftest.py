"""Shared fixtures: an in-memory (well, tmp) store loaded from the slices."""

from pathlib import Path
from sqlite3 import Connection

import pytest

from ndcres.db import connect
from ndcres.ingest import refresh

FIXTURES = Path(__file__).parent / "fixtures"
FULL = FIXTURES / "full"
NDC_V2 = FIXTURES / "ndc_v2"


@pytest.fixture(scope="session")
def loaded_db_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Path of a database ingested once from the full fixture slice."""
    db_path = tmp_path_factory.mktemp("db") / "ndcres.db"
    conn = connect(db_path)
    refresh(conn, from_dir=FULL)
    conn.close()
    return db_path


@pytest.fixture(scope="session")
def loaded_conn(loaded_db_path: Path) -> Connection:
    """A shared read-only connection to the fixture database."""
    return connect(loaded_db_path)


@pytest.fixture()
def fresh_conn(tmp_path: Path) -> Connection:
    """A brand-new empty database for tests that mutate state."""
    return connect(tmp_path / "ndcres.db")
