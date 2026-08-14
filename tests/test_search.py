"""Structured search goldens (SPEC §8).

The defect that motivated the engine: "estradiol .05" — an ingredient
plus a strength — returned zero results from the old whole-string LIKE.
Every golden here is a query a real person typed or would type.
"""

from __future__ import annotations

import sqlite3

import pytest

from ndcres.search import _strength_keys, _tokenize, search

ANCHOR_NDC9 = "003784642"  # Mylan estradiol 0.05 patch
DOTTI_NDC9 = "651620993"  # Amneal Dotti 0.05 (AB1, same group)
LYLLANA_NDC9 = "651620149"  # Amneal Lyllana 0.05 (AB3)
DIVIGEL_HIT = "gel"


def _ndc9s(conn: sqlite3.Connection, query: str) -> set[str]:
    return {hit.ndc9 for hit in search(conn, query, limit=100)}


class TestTheMotivatingDefect:
    def test_estradiol_dot05_finds_the_patch_family(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        found = _ndc9s(loaded_conn, "estradiol .05")
        assert ANCHOR_NDC9 in found
        assert DOTTI_NDC9 in found
        assert LYLLANA_NDC9 in found

    def test_token_order_never_matters(self, loaded_conn: sqlite3.Connection) -> None:
        forward = search(loaded_conn, "estradiol .05", limit=100)
        reversed_query = search(loaded_conn, ".05 estradiol", limit=100)
        assert forward == reversed_query

    def test_unit_spellings_are_equivalent(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        base = _ndc9s(loaded_conn, "estradiol .05")
        assert _ndc9s(loaded_conn, "estradiol 0.05 mg") == base
        assert _ndc9s(loaded_conn, "estradiol 0.05mg") == base
        assert _ndc9s(loaded_conn, "50 mcg estradiol") == base

    def test_strength_actually_narrows(self, loaded_conn: sqlite3.Connection) -> None:
        everything = _ndc9s(loaded_conn, "estradiol")
        narrowed = _ndc9s(loaded_conn, "estradiol .05")
        assert narrowed < everything  # strict subset: other strengths exist


class TestTokenClasses:
    def test_form_word_narrows_to_patches(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        patches = search(loaded_conn, "estradiol patch", limit=100)
        assert patches, "form-word search returned nothing"
        families = {hit.form_family for hit in patches}
        assert families == {"patch"}
        assert ANCHOR_NDC9 in {hit.ndc9 for hit in patches}

    def test_brand_word(self, loaded_conn: sqlite3.Connection) -> None:
        assert DOTTI_NDC9 in _ndc9s(loaded_conn, "dotti")

    def test_labeler_word_narrows(self, loaded_conn: sqlite3.Connection) -> None:
        mylan_only = search(loaded_conn, "mylan estradiol", limit=100)
        assert mylan_only
        assert all(
            "MYLAN" in (hit.labeler or "").upper() for hit in mylan_only
        )

    def test_ndc_two_segment_hyphenated(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        assert ANCHOR_NDC9 in _ndc9s(loaded_conn, "0378-4642")

    def test_ndc_bare_eight_digits_hyphen_insensitive(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        assert ANCHOR_NDC9 in _ndc9s(loaded_conn, "03784642")

    def test_ndc_full_package_spelling(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        hits = search(loaded_conn, "0378-4642-26", limit=10)
        assert any(hit.rep_ndc11 == "00378464226" for hit in hits)

    def test_multi_token_miss_is_empty_not_garbage(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        assert search(loaded_conn, "estradiol zzqxv", limit=10) == ()

    def test_empty_query_is_empty(self, loaded_conn: sqlite3.Connection) -> None:
        assert search(loaded_conn, "   ", limit=10) == ()


class TestRankingAndShape:
    def test_deterministic(self, loaded_conn: sqlite3.Connection) -> None:
        first = search(loaded_conn, "estradiol", limit=50)
        second = search(loaded_conn, "estradiol", limit=50)
        assert first == second

    def test_product_grain_no_duplicate_products(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        hits = search(loaded_conn, "estradiol", limit=100)
        ndc9s = [hit.ndc9 for hit in hits]
        assert len(ndc9s) == len(set(ndc9s))

    def test_rep_package_is_resolvable(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        from ndcres.resolve import resolve

        hits = search(loaded_conn, "dotti", limit=5)
        assert hits and hits[0].rep_ndc11
        resolution = resolve(loaded_conn, hits[0].rep_ndc11)
        assert resolution is not None

    def test_te_code_surfaces(self, loaded_conn: sqlite3.Connection) -> None:
        anchor = [
            hit for hit in search(loaded_conn, "0378-4642", limit=10)
            if hit.ndc9 == ANCHOR_NDC9
        ]
        assert anchor and anchor[0].te_code == "AB1"

    def test_marketed_ranks_above_unmarketed_at_equal_text_score(self) -> None:
        # Pure ranking property, pinned without fixtures: identical text
        # match, marketed flag decides.
        from ndcres.search import _score

        class FakeRow:  # sqlite3.Row quacks like a mapping
            def __init__(self, data: dict[str, object]) -> None:
                self._data = data

            def __getitem__(self, key: str) -> object:
                return self._data[key]

        base = {
            "proprietary_name": "Dotti",
            "proprietary_suffix": None,
            "nonproprietary_name": "estradiol",
            "ingredient_set": "ESTRADIOL",
            "labeler_name": "X",
            "rx_name": None,
            "has_nadac": 0,
        }
        marketed = FakeRow({**base, "marketed": 1})
        discontinued = FakeRow({**base, "marketed": 0})
        assert _score(marketed, ["dotti"]) > _score(discontinued, ["dotti"])


class TestQueryParsingUnits:
    def test_tokenizer_joins_number_and_unit(self) -> None:
        tokens = _tokenize("estradiol 0.05 mg")
        kinds = [(token.kind, token.text) for token in tokens]
        assert ("strength", "0.05 mg") in kinds

    def test_strength_keys_mg_and_mcg_meet(self) -> None:
        from_mg, _ = _strength_keys("0.05", "mg")
        from_mcg, _ = _strength_keys("50", "mcg")
        assert "UG24H:50" in from_mg
        assert "UG24H:50" in from_mcg

    def test_bare_number_covers_both_readings(self) -> None:
        exact, _ = _strength_keys(".05", None)
        assert "UG24H:50" in exact  # as mg/day
        assert "UG24H:0.05" in exact  # as µg (unlikely but the user said no unit)

    def test_percent_becomes_prefix(self) -> None:
        exact, prefixes = _strength_keys("0.06", "%")
        assert not exact
        assert prefixes == {"PCT:0.06;"}

    def test_unparseable_number_matches_nothing(self) -> None:
        exact, prefixes = _strength_keys("..", None)
        assert exact == set() and prefixes == set()


class TestSearchDocRebuild:
    def test_docs_exist_for_every_product(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        products = loaded_conn.execute("SELECT COUNT(*) FROM product").fetchone()[0]
        docs = loaded_conn.execute("SELECT COUNT(*) FROM search_doc").fetchone()[0]
        assert docs == products > 0

    def test_anchor_doc_derivations(self, loaded_conn: sqlite3.Connection) -> None:
        row = loaded_conn.execute(
            "SELECT * FROM search_doc WHERE ndc9 = ?", (ANCHOR_NDC9,)
        ).fetchone()
        assert row is not None
        assert row["te_code"] == "AB1"
        assert row["marketed"] == 1
        assert row["has_nadac"] == 1
        assert row["rep_ndc11"] == "00378464226"
        assert row["rx_name"] and "estradiol" in row["rx_name"].lower()

    def test_docs_carry_provenance(self, loaded_conn: sqlite3.Connection) -> None:
        orphans = loaded_conn.execute(
            """
            SELECT COUNT(*) FROM search_doc s
            WHERE NOT EXISTS (
              SELECT 1 FROM source_run r WHERE r.run_id = s.run_id
            )
            """
        ).fetchone()[0]
        assert orphans == 0
