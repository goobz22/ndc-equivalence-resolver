"""The gap report (SPEC §12): the delta between evidence and the list.

Reads the LATEST persisted sweep — never recomputes at request time —
and splits every assessed class three ways:

  unlisted_constraints — verdict = evidence-consistent-with-supply-
    constraint. By construction these carry ZERO active FDA records:
    the headline list, what the measuring cup misses.
  fda_listed — classes the official list covers (concordant picture).
  listed_but_quiet — on the FDA list with zero independent fingerprints:
    the instrument disagreeing in the other direction.

Ranking within unlisted_constraints (documented, deterministic):
evidence strength first (fingerprints), then evidence breadth
(surveyed_count — guards tiny-N artifacts), then market breadth
(member_count as the impact proxy), then drift severity, then the class
key. SDUD units are deliberately NOT an impact weight: units are
incomparable across dose forms (mL vs patches vs tablets).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from .signals import VERDICT_CONSTRAINT, VERDICT_FDA_LISTED
from .sweep import latest_sweep_id


class GapError(RuntimeError):
    """No sweep exists to report over."""


@dataclass(frozen=True)
class GapEntry:
    ingredient_set: str
    df_route: str
    strength_norm: str
    te_code: str
    rep_ndc11: str
    member_count: int
    marketed_count: int
    surveyed_count: int
    fda_listed_members: int
    drift_pct: float | None
    drift_fired: bool
    dropout_members: int
    dropout_ratio: float | None
    volume_change_pct: float | None
    volume_quarter: str | None
    recalls: int
    fingerprints: int
    verdict: str


@dataclass(frozen=True)
class GapReport:
    sweep_id: int
    run_date: str
    nadac_horizon: str | None
    class_count: int
    counts: dict[str, int]
    unlisted_constraints: tuple[GapEntry, ...]
    fda_listed: tuple[GapEntry, ...]
    listed_but_quiet: tuple[GapEntry, ...]


def _entry(row: sqlite3.Row) -> GapEntry:
    return GapEntry(
        ingredient_set=row["ingredient_set"],
        df_route=row["df_route"],
        strength_norm=row["strength_norm"],
        te_code=row["te_code"],
        rep_ndc11=row["rep_ndc11"],
        member_count=row["member_count"],
        marketed_count=row["marketed_count"],
        surveyed_count=row["surveyed_count"],
        fda_listed_members=row["fda_listed_members"],
        drift_pct=row["drift_pct"],
        drift_fired=bool(row["drift_fired"]),
        dropout_members=row["dropout_members"],
        dropout_ratio=row["dropout_ratio"],
        volume_change_pct=row["volume_change_pct"],
        volume_quarter=row["volume_quarter"],
        recalls=row["recalls"],
        fingerprints=row["fingerprints"],
        verdict=row["verdict"],
    )


def _rank_key(entry: GapEntry) -> tuple[Any, ...]:
    return (
        -entry.fingerprints,
        -entry.surveyed_count,
        -entry.member_count,
        -(entry.drift_pct if entry.drift_pct is not None else float("-inf")),
        entry.ingredient_set,
        entry.df_route,
        entry.strength_norm,
        entry.te_code,
    )


def gap_report(
    conn: sqlite3.Connection, sweep_id: int | None = None
) -> GapReport:
    resolved_id = sweep_id if sweep_id is not None else latest_sweep_id(conn)
    if resolved_id is None:
        raise GapError(
            "no sweep has been persisted — run `ndcres sweep` (or wait for "
            "the weekly pipeline) before asking for the gap report"
        )
    run = conn.execute(
        "SELECT * FROM sweep_run WHERE sweep_id = ?", (resolved_id,)
    ).fetchone()
    if run is None:
        raise GapError(f"no sweep_run with sweep_id={resolved_id}")

    entries = [
        _entry(row)
        for row in conn.execute(
            "SELECT * FROM sweep_class WHERE sweep_id = ?", (resolved_id,)
        )
    ]
    unlisted = sorted(
        (e for e in entries if e.verdict == VERDICT_CONSTRAINT), key=_rank_key
    )
    listed = sorted(
        (e for e in entries if e.verdict == VERDICT_FDA_LISTED), key=_rank_key
    )
    quiet_but_listed = [e for e in listed if e.fingerprints == 0]
    return GapReport(
        sweep_id=resolved_id,
        run_date=run["run_date"],
        nadac_horizon=run["nadac_horizon"],
        class_count=run["class_count"],
        counts={
            "fda_listed": run["fda_listed_count"],
            "constraint": run["constraint_count"],
            "mixed": run["mixed_count"],
            "quiet": run["quiet_count"],
        },
        unlisted_constraints=tuple(unlisted),
        fda_listed=tuple(listed),
        listed_but_quiet=tuple(quiet_but_listed),
    )
