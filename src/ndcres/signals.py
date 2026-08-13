"""Supply-stress signals.

Three independent, dataset-relative components, each with citable
evidence - combined into a single documented heuristic score in [0, 1].
The score is an INFERENCE about supply stress. It is never a statement
of availability; equivalence facts and supply inference must never be
conflated (design principle: probabilities, never booleans, anywhere
availability is implied).

Components and fixed weights (tuned 2026-08 against the motivating
real-world case — an estradiol-patch shortage that pharmacies lived
through for months while FDA's list stayed empty):

    shortage   0.50  an openFDA record with status Current or To Be
                     Discontinued. That list is manufacturer-SELF-
                     REPORTED and LAGGING: whole real shortages never
                     appear on it (zero transdermal-estradiol records
                     exist during a documented patch shortage). So its
                     absence is deliberately weak evidence and is worded
                     as "not on FDA's shortage list", never "available".
    dropout    0.25  the NDC has stopped appearing in weekly NADAC
                     surveys. NADAC derives from real pharmacy invoice
                     transactions, so dropout often precedes a shortage
                     bulletin. Measured against the dataset's own
                     horizon (max as-of date), never the wall clock -
                     deterministic and offline-friendly. Fires at >= 4
                     weeks, scales linearly to full weight at 8.
    drift      0.25  trailing-12-month acquisition-cost change: the
                     latest rate vs the rate in force one year before
                     the latest effective date (cross-year capable).
                     Fires at >= +10%, scales to full weight at +35%.
                     CMS damps generic rates with a 3-month moving
                     average (since 2024-12), so any sustained climb on
                     this index understates the spot market - which is
                     why the thresholds are low: during the motivating
                     shortage this was the ONLY public signal moving.
                     NADAC class-prices interchangeable generics, so a
                     generic's climb usually reflects its whole
                     equivalence class tightening at once.

Marketing status is a separate axis reported alongside - never folded
into the score (discontinuation is not shortage).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Sequence

_WEIGHT_SHORTAGE = 0.50
_WEIGHT_DROPOUT = 0.25
_WEIGHT_DRIFT = 0.25

_DROPOUT_FIRE_WEEKS = 4.0
_DROPOUT_FULL_WEEKS = 8.0
_DRIFT_FIRE_PCT = 0.10
_DRIFT_FULL_PCT = 0.35

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
    return shortage_component_from_rows(rows)


def shortage_component_from_rows(
    rows: Sequence[sqlite3.Row],
) -> SignalComponent:
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
            "not on FDA's official drug-shortage list (openFDA) - that list "
            "is manufacturer-self-reported and lagging; real-world pharmacy "
            "backorders often appear late or never, so absence is weak "
            "evidence and never evidence of availability"
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
    return dropout_component_from_last_seen(last_seen, horizon)


def dropout_component_from_last_seen(
    last_seen: str | None, horizon: str | None
) -> SignalComponent:
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
                f"{horizon} - transactions appear to have stopped"
            ),
        )
    return SignalComponent(
        name="survey-dropout",
        fired=False,
        contribution=0.0,
        evidence=f"present in the NADAC survey through {last_seen}",
    )


def _nadac_series(conn: sqlite3.Connection, ndc11: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT effective_date, price, classification FROM nadac "
        "WHERE ndc11 = ? ORDER BY effective_date",
        (ndc11,),
    ).fetchall()


def _drift_pair(
    series: Sequence[sqlite3.Row],
) -> tuple[sqlite3.Row, sqlite3.Row] | None:
    """(baseline, latest) rows for the trailing-year drift, or None.

    The baseline is the rate in force one year before the latest
    effective date (newest rate at or before the boundary, falling back
    to the oldest known rate). ``series`` must be sorted by
    effective_date ascending.
    """
    if len(series) < 2:
        return None
    latest = series[-1]
    window_start = _iso_to_date(latest["effective_date"]) - timedelta(days=365)
    in_force = [
        r for r in series if _iso_to_date(r["effective_date"]) <= window_start
    ]
    baseline = in_force[-1] if in_force else series[0]
    if baseline["price"] <= 0:
        return None
    return baseline, latest


def drift_pct(conn: sqlite3.Connection, ndc11: str) -> float | None:
    pair = _drift_pair(_nadac_series(conn, ndc11))
    if pair is None:
        return None
    baseline, latest = pair
    return float((latest["price"] - baseline["price"]) / baseline["price"])


def drift_component(conn: sqlite3.Connection, ndc11: str) -> SignalComponent:
    return drift_component_from_series(_nadac_series(conn, ndc11))


def drift_component_from_series(series: Sequence[sqlite3.Row]) -> SignalComponent:
    pair = _drift_pair(series)
    if pair is None:
        return SignalComponent(
            name="price-drift",
            fired=False,
            contribution=0.0,
            evidence="insufficient NADAC price history for a trend",
        )
    baseline, latest = pair
    pct = (latest["price"] - baseline["price"]) / baseline["price"]
    evidence = (
        f"acquisition cost {baseline['price']:.5f} (eff "
        f"{baseline['effective_date']}) -> {latest['price']:.5f} (eff "
        f"{latest['effective_date']}): {pct:+.1%} over the trailing year"
    )
    if pct >= _DRIFT_FIRE_PCT:
        scale = min(pct / _DRIFT_FULL_PCT, 1.0)
        note = " - sustained climb on a 3-month-damped index (spot increases run higher)"
        if latest["classification"] == "G":
            note += (
                "; NADAC class-prices interchangeable generics, so this "
                "reflects the whole equivalence class tightening"
            )
        return SignalComponent(
            name="price-drift",
            fired=True,
            contribution=_WEIGHT_DRIFT * scale,
            evidence=evidence + note,
        )
    return SignalComponent(
        name="price-drift", fired=False, contribution=0.0, evidence=evidence
    )


def signal_report(conn: sqlite3.Connection, ndc11: str) -> SignalReport:
    horizon = survey_horizon(conn)
    series = _nadac_series(conn, ndc11)
    shortage_rows = conn.execute(
        """
        SELECT status, availability, shortage_reason, update_date
        FROM shortage WHERE ndc11 = ? OR ndc9 = ?
        ORDER BY update_date DESC
        """,
        (ndc11, ndc11[:9]),
    ).fetchall()
    last_seen_row = conn.execute(
        "SELECT max(as_of_last) AS last_seen FROM nadac WHERE ndc11 = ?",
        (ndc11,),
    ).fetchone()
    last_seen = last_seen_row["last_seen"] if last_seen_row else None
    return signal_report_from(
        ndc11,
        nadac_series=series,
        nadac_last_seen=last_seen,
        shortage_rows=shortage_rows,
        horizon=horizon,
    )


def signal_report_from(
    ndc11: str,
    *,
    nadac_series: Sequence[sqlite3.Row],
    nadac_last_seen: str | None,
    shortage_rows: Sequence[sqlite3.Row],
    horizon: str | None,
) -> SignalReport:
    """Assemble a report from prefetched rows — the batch-friendly core
    the resolver uses so N candidates cost a handful of queries, not
    a handful per candidate."""
    components = (
        shortage_component_from_rows(shortage_rows),
        dropout_component_from_last_seen(nadac_last_seen, horizon),
        drift_component_from_series(nadac_series),
    )
    score = min(sum(c.contribution for c in components), 1.0)
    return SignalReport(
        ndc11=ndc11,
        score=round(score, 4),
        components=components,
        survey_horizon=horizon,
    )


# ---------------------------------------------------------------------------
# Class-level supply assessment — the triangulation view.
#
# FDA's shortage list is manufacturer-self-reported and lagging; whole
# real shortages never appear on it. But a genuine supply constraint
# leaves fingerprints across INDEPENDENT public datasets at the level of
# the equivalence class (interchangeable products move together):
#
#   - class acquisition cost climbing (NADAC, class-priced for generics)
#   - class members ceasing to transact (NADAC survey dropout ratio)
#   - national dispensed volume falling (Medicaid SDUD, year over year —
#     demand for chronic therapies is stable, so falling dispensed
#     volume with rising price means patients could not fill)
#   - recalls hitting the class (openFDA enforcement)
#
# Two or more independent fingerprints => "evidence consistent with a
# supply constraint" — deliberately probabilistic wording. This module
# never claims availability, in either direction.
# ---------------------------------------------------------------------------

VERDICT_FDA_LISTED = "fda-listed-shortage"
VERDICT_CONSTRAINT = "evidence-consistent-with-supply-constraint"
VERDICT_MIXED = "mixed-signals"
VERDICT_QUIET = "no-independent-stress-evidence"

VERDICT_LANGUAGE = {
    VERDICT_FDA_LISTED: (
        "On FDA's official drug-shortage list — a confirmed shortage."
    ),
    VERDICT_CONSTRAINT: (
        "NOT on FDA's shortage list, but two or more independent public "
        "signals show the pattern of a supply constraint. FDA's list is "
        "manufacturer-self-reported and lagging; treat this drug as hard "
        "to fill and take the full equivalents list to the pharmacy."
    ),
    VERDICT_MIXED: (
        "Not on FDA's shortage list; one independent signal is elevated. "
        "Worth watching, not conclusive."
    ),
    VERDICT_QUIET: (
        "No independent supply-stress evidence in the public data held "
        "here. This is NOT a statement of availability."
    ),
}

_CLASS_DROPOUT_WEEKS = 8.0
_CLASS_DROPOUT_RATIO_FIRE = 0.25
_VOLUME_DECLINE_FIRE = -0.15
# A demand surge strains supply just as a volume collapse evidences it:
# either direction of large movement is a constraint fingerprint when it
# accompanies price drift (2026 estradiol patches: +76% YoY volume).
_VOLUME_SURGE_FIRE = 0.25
_RECALL_WINDOW_DAYS = 730


@dataclass(frozen=True)
class ClassAssessment:
    member_count: int
    surveyed_count: int
    fda_listed_members: int
    drift_pct: float | None
    drift_fired: bool
    dropout_members: int
    dropout_ratio: float | None
    volume_change_pct: float | None
    volume_quarter: str | None
    recalls: int
    verdict: str
    verdict_language: str
    lines: tuple[str, ...]


def class_supply_assessment(
    conn: sqlite3.Connection, member_ndc11s: tuple[str, ...]
) -> ClassAssessment:
    members = tuple(dict.fromkeys(member_ndc11s))
    horizon = survey_horizon(conn)
    lines: list[str] = []

    # FDA list, across the class.
    fda_listed = 0
    for ndc11 in members:
        if shortage_component(conn, ndc11).fired:
            fda_listed += 1
    if fda_listed:
        lines.append(
            f"{fda_listed} of {len(members)} class members carry an active "
            "record on FDA's shortage list"
        )
    else:
        lines.append(
            "FDA's official shortage list: no entry for any class member "
            "(that list is manufacturer-self-reported and lagging - real "
            "shortages often never appear on it)"
        )

    # Class price drift: interchangeable generics are class-priced, so
    # the strongest member trend describes the class.
    class_drift: float | None = None
    drift_fired = False
    surveyed = 0
    dropout_members = 0
    for ndc11 in members:
        pct = drift_pct(conn, ndc11)
        if pct is not None:
            if class_drift is None or pct > class_drift:
                class_drift = pct
            drift_fired = drift_fired or pct >= _DRIFT_FIRE_PCT
        last_seen_row = conn.execute(
            "SELECT max(as_of_last) AS last_seen FROM nadac WHERE ndc11 = ?",
            (ndc11,),
        ).fetchone()
        last_seen = last_seen_row["last_seen"] if last_seen_row else None
        if last_seen is not None and horizon is not None:
            surveyed += 1
            weeks_gone = (
                _iso_to_date(horizon) - _iso_to_date(last_seen)
            ).days / 7.0
            if weeks_gone >= _CLASS_DROPOUT_WEEKS:
                dropout_members += 1
    if class_drift is not None:
        lines.append(
            f"class acquisition cost {class_drift:+.1%} over the trailing "
            "year on the CMS-damped NADAC index (spot increases run higher; "
            "generics are class-priced, so this is the whole class moving)"
        )
    dropout_ratio = dropout_members / surveyed if surveyed else None
    if surveyed:
        lines.append(
            f"{dropout_members} of {surveyed} surveyed class members have "
            f"stopped appearing in the weekly NADAC pharmacy survey "
            f"(>= {int(_CLASS_DROPOUT_WEEKS)} weeks)"
        )

    # Dispensed-volume trend (Medicaid SDUD), class-wide, year over year.
    volume_change: float | None = None
    volume_quarter: str | None = None
    if members:
        placeholders = ",".join("?" for _ in members)
        volume_rows = conn.execute(
            f"SELECT year, quarter, sum(units) AS units FROM sdud "  # noqa: S608
            f"WHERE ndc11 IN ({placeholders}) "
            "GROUP BY year, quarter ORDER BY year, quarter",
            members,
        ).fetchall()
        if volume_rows:
            latest = volume_rows[-1]
            volume_quarter = f"{latest['year']}Q{latest['quarter']}"
            prior = next(
                (
                    row
                    for row in volume_rows
                    if row["year"] == latest["year"] - 1
                    and row["quarter"] == latest["quarter"]
                ),
                None,
            )
            if prior is not None and prior["units"]:
                volume_change = (latest["units"] - prior["units"]) / prior["units"]
                if volume_change <= _VOLUME_DECLINE_FIRE:
                    reading = (
                        "falling volume with rising price is the fingerprint "
                        "of patients unable to fill"
                    )
                elif volume_change >= _VOLUME_SURGE_FIRE:
                    reading = (
                        "a demand surge of this size strains manufacturing "
                        "capacity - the classic setup for backorders"
                    )
                else:
                    reading = "volume roughly stable"
                lines.append(
                    f"national Medicaid dispensed volume for the class: "
                    f"{volume_change:+.1%} in {volume_quarter} vs the same "
                    f"quarter a year earlier ({reading})"
                )

    # Recalls against class members, measured against the dataset horizon
    # (never the wall clock — deterministic and offline-friendly).
    recalls = 0
    if members:
        ndc9s = tuple(dict.fromkeys(ndc11[:9] for ndc11 in members))
        placeholders = ",".join("?" for _ in ndc9s)
        reference = horizon
        if reference is None:
            latest_recall = conn.execute(
                "SELECT max(recall_initiation) AS d FROM enforcement"
            ).fetchone()
            reference = latest_recall["d"] if latest_recall else None
        cutoff = (
            (_iso_to_date(reference) - timedelta(days=_RECALL_WINDOW_DAYS)).isoformat()
            if reference
            else "0000-00-00"
        )
        recalls = conn.execute(
            f"SELECT count(DISTINCT record_hash) AS n FROM enforcement "  # noqa: S608
            f"WHERE ndc9 IN ({placeholders}) AND ("
            "  status = 'Ongoing' OR recall_initiation >= ?"
            ")",
            (*ndc9s, cutoff),
        ).fetchone()["n"]
        if recalls:
            lines.append(
                f"{recalls} recall record(s) against class members in the "
                "openFDA enforcement data (trailing two years)"
            )

    fingerprints = sum(
        (
            drift_fired,
            dropout_ratio is not None
            and surveyed >= 3
            and dropout_ratio >= _CLASS_DROPOUT_RATIO_FIRE,
            volume_change is not None
            and (
                volume_change <= _VOLUME_DECLINE_FIRE
                or volume_change >= _VOLUME_SURGE_FIRE
            ),
            recalls > 0,
        )
    )
    if fda_listed:
        verdict = VERDICT_FDA_LISTED
    elif fingerprints >= 2:
        verdict = VERDICT_CONSTRAINT
    elif fingerprints == 1:
        verdict = VERDICT_MIXED
    else:
        verdict = VERDICT_QUIET

    return ClassAssessment(
        member_count=len(members),
        surveyed_count=surveyed,
        fda_listed_members=fda_listed,
        drift_pct=class_drift,
        drift_fired=drift_fired,
        dropout_members=dropout_members,
        dropout_ratio=dropout_ratio,
        volume_change_pct=volume_change,
        volume_quarter=volume_quarter,
        recalls=recalls,
        verdict=verdict,
        verdict_language=VERDICT_LANGUAGE[verdict],
        lines=tuple(lines),
    )
