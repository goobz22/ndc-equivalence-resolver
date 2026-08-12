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
def loaded_conn(tmp_path_factory: pytest.TempPathFactory) -> Connection:
    """A database ingested once from the full fixture slice, shared
    read-only by resolve/explain/signal tests."""
    db_path = tmp_path_factory.mktemp("db") / "ndcres.db"
    conn = connect(db_path)
    refresh(conn, from_dir=FULL)
    return conn


@pytest.fixture()
def fresh_conn(tmp_path: Path) -> Connection:
    """A brand-new empty database for tests that mutate state."""
    return connect(tmp_path / "ndcres.db")
