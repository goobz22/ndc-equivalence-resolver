"""Supply-stress signals.

Three independent, dataset-relative components, each with citable
evidence — combined into a single documented heuristic score in [0, 1].
The score is an INFERENCE about supply stress. It is never a statement
of availability; equivalence facts and supply inference must never be
conflated (design principle: probabilities, never booleans, anywhere
availability is implied).

Components and fixed weights:

    shortage   0.60  an openFDA shortage record with status Current or
                     To Be Discontinued. Absence means "no known
                     shortage record" — NOT "available" (the shortage
                     dataset is sparse; whole drug families have no
                     records at all).
    dropout    0.25  the NDC has stopped appearing in weekly NADAC
                     surveys. NADAC derives from real pharmacy invoice
                     transactions, so dropout often precedes a shortage
                     bulletin. Measured against the dataset's own
                     horizon (max as-of date), never the wall clock —
                     deterministic and offline-friendly. Fires at >= 4
                     weeks, scales linearly to full weight at 8.
    drift      0.15  trailing-12-month acquisition-cost change: the
                     latest price vs the price in force one year before
                     the latest effective date (cross-year capable).
                     Fires at >= +15%, scales to full weight at +50%.
                     Note: CMS damps generic rates with a 3-month moving
                     average since 2024-12, so real drift is understated.

Marketing status is a separate axis reported alongside — never folded
into the score (discontinuation is not shortage).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

_WEIGHT_SHORTAGE = 0.60
_WEIGHT_DROPOUT = 0.25
_WEIGHT_DRIFT = 0.15

_DROPOUT_FIRE_WEEKS = 4.0
_DROPOUT_FULL_WEEKS = 8.0
_DRIFT_FIRE_PCT = 0.15
_DRIFT_FULL_PCT = 0.50

_ACTIVE_SHORTAGE_STATUSES = {"Current", "To Be Discontinued"}


@dataclass(frozen=True)
class SignalComponent:
    name: str
    fired: bool
    contribution: float
    evidence: str


@dataclass(frozen=True)
class SignalReport:
    ndc11: str
    score: float
    components: tuple[SignalComponent, ...]
    survey_horizon: str | None  # max as-of date in the NADAC data


def _iso_to_date(iso: str) -> date:
    year, month, day = iso.split("-")
    return date(int(year), int(month), int(day))


def survey_horizon(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT max(as_of_last) AS horizon FROM nadac").fetchone()
    return row["horizon"] if row is not None else None


def shortage_component(conn: sqlite3.Connection, ndc11: str) -> SignalComponent:
    rows = conn.execute(
        """
        SELECT status, availability, shortage_reason, update_date
        FROM shortage WHERE ndc11 = ? OR ndc9 = ?
        ORDER BY update_date DESC
        """,
        (ndc11, ndc11[:9]),
    ).fetchall()
    active = [r for r in rows if r["status"] in _ACTIVE_SHORTAGE_STATUSES]
    if active:
        top = active[0]
        detail = ", ".join(
            part
            for part in (
                f"status {top['status']}",
                f"availability {top['availability']}" if top["availability"] else None,
                f"reason: {top['shortage_reason']}" if top["shortage_reason"] else None,
                f"updated {top['update_date']}",
            )
            if part
        )
        return SignalComponent(
            name="shortage",
            fired=True,
            contribution=_WEIGHT_SHORTAGE,
            evidence=f"openFDA shortage record: {detail}",
        )
    if rows:
        return SignalComponent(
            name="shortage",
            fired=False,
            contribution=0.0,
            evidence=(
                "openFDA shortage records exist but none active "
                f"(latest status {rows[0]['status']})"
            ),
        )
    return SignalComponent(
        name="shortage",
        fired=False,
        contribution=0.0,
        evidence=(
            "no known shortage record in openFDA (absence is not evidence "
            "of availability)"
        ),
    )


def dropout_component(
    conn: sqlite3.Connection, ndc11: str, horizon: str | None
) -> SignalComponent:
    row = conn.execute(
        "SELECT max(as_of_last) AS last_seen FROM nadac WHERE ndc11 = ?",
        (ndc11,),
    ).fetchone()
    last_seen = row["last_seen"] if row is not None else None
    if last_seen is None or horizon is None:
        return SignalComponent(
            name="survey-dropout",
            fired=False,
            contribution=0.0,
            evidence="never present in the NADAC survey data held locally",
        )
    weeks_gone = (_iso_to_date(horizon) - _iso_to_date(last_seen)).days / 7.0
    if weeks_gone >= _DROPOUT_FIRE_WEEKS:
        scale = min(weeks_gone / _DROPOUT_FULL_WEEKS, 1.0)
        return SignalComponent(
            name="survey-dropout",
            fired=True,
            contribution=_WEIGHT_DROPOUT * scale,
            evidence=(
                f"last seen in the NADAC weekly survey {last_seen}; "
                f"{weeks_gone:.0f} weeks before the dataset horizon "
                f"{horizon} — transactions appear to have stopped"
            ),
        )
    return SignalComponent(
        name="survey-dropout",
        fired=False,
        contribution=0.0,
        evidence=f"present in the NADAC survey through {last_seen}",
    )


def drift_component(conn: sqlite3.Connection, ndc11: str) -> SignalComponent:
    rows = conn.execute(
        "SELECT effective_date, price FROM nadac WHERE ndc11 = ? "
        "ORDER BY effective_date",
        (ndc11,),
    ).fetchall()
    if len(rows) < 2:
        return SignalComponent(
            name="price-drift",
            fired=False,
            contribution=0.0,
            evidence="insufficient NADAC price history for a trend",
        )
    latest = rows[-1]
    window_start = _iso_to_date(latest["effective_date"]) - timedelta(days=365)
    # The price in force at the window boundary: the newest rate at or
    # before it, falling back to the oldest known rate.
    in_force = [
        r for r in rows if _iso_to_date(r["effective_date"]) <= window_start
    ]
    baseline = in_force[-1] if in_force else rows[0]
    if baseline["price"] <= 0:
        return SignalComponent(
            name="price-drift", fired=False, contribution=0.0,
            evidence="baseline price unusable",
        )
    pct = (latest["price"] - baseline["price"]) / baseline["price"]
    evidence = (
        f"acquisition cost {baseline['price']:.5f} (eff "
        f"{baseline['effective_date']}) -> {latest['price']:.5f} (eff "
        f"{latest['effective_date']}): {pct:+.1%} over the trailing year"
    )
    if pct >= _DRIFT_FIRE_PCT:
        scale = min(pct / _DRIFT_FULL_PCT, 1.0)
        return SignalComponent(
            name="price-drift",
            fired=True,
            contribution=_WEIGHT_DRIFT * scale,
            evidence=evidence + " — rising cost on a survey-priced product",
        )
    return SignalComponent(
        name="price-drift", fired=False, contribution=0.0, evidence=evidence
    )


def signal_report(conn: sqlite3.Connection, ndc11: str) -> SignalReport:
    horizon = survey_horizon(conn)
    components = (
        shortage_component(conn, ndc11),
        dropout_component(conn, ndc11, horizon),
        drift_component(conn, ndc11),
    )
    score = min(sum(c.contribution for c in components), 1.0)
    return SignalReport(
        ndc11=ndc11,
        score=round(score, 4),
        components=components,
        survey_horizon=horizon,
    )
