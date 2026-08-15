"""Market-wide sweep (SPEC §10): assess every equivalence class, weekly.

The FDA shortage list is voluntary and keeps no history. This module
gives the measuring cup its lines: it enumerates every TE-rated
equivalence class in the database (~2,900), runs the SAME
class_supply_assessment the per-NDC resolve path uses — one
golden-tested verdict engine, definitionally zero drift between what a
sweep says about a class and what /api/resolve shows for its members —
and persists the results append-only, so the longitudinal record
accumulates run over run.

Membership mirrors resolve's LEGAL class (the seed+T1+T2 set): sample
packages are dropped, discontinued-and-unmarketed members are dropped,
and a class with zero marketed packages is skipped entirely (a wholly
discontinued class cannot be supply-constrained).
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from . import __version__
from .signals import (
    VERDICT_CONSTRAINT,
    VERDICT_FDA_LISTED,
    VERDICT_MIXED,
    VERDICT_QUIET,
    ClassAssessment,
    class_supply_assessment,
    survey_horizon,
)


@dataclass(frozen=True)
class EqClass:
    ingredient_set: str
    df_route: str
    strength_norm: str  # '' when the OB strength is null (keyable)
    te_code: str
    members: tuple[str, ...]  # legal-class ndc11s (deduped, ordered)
    marketed_count: int
    rep_ndc11: str  # deterministic: min marketed ndc11


@dataclass(frozen=True)
class SweepClassRow:
    ingredient_set: str
    df_route: str
    strength_norm: str
    te_code: str
    rep_ndc11: str
    member_count: int
    marketed_count: int
    assessment: ClassAssessment


@dataclass(frozen=True)
class SweepResult:
    run_date: str
    started_at: str
    nadac_horizon: str | None
    classes: tuple[SweepClassRow, ...]
    counts: dict[str, int]
    elapsed_seconds: float


def enumerate_classes(conn: sqlite3.Connection) -> list[EqClass]:
    """Every TE-rated equivalence class with its legal-class members."""
    rows = conn.execute(
        """
        SELECT o.ingredient_set, o.df_route,
               coalesce(o.strength_norm, '') AS strength_norm,
               o.te_code, o.ob_type,
               k.ndc11, k.sample_package,
               (p.end_marketing IS NULL AND k.end_marketing IS NULL
                AND k.sample_package = 0) AS marketed
        FROM ob_product o
        JOIN product_ob_link l USING (appl_type, appl_no, product_no)
        JOIN product p ON p.ndc9 = l.ndc9
        JOIN package k ON k.ndc9 = l.ndc9
        WHERE o.te_code IS NOT NULL
        ORDER BY o.ingredient_set, o.df_route, strength_norm, o.te_code, k.ndc11
        """
    ).fetchall()

    grouped: dict[tuple[str, str, str, str], dict[str, bool]] = {}
    for row in rows:
        if row["sample_package"]:
            continue
        marketed = bool(row["marketed"])
        if row["ob_type"] == "DISCN" and not marketed:
            # resolve EXCLUDES these (discontinued-ob) — so does the class.
            continue
        key = (
            row["ingredient_set"],
            row["df_route"],
            row["strength_norm"],
            row["te_code"],
        )
        members = grouped.setdefault(key, {})
        # An ndc11 can arrive via multiple OB rows; marketed if any says so.
        members[row["ndc11"]] = members.get(row["ndc11"], False) or marketed

    classes: list[EqClass] = []
    for key, members in grouped.items():
        marketed_ndc11s = sorted(n for n, m in members.items() if m)
        if not marketed_ndc11s:
            continue
        classes.append(
            EqClass(
                ingredient_set=key[0],
                df_route=key[1],
                strength_norm=key[2],
                te_code=key[3],
                members=tuple(sorted(members)),
                marketed_count=len(marketed_ndc11s),
                rep_ndc11=marketed_ndc11s[0],
            )
        )
    classes.sort(
        key=lambda c: (c.ingredient_set, c.df_route, c.strength_norm, c.te_code)
    )
    return classes


def run_sweep(conn: sqlite3.Connection) -> SweepResult:
    """Pure compute: assess every class; no writes."""
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    horizon = survey_horizon(conn)
    rows: list[SweepClassRow] = []
    counts = {
        VERDICT_FDA_LISTED: 0,
        VERDICT_CONSTRAINT: 0,
        VERDICT_MIXED: 0,
        VERDICT_QUIET: 0,
    }
    for eq_class in enumerate_classes(conn):
        assessment = class_supply_assessment(
            conn,
            eq_class.members,
            class_key=(
                eq_class.ingredient_set,
                eq_class.df_route,
                eq_class.strength_norm,
                eq_class.te_code,
            ),
        )
        counts[assessment.verdict] = counts.get(assessment.verdict, 0) + 1
        rows.append(
            SweepClassRow(
                ingredient_set=eq_class.ingredient_set,
                df_route=eq_class.df_route,
                strength_norm=eq_class.strength_norm,
                te_code=eq_class.te_code,
                rep_ndc11=eq_class.rep_ndc11,
                member_count=len(eq_class.members),
                marketed_count=eq_class.marketed_count,
                assessment=assessment,
            )
        )
    return SweepResult(
        run_date=started_at[:10],
        started_at=started_at,
        nadac_horizon=horizon,
        classes=tuple(rows),
        counts=counts,
        elapsed_seconds=time.monotonic() - started,
    )


def persist_sweep(conn: sqlite3.Connection, result: SweepResult) -> int:
    """Append one run + its class rows; returns the new sweep_id."""
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO sweep_run
              (run_date, started_at, nadac_horizon, class_count,
               fda_listed_count, constraint_count, mixed_count, quiet_count,
               elapsed_seconds, code_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.run_date,
                result.started_at,
                result.nadac_horizon,
                len(result.classes),
                result.counts.get(VERDICT_FDA_LISTED, 0),
                result.counts.get(VERDICT_CONSTRAINT, 0),
                result.counts.get(VERDICT_MIXED, 0),
                result.counts.get(VERDICT_QUIET, 0),
                result.elapsed_seconds,
                __version__,
            ),
        )
        sweep_id = cursor.lastrowid
        assert sweep_id is not None
        conn.executemany(
            """
            INSERT INTO sweep_class
              (sweep_id, ingredient_set, df_route, strength_norm, te_code,
               rep_ndc11, member_count, marketed_count, surveyed_count,
               fda_listed_members, drift_pct, drift_fired, dropout_members,
               dropout_ratio, volume_change_pct, volume_quarter, recalls,
               fingerprints, verdict, discontinued_members, directory_exits,
               directory_exit_fired)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?)
            """,
            [
                (
                    sweep_id,
                    row.ingredient_set,
                    row.df_route,
                    row.strength_norm,
                    row.te_code,
                    row.rep_ndc11,
                    row.member_count,
                    row.marketed_count,
                    row.assessment.surveyed_count,
                    row.assessment.fda_listed_members,
                    row.assessment.drift_pct,
                    int(row.assessment.drift_fired),
                    row.assessment.dropout_members,
                    row.assessment.dropout_ratio,
                    row.assessment.volume_change_pct,
                    row.assessment.volume_quarter,
                    row.assessment.recalls,
                    row.assessment.fingerprints,
                    row.assessment.verdict,
                    row.assessment.discontinued_members,
                    row.assessment.directory_exits,
                    (
                        int(row.assessment.directory_exit_fired)
                        if row.assessment.directory_exits is not None
                        else None
                    ),
                )
                for row in result.classes
            ],
        )
    return int(sweep_id)


def latest_sweep_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT max(sweep_id) AS s FROM sweep_run").fetchone()
    return int(row["s"]) if row and row["s"] is not None else None
