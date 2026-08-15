"""Watch feeds (SPEC §10.4): RSS over sweep-to-sweep verdict changes.

Retention is the instrument's memory problem in reverse: the archive
remembers for us; feeds let a READER remember a drug. Two channels:

- gaps feed: classes that ENTERED or LEFT the unlisted-constraint set
  (or the FDA list) between the two most recent sweeps in the serving
  database.
- class feed: one class's verdict changes across the exported sweep
  window, plus a current-state item.

Built with xml.etree (never hand-templated strings: ingredient names
contain ``'()%&`` — hand-templating means hand-escaping, exactly the
bug class ElementTree kills). Output is deterministic: dates derive
from sweep run_date (dataset-relative, never wall-clock), guids are
stable functions of (slug, sweep_id, transition), and items are emitted
in a fixed sort order.

A feed URL must ALWAYS parse: fewer than two sweeps yields a VALID
EMPTY channel, never an error page.
"""

from __future__ import annotations

import os
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import format_datetime

from .classpage import class_slug, human_strength
from .signals import VERDICT_CONSTRAINT, VERDICT_FDA_LISTED


def _site_base() -> str:
    return os.environ.get(
        "NDCRES_SITE_BASE", "https://ndc-equivalence-resolver.vercel.app"
    )


def _rfc822(iso_date: str) -> str:
    parsed = date.fromisoformat(iso_date)
    return format_datetime(
        datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)
    )


@dataclass(frozen=True)
class FeedItem:
    title: str
    link: str
    guid: str
    pub_date: str  # RFC 2822, derived from sweep run_date
    description: str


def _class_label(row: sqlite3.Row) -> str:
    ingredients = " / ".join(
        part.title() for part in row["ingredient_set"].split(";")
    )
    form = row["df_route"].replace(";", " ").lower()
    return (
        f"{ingredients} {human_strength(row['strength_norm'])} ({form}, "
        f"TE {row['te_code']})"
    )


def _sweep_rows(
    conn: sqlite3.Connection, sweep_id: int
) -> dict[tuple[str, str, str, str], sqlite3.Row]:
    return {
        (
            row["ingredient_set"],
            row["df_route"],
            row["strength_norm"],
            row["te_code"],
        ): row
        for row in conn.execute(
            "SELECT * FROM sweep_class WHERE sweep_id = ?", (sweep_id,)
        )
    }


_TRANSITIONS: tuple[tuple[str, str], ...] = (
    ("entered-constraint", "now shows evidence consistent with a supply "
     "constraint while absent from FDA's shortage list"),
    ("left-constraint", "no longer shows the unlisted-constraint pattern"),
    ("entered-fda-list", "gained an active record on FDA's shortage list"),
    ("left-fda-list", "no longer carries an active FDA shortage-list record"),
)


def _transition(previous: str | None, current: str | None) -> str | None:
    if current is not None and previous != current:
        if current == VERDICT_CONSTRAINT:
            return "entered-constraint"
        if current == VERDICT_FDA_LISTED:
            return "entered-fda-list"
    if previous is not None and previous != current:
        if previous == VERDICT_CONSTRAINT:
            return "left-constraint"
        if previous == VERDICT_FDA_LISTED:
            return "left-fda-list"
    return None


def gaps_transitions(conn: sqlite3.Connection) -> list[FeedItem]:
    sweeps = [
        (row["sweep_id"], row["run_date"])
        for row in conn.execute(
            "SELECT sweep_id, run_date FROM sweep_run "
            "ORDER BY sweep_id DESC LIMIT 2"
        )
    ]
    if len(sweeps) < 2:
        return []
    (current_id, current_date), (previous_id, _) = sweeps
    current_rows = _sweep_rows(conn, current_id)
    previous_rows = _sweep_rows(conn, previous_id)
    descriptions = dict(_TRANSITIONS)
    items: list[FeedItem] = []
    for key in sorted(set(current_rows) | set(previous_rows)):
        current = current_rows.get(key)
        previous = previous_rows.get(key)
        change = _transition(
            previous["verdict"] if previous is not None else None,
            current["verdict"] if current is not None else None,
        )
        if change is None:
            continue
        anchor = current if current is not None else previous
        assert anchor is not None
        slug = class_slug(*key)
        items.append(
            FeedItem(
                title=f"{_class_label(anchor)}: {change.replace('-', ' ')}",
                link=f"{_site_base()}/class/{slug}",
                guid=f"{slug}@{current_id}:{change}",
                pub_date=_rfc822(current_date),
                description=(
                    f"This equivalence class {descriptions[change]} in the "
                    f"weekly sweep dated {current_date}. Probabilistic "
                    "evidence from public data - never a statement of "
                    "availability."
                ),
            )
        )
    return items


def class_history_items(
    conn: sqlite3.Connection, slug: str
) -> list[FeedItem] | None:
    """Verdict-change items for one class; None if the slug is unknown."""
    from .classpage import slug_index

    key = slug_index(conn).get(slug)
    if key is None:
        return None
    rows = conn.execute(
        """
        SELECT c.*, r.run_date FROM sweep_class c
        JOIN sweep_run r ON r.sweep_id = c.sweep_id
        WHERE c.ingredient_set = ? AND c.df_route = ?
          AND c.strength_norm = ? AND c.te_code = ?
        ORDER BY c.sweep_id
        """,
        key,
    ).fetchall()
    if not rows:
        return []
    items: list[FeedItem] = []
    previous_verdict: str | None = None
    for row in rows:
        if row["verdict"] != previous_verdict and previous_verdict is not None:
            items.append(
                FeedItem(
                    title=(
                        f"{_class_label(row)}: verdict changed to "
                        f"{row['verdict']}"
                    ),
                    link=f"{_site_base()}/class/{slug}",
                    guid=f"{slug}@{row['sweep_id']}:verdict-change",
                    pub_date=_rfc822(row["run_date"]),
                    description=(
                        f"Sweep dated {row['run_date']}: verdict moved from "
                        f"{previous_verdict} to {row['verdict']} "
                        f"({row['fingerprints']} evidence fingerprint(s))."
                    ),
                )
            )
        previous_verdict = row["verdict"]
    latest = rows[-1]
    items.append(
        FeedItem(
            title=(
                f"{_class_label(latest)}: current verdict "
                f"{latest['verdict']}"
            ),
            link=f"{_site_base()}/class/{slug}",
            guid=f"{slug}@{latest['sweep_id']}:current",
            pub_date=_rfc822(latest["run_date"]),
            description=(
                f"As of the sweep dated {latest['run_date']}: "
                f"{latest['verdict']} with {latest['fingerprints']} "
                "evidence fingerprint(s). Probabilistic evidence from "
                "public data - never a statement of availability."
            ),
        )
    )
    items.reverse()  # newest first, the RSS convention
    return items


def render_rss(
    title: str, link: str, description: str, items: list[FeedItem]
) -> bytes:
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = link
    ET.SubElement(channel, "description").text = description
    for item in items:
        element = ET.SubElement(channel, "item")
        ET.SubElement(element, "title").text = item.title
        ET.SubElement(element, "link").text = item.link
        guid = ET.SubElement(element, "guid", isPermaLink="false")
        guid.text = item.guid
        ET.SubElement(element, "pubDate").text = item.pub_date
        ET.SubElement(element, "description").text = item.description
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)
