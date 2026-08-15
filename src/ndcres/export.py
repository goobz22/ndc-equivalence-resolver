"""Web export: a trimmed, read-only database for serverless serving.

Serverless functions bundle the database file, so size is a hard
constraint (Vercel: 250MB per function; our gate is far tighter). The
export keeps every reference table the resolver reads, and reduces NADAC
— by far the largest table — to exactly the rows the serving path uses:

    per NDC: the latest rate row, plus the rate in force one year before
    the latest effective date (the price-drift baseline).

Signals computed from the export therefore match the full database:
drift uses (latest, baseline); dropout uses the latest row's as_of_last
vs the global horizon (preserved in meta); annotations show the latest
price. Verbose display-only blobs (package descriptions, shortage raw
JSON) are dropped.

The export FAILS if the result exceeds the size gate — a deploy must
never silently ship an oversized or truncated bundle.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .db import connect
from .signals import survey_horizon

# Vercel's serverless budget is 250MB uncompressed for the whole bundle
# (function + deps + this file). Deps run ~40MB. Budget math for the
# 176MiB (184.5MB) gate: ~167MB current artifact + ≤1MB directory-
# membership window (SPEC §10.3) + ~10MB for the 13-sweep watch-feed
# window (§10.4; ~0.8MB/sweep) ≈ 178MB, leaving ~6MB organic-growth
# slack under the gate and ~25MB of bundle clearance under the platform
# ceiling. Raised from 160MiB with the 5-axis assessment (§7.2);
# previously raised from 150MiB when search_doc joined (§8).
# CI fails the deploy on breach.
SIZE_GATE_BYTES = 176 * 1024 * 1024

_FULL_COPY_TABLES = (
    "meta",
    "source_run",
    "special_case",
    "ob_product",
    "product_ob_link",
    "rx_concept",
    "rx_rel",
    "rx_ndc",
    "product_derived",
    "search_doc",
)


def export_web_db(
    source_path: Path, dest_path: Path, *, size_gate: int = SIZE_GATE_BYTES
) -> int:
    """Build the trimmed web database; returns its size in bytes."""
    if dest_path.exists():
        dest_path.unlink()
    conn = connect(source_path)
    horizon = survey_horizon(conn)
    dest = connect(dest_path)  # creates the schema
    dest.close()

    conn.execute("ATTACH DATABASE ? AS web", (str(dest_path),))
    try:
        with conn:
            for table in _FULL_COPY_TABLES:
                conn.execute(f"DELETE FROM web.{table}")  # noqa: S608
                conn.execute(
                    f"INSERT INTO web.{table} SELECT * FROM main.{table}"  # noqa: S608
                )

            # product: drop the raw substance blob (ingredient_set is the
            # canonical form every consumer uses).
            conn.execute("DELETE FROM web.product")
            conn.execute(
                """
                INSERT INTO web.product
                SELECT ndc9, product_ndc_filed, product_type,
                       proprietary_name, proprietary_suffix,
                       nonproprietary_name, dosage_form_raw, route_raw,
                       marketing_category, appl_type, appl_no, appl_no_raw,
                       labeler_name, NULL, ingredient_set, ingredient_count,
                       strength_numerator, strength_unit, strength_norm,
                       form_family, dea_schedule, start_marketing,
                       end_marketing, ob_link_status, run_id
                FROM main.product
                """
            )

            # package: keep rows, drop the verbose description blob.
            conn.execute("DELETE FROM web.package")
            conn.execute(
                """
                INSERT INTO web.package
                SELECT ndc11, ndc9, package_ndc_filed, ndc_shape, NULL,
                       pack_count, pack_unit, wear_hours, sample_package,
                       start_marketing, end_marketing, run_id
                FROM main.package
                """
            )

            # sdud: the volume-trend signal compares the latest quarter to
            # the same quarter a year earlier — two years suffice.
            conn.execute("DELETE FROM web.sdud")
            conn.execute(
                """
                INSERT INTO web.sdud
                SELECT * FROM main.sdud
                WHERE year >= (SELECT max(year) - 1 FROM main.sdud)
                """
            )

            # enforcement: only NDC-indexed records participate in the
            # class assessment; unindexed free-text records are dead
            # weight in the serving bundle.
            conn.execute("DELETE FROM web.enforcement")
            conn.execute(
                "INSERT INTO web.enforcement "
                "SELECT * FROM main.enforcement WHERE ndc9 IS NOT NULL"
            )

            # shortage: keep rows, drop raw JSON.
            conn.execute("DELETE FROM web.shortage")
            conn.execute(
                """
                INSERT INTO web.shortage
                SELECT record_hash, ndc11, ndc9, generic_name, company_name,
                       status, availability, shortage_reason, initial_posting,
                       update_date, '{}', run_id
                FROM main.shortage
                """
            )

            # nadac: latest row + drift-baseline row per NDC.
            conn.execute("DELETE FROM web.nadac")
            conn.execute(
                """
                INSERT INTO web.nadac
                WITH latest AS (
                  SELECT ndc11, max(effective_date) AS eff
                  FROM main.nadac GROUP BY ndc11
                ),
                baseline AS (
                  SELECT n.ndc11, max(n.effective_date) AS eff
                  FROM main.nadac n JOIN latest l ON n.ndc11 = l.ndc11
                  WHERE n.effective_date <= date(l.eff, '-365 days')
                  GROUP BY n.ndc11
                )
                SELECT n.* FROM main.nadac n
                WHERE EXISTS (
                    SELECT 1 FROM latest l
                    WHERE l.ndc11 = n.ndc11 AND l.eff = n.effective_date
                  )
                  OR EXISTS (
                    SELECT 1 FROM baseline b
                    WHERE b.ndc11 = n.ndc11 AND b.eff = n.effective_date
                  )
                """
            )

            # The dropout signal needs the pre-trim horizon: trimming
            # keeps each NDC's latest row, so max(as_of_last) survives for
            # present NDCs — but record it explicitly for safety.
            if horizon is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO web.meta (key, value) "
                    "VALUES ('nadac_horizon', ?)",
                    (horizon,),
                )

            # Latest 13 sweeps (one quarter of weekly transitions): the
            # serving tier reads the current market picture (/api/gaps,
            # dossier) AND renders watch feeds over recent verdict
            # changes (SPEC §10.4, ~0.8MB/sweep — in the 176MiB gate's
            # budget math). The FULL longitudinal record lives in
            # ndcres-history.db, never in the size-gated artifact.
            conn.execute(
                "INSERT INTO web.sweep_run SELECT * FROM main.sweep_run "
                "WHERE sweep_id IN (SELECT sweep_id FROM main.sweep_run "
                "ORDER BY sweep_id DESC LIMIT 13)"
            )
            conn.execute(
                "INSERT INTO web.sweep_class SELECT * FROM main.sweep_class "
                "WHERE sweep_id IN (SELECT sweep_id FROM main.sweep_run "
                "ORDER BY sweep_id DESC LIMIT 13)"
            )

            # Directory-membership window (SPEC §10.3): the serving
            # path's live class_supply_assessment computes the
            # directory-exit axis from these — one engine, zero drift
            # between what a sweep said and what /api/resolve shows.
            conn.execute(
                "INSERT INTO web.ndc_membership_run "
                "SELECT * FROM main.ndc_membership_run"
            )
            conn.execute(
                "INSERT INTO web.ndc_membership_delta "
                "SELECT * FROM main.ndc_membership_delta"
            )
    finally:
        conn.execute("DETACH DATABASE web")
        conn.close()

    packed = sqlite3.connect(dest_path)
    try:
        # connect() created the schema in WAL mode, and the flag persists
        # in the file header. A WAL database cannot be opened from a
        # read-only filesystem (readers must create -shm), and serverless
        # hosts mount the bundle read-only — so the ARTIFACT ships in
        # rollback-journal mode. The VACUUM afterwards rewrites the file
        # compactly with that header.
        packed.execute("PRAGMA journal_mode = DELETE")
        packed.execute("VACUUM")
    finally:
        packed.close()

    size = dest_path.stat().st_size
    if size > size_gate:
        dest_path.unlink()
        raise RuntimeError(
            f"web export is {size / 1e6:.1f}MB, over the "
            f"{size_gate / 1e6:.0f}MB gate — refusing to produce an "
            "oversized serving bundle"
        )
    return size
