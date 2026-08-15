"""Canonical class addresses (SPEC §14/§15): slugs that cannot collide."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ndcres.classpage import class_slug, human_strength, slug_index
from ndcres.db import connect
from ndcres.ingest import refresh
from ndcres.sweep import persist_sweep, run_sweep

FIXTURES = Path(__file__).parent / "fixtures" / "full"


class TestHumanStrength:
    def test_patch_rate(self) -> None:
        assert human_strength("UG24H:50") == "50 mcg/24hr"

    def test_mass_milligrams(self) -> None:
        assert human_strength("UG:300000") == "300 mg"

    def test_mass_micrograms(self) -> None:
        assert human_strength("UG:500") == "500 mcg"

    def test_gel_concentration(self) -> None:
        assert human_strength("PCT:0.06;G:1.25") == "0.06%"

    def test_raw_is_honestly_labeled(self) -> None:
        assert human_strength("RAW:40MG/ML") == "40MG/ML (as filed)"

    def test_empty(self) -> None:
        assert human_strength("") == "?"


class TestClassSlug:
    def test_deterministic(self) -> None:
        first = class_slug("ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:50", "AB1")
        second = class_slug("ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:50", "AB1")
        assert first == second

    def test_readable_head_plus_hash_suffix(self) -> None:
        slug = class_slug("ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:50", "AB1")
        assert slug.startswith("estradiol-system-transdermal-50-mcg-24hr-ab1-")
        head, _, suffix = slug.rpartition("-")
        assert len(suffix) == 8 and all(c in "0123456789abcdef" for c in suffix)

    def test_punctuation_only_keys_stay_distinct(self) -> None:
        # The planted collision: slug cleaning alone maps both to the
        # same head — the hash suffix must keep them distinct addresses.
        left = class_slug("X", "SOLUTION;ORAL", "RAW:0.05%", "AA")
        right = class_slug("X", "SOLUTION;ORAL", "RAW:005", "AA")
        assert left != right

    def test_long_keys_capped_but_unique(self) -> None:
        many = "|".join(f"INGREDIENT{i}" for i in range(13))
        slug_a = class_slug(many, "SOLUTION;INTRAVENOUS", "RAW:2 IU/ML", "AP")
        slug_b = class_slug(many, "SOLUTION;INTRAVENOUS", "RAW:3 IU/ML", "AP")
        assert len(slug_a) <= 95
        assert slug_a != slug_b

    def test_url_safe(self) -> None:
        slug = class_slug(
            "RIBOFLAVIN 5'-PHOSPHATE SODIUM|ASCORBIC ACID",
            "INJECTABLE;INTRAVENOUS",
            "RAW:2,300 IU/VIAL",
            "AP",
        )
        assert all(c.isalnum() or c == "-" for c in slug)


class TestSlugIndex:
    @pytest.fixture()
    def swept(self, tmp_path: Path) -> sqlite3.Connection:
        conn = connect(tmp_path / "t.db")
        refresh(conn, from_dir=FIXTURES)
        persist_sweep(conn, run_sweep(conn))
        return conn

    def test_unique_across_fixture_universe(
        self, swept: sqlite3.Connection
    ) -> None:
        index = slug_index(swept)
        classes = swept.execute(
            "SELECT count(*) FROM sweep_class WHERE sweep_id = "
            "(SELECT max(sweep_id) FROM sweep_run)"
        ).fetchone()[0]
        assert len(index) == classes > 0  # one slug per class, no collisions

    def test_anchor_class_addressable(self, swept: sqlite3.Connection) -> None:
        index = slug_index(swept)
        anchor_slug = class_slug(
            "ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:50", "AB1"
        )
        entry = index[anchor_slug]
        assert entry["rep_ndc11"] == "00378464226"

    def test_empty_db_empty_index(self, tmp_path: Path) -> None:
        conn = connect(tmp_path / "empty.db")
        assert slug_index(conn) == {}
