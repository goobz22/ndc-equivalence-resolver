"""Explain tests — the source-cited rationale between two NDCs."""

import sqlite3

from ndcres.explain import explain


class TestAnchorVsDotti:
    def test_verdict_is_direct_substitute(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        explanation = explain(loaded_conn, "00378-4642-26", "65162-993-08")
        assert explanation.verdict.tier == "T1"
        assert explanation.verdict.reasons == ()

    def test_every_dimension_line_cites_a_source(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        explanation = explain(loaded_conn, "0378-4642-26", "65162-993-08")
        assert all(line.source for line in explanation.lines)

    def test_te_dimension_shows_the_group(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        explanation = explain(loaded_conn, "0378-4642-26", "65162-993-08")
        te_line = next(line for line in explanation.lines if "TE code" in line.dimension)
        assert "AB1" in te_line.left
        assert "AB1" in te_line.right
        assert te_line.same is True


class TestAnchorVsLyllana:
    def test_verdict_requires_prescriber(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        explanation = explain(loaded_conn, "0378-4642-26", "65162-149-08")
        assert explanation.verdict.tier == "T3"
        assert explanation.verdict.reasons == ("different-te-subgroup",)

    def test_te_dimension_differs_while_everything_else_matches(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        explanation = explain(loaded_conn, "0378-4642-26", "65162-149-08")
        by_dim = {line.dimension: line for line in explanation.lines}
        assert by_dim["active ingredient(s)"].same is True
        assert by_dim["delivery form family"].same is True
        assert by_dim["strength"].same is True
        assert by_dim["application schedule"].same is True
        assert by_dim["package size"].same is True
        assert by_dim["TE code (Orange Book)"].same is False  # the whole story


class TestMenostarSpecialCase:
    def test_te_source_mentions_the_special_case(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        explanation = explain(loaded_conn, "50419-455-04", "50419-451-04")
        te_line = next(line for line in explanation.lines if "TE code" in line.dimension)
        assert "special-cased" in te_line.source
        # Menostar joins to its TRUE application (N021674), not Climara's.
        assert "NDA021674" in te_line.left
