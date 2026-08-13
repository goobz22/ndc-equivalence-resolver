"""SQLite store: schema, connection, provenance, refresh semantics.

Grain model (see the design review in the repo history):

- product grain = ``ndc9`` (labeler+product, zero-padded TEXT) — application
  number, strength, ingredients, TE linkage.
- package grain = ``ndc11`` (5-4-2 zero-padded TEXT, never INTEGER — leading
  zeros are data) — pack facts, NADAC, shortages.
- Orange Book grain = ``(appl_type, appl_no, product_no)``.

Refresh semantics:

- Mirror tables (product, package, ob_product, rx_*, shortage,
  product_ob_link) are replaced atomically per source. Upstream ABSENCE is
  a signal (discontinued brands vanish from the NDC Directory), so
  upsert-only refresh would accumulate ghosts.
- ``nadac`` is the exception: append/merge keyed on (ndc11,
  effective_date). The survey-dropout signal requires history that the
  weekly full-replacement files upstream do not replay.

Every row carries ``run_id`` → ``source_run`` (URL, hash, vintage), which
is how resolve/explain cite their sources.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_run (
  run_id          INTEGER PRIMARY KEY AUTOINCREMENT,
  source          TEXT NOT NULL,
  source_url      TEXT NOT NULL,
  fetched_at      TEXT NOT NULL,
  file_sha256     TEXT,
  dataset_vintage TEXT,
  row_count       INTEGER,
  status          TEXT NOT NULL DEFAULT 'ok'
);
CREATE INDEX IF NOT EXISTS idx_run_source ON source_run(source, fetched_at);

CREATE TABLE IF NOT EXISTS product (
  ndc9                TEXT PRIMARY KEY,
  product_ndc_filed   TEXT NOT NULL,
  product_type        TEXT,
  proprietary_name    TEXT,
  proprietary_suffix  TEXT,
  nonproprietary_name TEXT,
  dosage_form_raw     TEXT,
  route_raw           TEXT,
  marketing_category  TEXT,
  appl_type           TEXT,
  appl_no             TEXT,
  appl_no_raw         TEXT,
  labeler_name        TEXT,
  substance_raw       TEXT,
  ingredient_set      TEXT,
  ingredient_count    INTEGER NOT NULL DEFAULT 0,
  strength_numerator  TEXT,
  strength_unit       TEXT,
  strength_norm       TEXT,
  form_family         TEXT,
  dea_schedule        TEXT,
  start_marketing     TEXT,
  end_marketing       TEXT,
  ob_link_status      TEXT NOT NULL DEFAULT 'unlinked',
  run_id              INTEGER NOT NULL REFERENCES source_run(run_id)
);
CREATE INDEX IF NOT EXISTS idx_product_appl ON product(appl_type, appl_no);
CREATE INDEX IF NOT EXISTS idx_product_ingr ON product(ingredient_set, form_family);
CREATE INDEX IF NOT EXISTS idx_product_name ON product(proprietary_name);

CREATE TABLE IF NOT EXISTS package (
  ndc11             TEXT PRIMARY KEY,
  ndc9              TEXT NOT NULL,
  package_ndc_filed TEXT NOT NULL,
  ndc_shape         TEXT,
  package_descr_raw TEXT,
  pack_count        INTEGER,
  pack_unit         TEXT,
  wear_hours        REAL,
  sample_package    INTEGER NOT NULL DEFAULT 0,
  start_marketing   TEXT,
  end_marketing     TEXT,
  run_id            INTEGER NOT NULL REFERENCES source_run(run_id)
);
CREATE INDEX IF NOT EXISTS idx_package_ndc9 ON package(ndc9);

CREATE TABLE IF NOT EXISTS ob_product (
  appl_type      TEXT NOT NULL,
  appl_no        TEXT NOT NULL,
  product_no     TEXT NOT NULL,
  ingredient_raw TEXT NOT NULL,
  ingredient_set TEXT NOT NULL,
  df_route       TEXT NOT NULL,
  trade_name     TEXT,
  applicant      TEXT,
  applicant_full TEXT,
  strength_raw   TEXT,
  strength_norm  TEXT,
  te_code        TEXT,
  te_class       TEXT,
  te_subscript   TEXT,
  rld            INTEGER NOT NULL DEFAULT 0,
  rs             INTEGER NOT NULL DEFAULT 0,
  ob_type        TEXT NOT NULL,
  approval_date  TEXT,
  run_id         INTEGER NOT NULL REFERENCES source_run(run_id),
  PRIMARY KEY (appl_type, appl_no, product_no)
);
CREATE INDEX IF NOT EXISTS idx_ob_group
  ON ob_product(ingredient_set, df_route, strength_norm, te_code);
CREATE INDEX IF NOT EXISTS idx_ob_ingr ON ob_product(ingredient_set);

CREATE TABLE IF NOT EXISTS product_ob_link (
  ndc9         TEXT NOT NULL,
  appl_type    TEXT NOT NULL,
  appl_no      TEXT NOT NULL,
  product_no   TEXT NOT NULL,
  match_method TEXT NOT NULL,
  run_id       INTEGER NOT NULL REFERENCES source_run(run_id),
  PRIMARY KEY (ndc9, appl_type, appl_no, product_no)
);
CREATE INDEX IF NOT EXISTS idx_obl_ob ON product_ob_link(appl_type, appl_no, product_no);

CREATE TABLE IF NOT EXISTS rx_concept (
  rxcui  TEXT PRIMARY KEY,
  tty    TEXT NOT NULL,
  name   TEXT NOT NULL,
  run_id INTEGER NOT NULL REFERENCES source_run(run_id)
);

CREATE TABLE IF NOT EXISTS rx_rel (
  rxcui1 TEXT NOT NULL,
  rela   TEXT NOT NULL,
  rxcui2 TEXT NOT NULL,
  run_id INTEGER NOT NULL REFERENCES source_run(run_id),
  PRIMARY KEY (rxcui1, rela, rxcui2)
);
CREATE INDEX IF NOT EXISTS idx_rxrel_2 ON rx_rel(rxcui2, rela);

CREATE TABLE IF NOT EXISTS rx_ndc (
  ndc11  TEXT NOT NULL,
  rxcui  TEXT NOT NULL,
  run_id INTEGER NOT NULL REFERENCES source_run(run_id),
  PRIMARY KEY (ndc11, rxcui)
);
CREATE INDEX IF NOT EXISTS idx_rxndc_cui ON rx_ndc(rxcui);

CREATE TABLE IF NOT EXISTS nadac (
  ndc11             TEXT NOT NULL,
  effective_date    TEXT NOT NULL,
  price             REAL NOT NULL,
  pricing_unit      TEXT,
  description       TEXT,
  classification    TEXT,
  explanation_codes TEXT,
  as_of_first       TEXT NOT NULL,
  as_of_last        TEXT NOT NULL,
  run_id            INTEGER NOT NULL REFERENCES source_run(run_id),
  PRIMARY KEY (ndc11, effective_date)
);
CREATE INDEX IF NOT EXISTS idx_nadac_seen ON nadac(ndc11, as_of_last DESC);

CREATE TABLE IF NOT EXISTS shortage (
  record_hash     TEXT PRIMARY KEY,
  ndc11           TEXT,
  ndc9            TEXT,
  generic_name    TEXT,
  company_name    TEXT,
  status          TEXT,
  availability    TEXT,
  shortage_reason TEXT,
  initial_posting TEXT,
  update_date     TEXT,
  raw_json        TEXT NOT NULL,
  run_id          INTEGER NOT NULL REFERENCES source_run(run_id)
);
CREATE INDEX IF NOT EXISTS idx_shortage_ndc11 ON shortage(ndc11);
CREATE INDEX IF NOT EXISTS idx_shortage_ndc9 ON shortage(ndc9);

CREATE TABLE IF NOT EXISTS sdud (
  ndc11         TEXT NOT NULL,
  year          INTEGER NOT NULL,
  quarter       INTEGER NOT NULL,
  units         REAL NOT NULL DEFAULT 0,
  prescriptions REAL NOT NULL DEFAULT 0,
  state_rows    INTEGER NOT NULL DEFAULT 0,
  run_id        INTEGER NOT NULL REFERENCES source_run(run_id),
  PRIMARY KEY (ndc11, year, quarter)
);

CREATE TABLE IF NOT EXISTS enforcement (
  record_hash        TEXT PRIMARY KEY,
  ndc9               TEXT,
  product_ndcs       TEXT,
  classification     TEXT,
  status             TEXT,
  recall_initiation  TEXT,
  product_description TEXT,
  reason             TEXT,
  run_id             INTEGER NOT NULL REFERENCES source_run(run_id)
);
CREATE INDEX IF NOT EXISTS idx_enforcement_ndc9 ON enforcement(ndc9);

CREATE TABLE IF NOT EXISTS special_case (
  scope           TEXT NOT NULL,
  key             TEXT NOT NULL,
  field           TEXT NOT NULL,
  raw_value       TEXT,
  corrected_value TEXT,
  reason          TEXT NOT NULL,
  citation        TEXT,
  PRIMARY KEY (scope, key, field)
);

CREATE TABLE IF NOT EXISTS product_derived (
  ndc9       TEXT NOT NULL,
  attr       TEXT NOT NULL,
  value      TEXT,
  confidence TEXT,
  conflict   INTEGER NOT NULL DEFAULT 0,
  evidence   TEXT NOT NULL,
  run_id     INTEGER NOT NULL REFERENCES source_run(run_id),
  PRIMARY KEY (ndc9, attr)
);

-- Derived per-product search support (SPEC §8): best RxNorm concept
-- name, TE code, marketed flag, NADAC presence, representative package.
-- Rebuilt after every refresh (a derived mirror, like product_ob_link);
-- ships in the web export so /api/search serves from it.
-- No FK to product: search_doc is rebuilt-from-product after refresh
-- (integrity by construction), and an FK would block the mirror-replace
-- DELETE of product on the next refresh — same reason product_ob_link
-- carries none.
CREATE TABLE IF NOT EXISTS search_doc (
  ndc9          TEXT PRIMARY KEY,
  rx_name       TEXT,
  te_code       TEXT,
  marketed      INTEGER NOT NULL DEFAULT 0,
  has_nadac     INTEGER NOT NULL DEFAULT 0,
  rep_ndc11     TEXT,
  package_count INTEGER NOT NULL DEFAULT 0,
  run_id        INTEGER NOT NULL REFERENCES source_run(run_id)
);
"""

# Curated upstream-data corrections. Each row is applied at ingest (the
# corrected value lands in the main column, the verbatim value in the
# *_raw column) and surfaced by explain as a 'special-cased' badge.
SPECIAL_CASES: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    (
        "product",
        "504190455",  # Menostar, Bayer
        "appl_no",
        "020375",
        "021674",
        "NDC Directory files Menostar under Climara's NDA020375; the Orange "
        "Book lists Menostar under N021674. Joining on the raw value would "
        "wrongly place Menostar in Climara's AB2 group.",
        "verified against both live datasets 2026-08-12",
    ),
)

# The tables owned by each source, replaced atomically on refresh.
# nadac is deliberately absent — it merges, never replaces.
MIRROR_TABLES: dict[str, tuple[str, ...]] = {
    "ndc": ("product", "package"),
    "orangebook": ("ob_product",),
    "rxnorm": ("rx_concept", "rx_rel", "rx_ndc"),
    "shortage": ("shortage",),
    "sdud": ("sdud",),
    "enforcement": ("enforcement",),
    "link": ("product_ob_link",),
    "search": ("search_doc",),
}


def default_db_path() -> Path:
    env = os.environ.get("NDCRES_DB")
    if env:
        return Path(env)
    return Path.home() / ".ndcres" / "ndcres.db"


def connect_readonly(
    path: str | Path | None = None, *, immutable: bool = False
) -> sqlite3.Connection:
    """Open an EXISTING database for serving — never writes, never creates.

    The read-write connect() below cannot even open on a read-only
    filesystem (it mkdirs, forces WAL — which needs -wal/-shm sidecars —
    and runs DDL), and serverless hosts mount the bundle read-only.

    immutable=True additionally disables all SQLite locking and change
    detection. That is correct ONLY when nothing can write the file while
    it is open: the serverless bundle (guaranteed read-only) or an
    atomically-replaced export artifact. Never use it on a database a
    concurrent refresh writes in place.
    """
    db_path = Path(path) if path is not None else default_db_path()
    if not db_path.exists():
        raise FileNotFoundError(f"ndcres database not found: {db_path}")
    query = "mode=ro&immutable=1" if immutable else "mode=ro"
    conn = sqlite3.connect(f"{db_path.resolve().as_uri()}?{query}", uri=True)
    conn.row_factory = sqlite3.Row
    # Belt over the ro open: any write attempt errors instead of relying
    # on filesystem permissions.
    conn.execute("PRAGMA query_only = ON")
    conn.execute("PRAGMA cache_size = -65536")  # 64MB
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA mmap_size = 268435456")  # 256MB
    return conn


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the ndcres database."""
    db_path = Path(path) if path is not None else default_db_path()
    if db_path != Path(":memory:"):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    # Pre-release schema shim: the first cut of search_doc carried an FK
    # to product, which blocks the mirror-replace DELETE on the next
    # refresh. CREATE IF NOT EXISTS cannot fix an existing table, so drop
    # the bad shape here; the DDL below recreates it and the next refresh
    # repopulates (a derived table — nothing is lost).
    legacy = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='search_doc'"
    ).fetchone()
    if legacy and "REFERENCES product" in (legacy["sql"] or ""):
        conn.execute("DROP TABLE search_doc")
    # Read-heavy workload over a few hundred MB: a generous page cache and
    # memory-mapped reads keep the resolve path off the disk.
    conn.execute("PRAGMA cache_size = -65536")  # 64MB
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA mmap_size = 268435456")  # 256MB
    conn.executescript(_DDL)
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    for row in SPECIAL_CASES:
        conn.execute(
            "INSERT OR REPLACE INTO special_case "
            "(scope, key, field, raw_value, corrected_value, reason, citation) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            row,
        )
    conn.commit()
    return conn


def start_run(
    conn: sqlite3.Connection,
    *,
    source: str,
    source_url: str,
    fetched_at: str,
    file_sha256: str | None = None,
    dataset_vintage: str | None = None,
) -> int:
    """Record the start of a source refresh; returns the run_id."""
    cursor = conn.execute(
        "INSERT INTO source_run "
        "(source, source_url, fetched_at, file_sha256, dataset_vintage) "
        "VALUES (?, ?, ?, ?, ?)",
        (source, source_url, fetched_at, file_sha256, dataset_vintage),
    )
    run_id = cursor.lastrowid
    assert run_id is not None
    return run_id


def finish_run(conn: sqlite3.Connection, run_id: int, *, row_count: int) -> None:
    conn.execute(
        "UPDATE source_run SET row_count = ?, status = 'ok' WHERE run_id = ?",
        (row_count, run_id),
    )


def clear_mirror_tables(conn: sqlite3.Connection, source: str) -> None:
    """Atomic-replace step: drop the source's mirrored rows.

    Must be called inside the same transaction as the re-insert so a
    failed refresh never leaves the store half-empty.
    """
    for table in MIRROR_TABLES[source]:
        conn.execute(f"DELETE FROM {table}")  # noqa: S608 - table names are ours


def special_case_value(
    conn: sqlite3.Connection, scope: str, key: str, field: str, raw_value: str | None
) -> tuple[str | None, bool]:
    """Return (possibly corrected value, was_corrected) for a field."""
    row = conn.execute(
        "SELECT raw_value, corrected_value FROM special_case "
        "WHERE scope = ? AND key = ? AND field = ?",
        (scope, key, field),
    ).fetchone()
    if row is None:
        return raw_value, False
    if raw_value is not None and row["raw_value"] is not None and raw_value != row["raw_value"]:
        # Upstream changed since the correction was recorded — do not
        # apply a stale fix; surface the raw value instead.
        return raw_value, False
    return row["corrected_value"], True
