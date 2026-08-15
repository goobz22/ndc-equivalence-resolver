"""Watch feeds (SPEC §10.4): valid always, deterministic, honest.

A feed URL must ALWAYS parse (readers poll unattended) — fewer than two
sweeps yields a valid empty channel, never an error. Items derive from
sweep run_date (dataset-relative) with stable guids, so a reader never
sees a duplicate or a wall-clock date.
"""

from __future__ import annotations

import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from ndcres.db import connect
from ndcres.feeds import class_history_items, gaps_transitions, render_rss
from ndcres.ingest import refresh
from ndcres.signals import VERDICT_CONSTRAINT, VERDICT_QUIET
from ndcres.sweep import persist_sweep, run_sweep

FIXTURES = Path(__file__).parent / "fixtures" / "full"


@pytest.fixture()
def swept_conn(tmp_path: Path) -> sqlite3.Connection:
    conn = connect(tmp_path / "t.db")
    refresh(conn, from_dir=FIXTURES)
    persist_sweep(conn, run_sweep(conn))
    return conn


def _resweep_with_flip(conn: sqlite3.Connection) -> None:
    """Persist a second sweep, then plant a verdict flip in it."""
    sweep_id = persist_sweep(conn, run_sweep(conn))
    with conn:
        conn.execute(
            "UPDATE sweep_class SET verdict = ? WHERE sweep_id = ? AND "
            "ingredient_set = 'ESTRADIOL' AND te_code = 'AB1'",
            (VERDICT_QUIET, sweep_id),
        )


class TestGapsTransitions:
    def test_single_sweep_yields_valid_empty_channel(
        self, swept_conn: sqlite3.Connection
    ) -> None:
        items = gaps_transitions(swept_conn)
        assert items == []
        body = render_rss("t", "https://example.com", "d", items)
        parsed = ET.fromstring(body)
        assert parsed.tag == "rss"
        assert parsed.find("channel/title") is not None
        assert parsed.findall("channel/item") == []

    def test_planted_flip_produces_transition_item(
        self, swept_conn: sqlite3.Connection
    ) -> None:
        _resweep_with_flip(swept_conn)
        items = gaps_transitions(swept_conn)
        left = [i for i in items if "left-constraint" in i.guid]
        assert len(left) == 1
        item = left[0]
        assert "Estradiol" in item.title
        assert item.link.startswith("https://")
        assert "/class/" in item.link
        # Dataset-relative date: the sweep's run_date, never wall-clock.
        run_date = swept_conn.execute(
            "SELECT run_date FROM sweep_run ORDER BY sweep_id DESC LIMIT 1"
        ).fetchone()["run_date"]
        assert run_date[:4] in item.pub_date

    def test_no_change_no_items(self, swept_conn: sqlite3.Connection) -> None:
        persist_sweep(swept_conn, run_sweep(swept_conn))
        assert gaps_transitions(swept_conn) == []

    def test_deterministic_bytes(self, swept_conn: sqlite3.Connection) -> None:
        _resweep_with_flip(swept_conn)
        first = render_rss("t", "https://example.com", "d",
                           gaps_transitions(swept_conn))
        second = render_rss("t", "https://example.com", "d",
                            gaps_transitions(swept_conn))
        assert first == second


class TestClassFeed:
    def test_unknown_slug_returns_none(
        self, swept_conn: sqlite3.Connection
    ) -> None:
        assert class_history_items(swept_conn, "nope-00000000") is None

    def test_history_carries_change_and_current(
        self, swept_conn: sqlite3.Connection
    ) -> None:
        from ndcres.classpage import slug_index

        _resweep_with_flip(swept_conn)
        slug = next(
            s for s, key in slug_index(swept_conn).items()
            if key[0] == "ESTRADIOL" and key[3] == "AB1"
        )
        items = class_history_items(swept_conn, slug)
        assert items is not None
        guids = [item.guid for item in items]
        assert any(":current" in g for g in guids)
        assert any(":verdict-change" in g for g in guids)
        # Newest first; language discipline holds in rendered output.
        assert ":current" in items[0].guid
        body = render_rss("t", "https://example.com", "d", items).decode()
        assert "available" not in body.split("statement of availability")[0]

    def test_escaping_survives_hostile_names(self) -> None:
        # The reason ElementTree, not string templates: names with &<>'
        from ndcres.feeds import FeedItem

        body = render_rss(
            "t & u <v>", "https://example.com", "d",
            [FeedItem(
                title="0.05% w/w & <gel>",
                link="https://example.com/class/x",
                guid="x@1:entered-constraint",
                pub_date="Thu, 13 Aug 2026 00:00:00 +0000",
                description="5% & 3%",
            )],
        )
        parsed = ET.fromstring(body)  # must parse cleanly
        item = parsed.find("channel/item")
        assert item is not None
        title = item.find("title")
        assert title is not None and title.text == "0.05% w/w & <gel>"


class TestExportWindow:
    def test_oldest_sweep_excluded_beyond_13(self, tmp_path: Path) -> None:
        import shutil

        from ndcres.export import export_web_db

        source_path = tmp_path / "main.db"
        conn = connect(source_path)
        refresh(conn, from_dir=FIXTURES)
        for _ in range(14):
            persist_sweep(conn, run_sweep(conn))
        conn.close()
        dest = tmp_path / "web.db"
        export_web_db(source_path, dest)
        from ndcres.db import connect_readonly

        web = connect_readonly(dest)
        try:
            ids = [r["sweep_id"] for r in web.execute(
                "SELECT sweep_id FROM sweep_run ORDER BY sweep_id")]
            assert len(ids) == 13
            assert 1 not in ids  # the oldest fell out of the window
            assert max(ids) == 14
            class_sweeps = web.execute(
                "SELECT count(DISTINCT sweep_id) FROM sweep_class"
            ).fetchone()[0]
            assert class_sweeps == 13
        finally:
            web.close()
