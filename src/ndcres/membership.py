"""Directory-membership snapshots (SPEC §10.3): the fast witness.

The NDC Directory is a weekly full replacement — a product that vanishes
from it has left the market's shelf-facing record NOW, weeks before the
price survey notices and months before quarterly volumes do. This module
records what the directory said, week over week:

  ndc_membership_state — one row per directory ndc11 (the rolling
    baseline), carrying the marketing status, OB type, and equivalence-
    class key AT LAST SIGHT.
  ndc_membership_delta — append-only appeared/vanished rows from the
    second snapshot on. A vanished NDC's row is stamped FROM STATE —
    the current database no longer holds the row, so the state table is
    the only honest witness to what it looked like.
  ndc_membership_run — one row per snapshot (dataset-relative date =
    the ndc source_run fetch date), idempotent on re-runs.

The directory-exit signal axis (Phase 3) consumes the deltas; until
then this module only accumulates. Snapshots write to the durable
archive AND the local database; `copy_recent_deltas` backfills the
trailing window into a fresh weekly pipeline database so the serving
export can carry it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from .sweep import enumerate_classes


@dataclass(frozen=True)
class MembershipSnapshot:
    snapshot_date: str
    is_baseline: bool
    present: int
    appeared: int
    vanished: int


def _ndc_fetch_date(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT max(fetched_at) AS f FROM source_run "
        "WHERE source = 'ndc' AND status = 'ok'"
    ).fetchone()
    return row["f"][:10] if row and row["f"] else None


def _current_membership(
    conn: sqlite3.Connection,
) -> dict[str, tuple[str | None, str | None, tuple[str, str, str, str] | None]]:
    """ndc11 -> (end_marketing, ob_type, class_key) from the live tables.

    end_marketing: non-null when EITHER the package or its product is
    end-marketed (matching resolve's marketed test). ob_type: best
    linked Orange Book type, RX > OTC > DISCN. class_key: the TE-rated
    legal class per sweep.enumerate_classes (one engine); an ndc11 in
    multiple classes gets the lexicographically first (deterministic).
    """
    membership: dict[
        str, tuple[str | None, str | None, tuple[str, str, str, str] | None]
    ] = {}
    ob_rank = {"RX": 0, "OTC": 1, "DISCN": 2}
    for row in conn.execute(
        """
        SELECT k.ndc11,
               coalesce(k.end_marketing, p.end_marketing) AS end_marketing,
               (SELECT o.ob_type
                  FROM product_ob_link l
                  JOIN ob_product o USING (appl_type, appl_no, product_no)
                 WHERE l.ndc9 = k.ndc9
                 ORDER BY CASE o.ob_type
                   WHEN 'RX' THEN 0 WHEN 'OTC' THEN 1 ELSE 2 END
                 LIMIT 1) AS ob_type
        FROM package k JOIN product p USING (ndc9)
        """
    ):
        membership[row["ndc11"]] = (row["end_marketing"], row["ob_type"], None)
    del ob_rank
    for eq_class in enumerate_classes(conn):
        key = (
            eq_class.ingredient_set,
            eq_class.df_route,
            eq_class.strength_norm,
            eq_class.te_code,
        )
        for member in eq_class.members:
            existing = membership.get(member)
            if existing is None:
                continue
            if existing[2] is None or key < existing[2]:
                membership[member] = (existing[0], existing[1], key)
    return membership


def snapshot_membership(
    conn: sqlite3.Connection, history_conn: sqlite3.Connection
) -> MembershipSnapshot:
    """Record the directory's current membership into the archive.

    First run: baseline (state populated, ZERO delta rows — a baseline
    has nothing to differ from). Later runs: vanished = state rows
    absent from the current directory (delta stamped from state, state
    row removed); appeared = current rows absent from state; state
    upserted. Same-snapshot-date re-runs are idempotent no-ops.
    """
    snapshot_date = _ndc_fetch_date(conn)
    if snapshot_date is None:
        raise RuntimeError(
            "no successful ndc ingest to snapshot — refresh first"
        )
    existing = history_conn.execute(
        "SELECT present_count, appeared_count, vanished_count, is_baseline "
        "FROM ndc_membership_run WHERE snapshot_date = ?",
        (snapshot_date,),
    ).fetchone()
    if existing is not None:
        return MembershipSnapshot(
            snapshot_date=snapshot_date,
            is_baseline=bool(existing["is_baseline"]),
            present=existing["present_count"],
            appeared=existing["appeared_count"],
            vanished=existing["vanished_count"],
        )

    current = _current_membership(conn)
    state_rows = {
        row["ndc11"]: row
        for row in history_conn.execute("SELECT * FROM ndc_membership_state")
    }
    is_baseline = not state_rows

    appeared = [] if is_baseline else sorted(set(current) - set(state_rows))
    vanished = [] if is_baseline else sorted(set(state_rows) - set(current))

    with history_conn:
        if not is_baseline:
            history_conn.executemany(
                """
                INSERT OR IGNORE INTO ndc_membership_delta
                  (snapshot_date, ndc11, change, last_end_marketing,
                   last_ob_type, ingredient_set, df_route, strength_norm,
                   te_code)
                VALUES (?, ?, 'appeared', NULL, NULL, ?, ?, ?, ?)
                """,
                [
                    (snapshot_date, ndc11, *(current[ndc11][2] or (None,) * 4))
                    for ndc11 in appeared
                ],
            )
            history_conn.executemany(
                """
                INSERT OR IGNORE INTO ndc_membership_delta
                  (snapshot_date, ndc11, change, last_end_marketing,
                   last_ob_type, ingredient_set, df_route, strength_norm,
                   te_code)
                VALUES (?, ?, 'vanished', ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        snapshot_date,
                        ndc11,
                        state_rows[ndc11]["end_marketing"],
                        state_rows[ndc11]["ob_type"],
                        state_rows[ndc11]["ingredient_set"],
                        state_rows[ndc11]["df_route"],
                        state_rows[ndc11]["strength_norm"],
                        state_rows[ndc11]["te_code"],
                    )
                    for ndc11 in vanished
                ],
            )
            history_conn.executemany(
                "DELETE FROM ndc_membership_state WHERE ndc11 = ?",
                [(ndc11,) for ndc11 in vanished],
            )
        history_conn.executemany(
            """
            INSERT INTO ndc_membership_state
              (ndc11, end_marketing, ob_type, ingredient_set, df_route,
               strength_norm, te_code, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ndc11) DO UPDATE SET
              end_marketing = excluded.end_marketing,
              ob_type = excluded.ob_type,
              ingredient_set = excluded.ingredient_set,
              df_route = excluded.df_route,
              strength_norm = excluded.strength_norm,
              te_code = excluded.te_code,
              last_seen = excluded.last_seen
            """,
            [
                (
                    ndc11,
                    end_marketing,
                    ob_type,
                    *(class_key or (None,) * 4),
                    snapshot_date,
                    snapshot_date,
                )
                for ndc11, (end_marketing, ob_type, class_key) in current.items()
            ],
        )
        history_conn.execute(
            """
            INSERT INTO ndc_membership_run
              (snapshot_date, present_count, appeared_count, vanished_count,
               is_baseline)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                snapshot_date,
                len(current),
                len(appeared),
                len(vanished),
                int(is_baseline),
            ),
        )
    return MembershipSnapshot(
        snapshot_date=snapshot_date,
        is_baseline=is_baseline,
        present=len(current),
        appeared=len(appeared),
        vanished=len(vanished),
    )


def copy_recent_deltas(
    history_conn: sqlite3.Connection,
    conn: sqlite3.Connection,
    *,
    window_weeks: int = 12,
) -> int:
    """Backfill the trailing delta window into a (fresh) main database.

    The weekly pipeline database is rebuilt from sources each run and
    has no memory; the archive does. The serving export needs the
    trailing window locally so the directory-exit axis computes the
    same answer everywhere (one engine).
    """
    latest = history_conn.execute(
        "SELECT max(snapshot_date) AS d FROM ndc_membership_run"
    ).fetchone()
    if latest is None or latest["d"] is None:
        return 0
    floor = (
        date.fromisoformat(latest["d"]) - timedelta(weeks=window_weeks)
    ).isoformat()
    runs = history_conn.execute(
        "SELECT * FROM ndc_membership_run WHERE snapshot_date >= ?", (floor,)
    ).fetchall()
    deltas = history_conn.execute(
        "SELECT * FROM ndc_membership_delta WHERE snapshot_date >= ?", (floor,)
    ).fetchall()
    with conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO ndc_membership_run
              (snapshot_date, snapshot_source, present_count, appeared_count,
               vanished_count, is_baseline)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["snapshot_date"],
                    row["snapshot_source"],
                    row["present_count"],
                    row["appeared_count"],
                    row["vanished_count"],
                    row["is_baseline"],
                )
                for row in runs
            ],
        )
        conn.executemany(
            """
            INSERT OR IGNORE INTO ndc_membership_delta
              (snapshot_date, ndc11, change, last_end_marketing, last_ob_type,
               ingredient_set, df_route, strength_norm, te_code)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["snapshot_date"],
                    row["ndc11"],
                    row["change"],
                    row["last_end_marketing"],
                    row["last_ob_type"],
                    row["ingredient_set"],
                    row["df_route"],
                    row["strength_norm"],
                    row["te_code"],
                )
                for row in deltas
            ],
        )
    return len(deltas)


def membership_snapshot_count(conn: sqlite3.Connection) -> int:
    return int(
        conn.execute("SELECT count(*) FROM ndc_membership_run").fetchone()[0]
    )
