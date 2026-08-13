"""Forward archive (SPEC §10.2): the record the FDA list doesn't keep.

FDA deletes resolved shortage records instead of keeping history —
HHS/ASPE had to reconstruct the list's past from Wayback Machine
snapshots. This module accumulates that record going forward, in two
append-only tables:

  fda_list_history — what the FDA list said, week by week, derived from
    the openFDA bulk ALREADY ingested (vintage-stamped; no second fetch,
    no second parser to drift).
  sweep_run / sweep_class — what the independent evidence said about
    every equivalence class, week by week (sweep.py).

Both live in the main database AND in a small durable `ndcres-history.db`
that the weekly pipeline downloads from the rolling release, appends to,
and re-uploads — because the pipeline's main database is rebuilt from
sources on a fresh runner every week, and sweep verdicts + list
snapshots are exactly the data no upstream source will ever replay.

Every append is integrity-guarded: a damaged or regressive archive
raises instead of being clobber-uploaded.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .db import connect

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_drug_name(name: str) -> str:
    return _WHITESPACE_RE.sub(" ", name.strip()).upper()


def _latest_shortage_fetch_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT max(fetched_at) AS f FROM source_run "
        "WHERE source = 'shortage' AND status = 'ok'"
    ).fetchone()
    return row["f"][:10] if row and row["f"] else None


def snapshot_fda_list(
    conn: sqlite3.Connection,
    history_conn: sqlite3.Connection,
    *,
    snapshot_source: str = "openfda-weekly",
) -> int:
    """Record the current FDA-list state into the history table.

    The snapshot date is the shortage source_run's fetch date (dataset-
    relative, never the wall clock), and the PRIMARY KEY dedupes re-runs
    of the same snapshot. Returns the number of NEW rows recorded.
    """
    snapshot_date = _latest_shortage_fetch_date(conn)
    if snapshot_date is None:
        raise RuntimeError(
            "no successful shortage ingest to snapshot — refresh first"
        )
    rows = conn.execute(
        """
        SELECT generic_name, coalesce(company_name, '') AS company,
               coalesce(status, '') AS status,
               min(initial_posting) AS initial_posting,
               max(update_date) AS update_date
        FROM shortage
        WHERE generic_name IS NOT NULL
        GROUP BY generic_name, company, status
        """
    ).fetchall()
    before = history_conn.execute(
        "SELECT count(*) FROM fda_list_history"
    ).fetchone()[0]
    with history_conn:
        history_conn.executemany(
            """
            INSERT OR IGNORE INTO fda_list_history
              (snapshot_date, snapshot_source, drug_name_raw, drug_name_norm,
               company, status, initial_posting, update_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot_date,
                    snapshot_source,
                    row["generic_name"],
                    normalize_drug_name(row["generic_name"]),
                    row["company"],
                    row["status"],
                    row["initial_posting"],
                    row["update_date"],
                )
                for row in rows
            ],
        )
    after = history_conn.execute(
        "SELECT count(*) FROM fda_list_history"
    ).fetchone()[0]
    return int(after - before)


def open_history(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) the durable archive and verify it.

    A damaged archive must fail HERE — before anything appends to it and
    long before a clobber-upload could destroy the only copy.
    """
    conn = connect(path)
    verdict = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if verdict != "ok":
        conn.close()
        raise RuntimeError(f"history archive failed integrity_check: {verdict}")
    return conn


def append_sweep_to_history(
    conn: sqlite3.Connection, history_conn: sqlite3.Connection, sweep_id: int
) -> int:
    """Copy one sweep (run + class rows) into the archive.

    The archive assigns its own sweep_id (weekly runners start fresh, so
    their local ids all begin at 1 and would collide). Growth is
    verified: the archive must hold strictly more runs afterwards.
    """
    run = conn.execute(
        "SELECT * FROM sweep_run WHERE sweep_id = ?", (sweep_id,)
    ).fetchone()
    if run is None:
        raise RuntimeError(f"no sweep_run with sweep_id={sweep_id}")
    class_rows = conn.execute(
        "SELECT * FROM sweep_class WHERE sweep_id = ?", (sweep_id,)
    ).fetchall()
    before = history_conn.execute("SELECT count(*) FROM sweep_run").fetchone()[0]
    with history_conn:
        cursor = history_conn.execute(
            """
            INSERT INTO sweep_run
              (run_date, started_at, nadac_horizon, class_count,
               fda_listed_count, constraint_count, mixed_count, quiet_count,
               elapsed_seconds, code_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run["run_date"],
                run["started_at"],
                run["nadac_horizon"],
                run["class_count"],
                run["fda_listed_count"],
                run["constraint_count"],
                run["mixed_count"],
                run["quiet_count"],
                run["elapsed_seconds"],
                run["code_version"],
            ),
        )
        new_id = cursor.lastrowid
        assert new_id is not None
        history_conn.executemany(
            """
            INSERT INTO sweep_class
              (sweep_id, ingredient_set, df_route, strength_norm, te_code,
               rep_ndc11, member_count, marketed_count, surveyed_count,
               fda_listed_members, drift_pct, drift_fired, dropout_members,
               dropout_ratio, volume_change_pct, volume_quarter, recalls,
               fingerprints, verdict)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    new_id,
                    row["ingredient_set"],
                    row["df_route"],
                    row["strength_norm"],
                    row["te_code"],
                    row["rep_ndc11"],
                    row["member_count"],
                    row["marketed_count"],
                    row["surveyed_count"],
                    row["fda_listed_members"],
                    row["drift_pct"],
                    row["drift_fired"],
                    row["dropout_members"],
                    row["dropout_ratio"],
                    row["volume_change_pct"],
                    row["volume_quarter"],
                    row["recalls"],
                    row["fingerprints"],
                    row["verdict"],
                )
                for row in class_rows
            ],
        )
    after = history_conn.execute("SELECT count(*) FROM sweep_run").fetchone()[0]
    if after <= before:
        raise RuntimeError(
            f"archive did not grow (runs {before} -> {after}) — refusing"
        )
    return int(new_id)
