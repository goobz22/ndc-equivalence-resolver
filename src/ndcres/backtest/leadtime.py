"""Lead-time analysis (SPEC §13): were the signals early?

For every historical FDA listing (first-posting dates recovered by
wayback.py plus the forward snapshots), map the listed drug name to the
equivalence classes it names, then replay the four independent evidence
axes using ONLY data whose dataset-internal dates precede a cutoff:

  concordance-at-listing — did >=2 axes fire at the moment FDA first
    posted it?
  lead time — stepping the cutoff back 28 days at a time, how far
    before the posting did the evidence already show the pattern?

Framing the thesis requires: the FDA list is NOT ground truth (that is
the finding). Classes that fire without ever being listed are
UNCONFIRMED, not false — the estradiol case is the worked example of an
unconfirmed firing later corroborated by three mandatory-reporting
regimes abroad.

Documented approximations (docs/VALIDATION.md): replayed NADAC yearly
files carry effective-date fidelity but not the original weekly as-of
observations, so the dropout axis is proxied by a stall in a member's
rate-change cadence; thresholds are imported from signals.py — the ONE
home — never retuned here (tuning against the lagging reference we are
indicting would be circular).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from ..signals import (
    _CLASS_DROPOUT_RATIO_FIRE,
    _DRIFT_FIRE_PCT,
    _RECALL_WINDOW_DAYS,
    _VOLUME_DECLINE_FIRE,
    _VOLUME_SURGE_FIRE,
)

_STEP_DAYS = 28
_MAX_STEPS = 13  # ~1 year of lookback
_DROPOUT_STALL_DAYS = 56  # ~8 weeks without a rate change before cutoff


def _iso(day: date) -> str:
    return day.isoformat()


def _to_date(text: str) -> date:
    return date.fromisoformat(text)


@dataclass(frozen=True)
class ListingCase:
    drug_name_norm: str
    first_posted: str
    class_count: int
    member_ndc11s: tuple[str, ...]
    fingerprints_at_posting: int
    lead_days: int  # 0 = concordant only at posting; >0 = early


def class_members_for_name(
    conn: sqlite3.Connection, drug_name_norm: str
) -> tuple[int, tuple[str, ...]]:
    """Map a listed drug name to TE-rated classes by ingredient names.

    A class matches when every part of its ingredient_set appears as a
    substring of the normalized name. The error direction is
    OVER-matching: a combination product's name ("Ethinyl Estradiol and
    Norethindrone") also matches plain single-ingredient classes, so
    those classes' members pool into the replay. Per-case class/member
    counts are reported so over-matched cases are inspectable; the
    docs/VALIDATION.md limitations name this. Returns (class_count,
    member ndc11s across the matched classes).
    """
    classes = conn.execute(
        """
        SELECT DISTINCT o.ingredient_set, o.df_route,
               coalesce(o.strength_norm,'') AS strength_norm, o.te_code
        FROM ob_product o JOIN product_ob_link l
          USING (appl_type, appl_no, product_no)
        WHERE o.te_code IS NOT NULL
        """
    ).fetchall()
    matched_keys = []
    for row in classes:
        parts = row["ingredient_set"].split("|")
        if all(part in drug_name_norm for part in parts):
            matched_keys.append(row)
    members: list[str] = []
    for key in matched_keys:
        for member in conn.execute(
            """
            SELECT DISTINCT k.ndc11
            FROM ob_product o
            JOIN product_ob_link l USING (appl_type, appl_no, product_no)
            JOIN package k ON k.ndc9 = l.ndc9
            WHERE o.ingredient_set = ? AND o.df_route = ?
              AND coalesce(o.strength_norm,'') = ? AND o.te_code = ?
              AND k.sample_package = 0
            """,
            (
                key["ingredient_set"],
                key["df_route"],
                key["strength_norm"],
                key["te_code"],
            ),
        ):
            members.append(member["ndc11"])
    return len(matched_keys), tuple(dict.fromkeys(members))


def fingerprints_at(
    conn: sqlite3.Connection, members: tuple[str, ...], cutoff: str
) -> int:
    """Replay the four evidence axes using only pre-cutoff data."""
    if not members:
        return 0
    placeholders = ",".join("?" for _ in members)

    # Axis 1: class price drift (latest pre-cutoff rate vs the rate in
    # force one year earlier).
    drift_fired = False
    for member in members:
        series = conn.execute(
            "SELECT effective_date, price FROM nadac "
            "WHERE ndc11 = ? AND effective_date < ? ORDER BY effective_date",
            (member, cutoff),
        ).fetchall()
        if len(series) < 2:
            continue
        latest = series[-1]
        baseline_day = _iso(_to_date(latest["effective_date"]) - timedelta(days=365))
        baseline = None
        for row in series:
            if row["effective_date"] <= baseline_day:
                baseline = row
        if baseline is None or not baseline["price"]:
            continue
        pct = (latest["price"] - baseline["price"]) / baseline["price"]
        if pct >= _DRIFT_FIRE_PCT:
            drift_fired = True
            break

    # Axis 2: dropout proxy — members whose rate-change cadence stalled
    # before the cutoff (documented approximation).
    surveyed = 0
    stalled = 0
    stall_floor = _iso(_to_date(cutoff) - timedelta(days=_DROPOUT_STALL_DAYS))
    for member in members:
        last = conn.execute(
            "SELECT max(effective_date) AS d FROM nadac "
            "WHERE ndc11 = ? AND effective_date < ?",
            (member, cutoff),
        ).fetchone()["d"]
        if last is None:
            continue
        surveyed += 1
        if last < stall_floor:
            stalled += 1
    dropout_fired = (
        surveyed >= 3 and (stalled / surveyed) >= _CLASS_DROPOUT_RATIO_FIRE
    )

    # Axis 3: dispensed-volume movement, latest complete pre-cutoff
    # quarter vs the same quarter a year earlier.
    volume_fired = False
    cutoff_day = _to_date(cutoff)
    cutoff_quarter = (cutoff_day.year, (cutoff_day.month - 1) // 3 + 1)
    quarters = conn.execute(
        f"SELECT year, quarter, sum(units) AS units FROM sdud "  # noqa: S608
        f"WHERE ndc11 IN ({placeholders}) GROUP BY year, quarter "
        "ORDER BY year, quarter",
        members,
    ).fetchall()
    usable = [
        row for row in quarters if (row["year"], row["quarter"]) < cutoff_quarter
    ]
    if usable:
        latest_quarter = usable[-1]
        prior = next(
            (
                row
                for row in usable
                if row["year"] == latest_quarter["year"] - 1
                and row["quarter"] == latest_quarter["quarter"]
            ),
            None,
        )
        if prior is not None and prior["units"]:
            change = (latest_quarter["units"] - prior["units"]) / prior["units"]
            volume_fired = (
                change <= _VOLUME_DECLINE_FIRE or change >= _VOLUME_SURGE_FIRE
            )

    # Axis 4: recalls in the trailing window before the cutoff.
    ndc9s = tuple(dict.fromkeys(member[:9] for member in members))
    ndc9_placeholders = ",".join("?" for _ in ndc9s)
    window_floor = _iso(_to_date(cutoff) - timedelta(days=_RECALL_WINDOW_DAYS))
    recalls = conn.execute(
        f"SELECT count(DISTINCT record_hash) AS n FROM enforcement "  # noqa: S608
        f"WHERE ndc9 IN ({ndc9_placeholders}) "
        "AND recall_initiation >= ? AND recall_initiation < ?",
        (*ndc9s, window_floor, cutoff),
    ).fetchone()["n"]

    return sum((drift_fired, dropout_fired, volume_fired, recalls > 0))


def lead_time_report(
    conn: sqlite3.Connection, *, since: str = "2020-01-01"
) -> dict[str, Any]:
    """Concordance + lead-time distribution over historical listings."""
    # HAVING, not WHERE: the aggregate must see the drug's ENTIRE
    # posting history, so a drug FIRST listed before `since` is excluded
    # outright rather than having a later RE-listing masquerade as a
    # first posting (which would credit the signals with "lead" over a
    # shortage FDA had already posted — review catch).
    listings = conn.execute(
        """
        SELECT drug_name_norm, min(initial_posting) AS first_posted
        FROM fda_list_history
        WHERE initial_posting IS NOT NULL
        GROUP BY drug_name_norm
        HAVING min(initial_posting) >= ?
        ORDER BY first_posted
        """,
        (since,),
    ).fetchall()

    cases: list[ListingCase] = []
    unmapped = 0
    for listing in listings:
        class_count, members = class_members_for_name(
            conn, listing["drug_name_norm"]
        )
        if not members:
            unmapped += 1
            continue
        at_posting = fingerprints_at(conn, members, listing["first_posted"])
        lead_days = 0
        if at_posting >= 2:
            posted = _to_date(listing["first_posted"])
            for step in range(1, _MAX_STEPS + 1):
                earlier = _iso(posted - timedelta(days=step * _STEP_DAYS))
                if fingerprints_at(conn, members, earlier) >= 2:
                    lead_days = step * _STEP_DAYS
                else:
                    break
        cases.append(
            ListingCase(
                drug_name_norm=listing["drug_name_norm"],
                first_posted=listing["first_posted"],
                class_count=class_count,
                member_ndc11s=members,
                fingerprints_at_posting=at_posting,
                lead_days=lead_days,
            )
        )

    concordant = [c for c in cases if c.fingerprints_at_posting >= 2]
    early = [c for c in concordant if c.lead_days > 0]
    leads = sorted(c.lead_days for c in early)
    # Cases still firing at the deepest step are right-censored: their
    # true lead exceeds the lookback. Counted so the median stays honest.
    censored = sum(1 for c in early if c.lead_days >= _STEP_DAYS * _MAX_STEPS)

    def _percentile(values: list[int], fraction: float) -> int | None:
        if not values:
            return None
        return values[min(len(values) - 1, int(fraction * len(values)))]

    return {
        "since": since,
        "listings_total": len(listings),
        "listings_mapped": len(cases),
        "listings_unmapped": unmapped,
        "concordant_at_posting": len(concordant),
        "concordance_rate": (len(concordant) / len(cases)) if cases else None,
        "early": len(early),
        "lead_days_median": _percentile(leads, 0.5),
        "lead_days_p25": _percentile(leads, 0.25),
        "lead_days_p75": _percentile(leads, 0.75),
        "lead_days_max": leads[-1] if leads else None,
        "right_censored": censored,
        "step_days": _STEP_DAYS,
        "max_lookback_days": _STEP_DAYS * _MAX_STEPS,
        "cases": [
            {
                "drug": case.drug_name_norm,
                "first_posted": case.first_posted,
                "classes": case.class_count,
                "members": len(case.member_ndc11s),
                "fingerprints_at_posting": case.fingerprints_at_posting,
                "lead_days": case.lead_days,
            }
            for case in cases
        ],
    }
