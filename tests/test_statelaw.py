"""State substitution law (SPEC §20): curated, statute-cited, honest.

The rows are curated at research time; these tests pin the contract:
complete coverage, verifiable citations, and the planted goldens from
the recorded research pass (statute-verified facts an editing mistake
would silently corrupt).
"""

from __future__ import annotations

import re

from ndcres.statelaw import (
    DISCLAIMER,
    STATE_RULES,
    SUBSTITUTION_KINDS,
    rule_for,
    statelaw_payload,
)

ALL_JURISDICTIONS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA",
    "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY",
    "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX",
    "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}


class TestCoverage:
    def test_all_51_jurisdictions_present_exactly_once(self) -> None:
        codes = [rule.state for rule in STATE_RULES]
        assert sorted(codes) == sorted(ALL_JURISDICTIONS)

    def test_row_format(self) -> None:
        for rule in STATE_RULES:
            assert rule.substitution in SUBSTITUTION_KINDS, rule.state
            assert rule.statute_url.startswith("https://"), rule.state
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", rule.as_of), rule.state
            assert rule.prescriber_override, rule.state
            assert rule.statute_citation, rule.state
            assert rule.name, rule.state

    def test_unverified_rows_are_the_exception(self) -> None:
        # The research standard: verify against the statute or two
        # agreeing citable secondaries. A majority-unverified table
        # means the research pass failed — refuse to ship it.
        unverified = [
            r.state for r in STATE_RULES if r.substitution == "unverified"
        ]
        assert len(unverified) <= 8, unverified


class TestLookup:
    def test_lookup_normalizes(self) -> None:
        assert rule_for(" fl ") == rule_for("FL")

    def test_unknown_returns_none(self) -> None:
        assert rule_for("XX") is None
        assert rule_for("") is None


class TestGoldens:
    """Statute-verified facts from the recorded research pass."""

    def test_florida_mandatory_with_medically_necessary(self) -> None:
        florida = rule_for("FL")
        assert florida is not None
        assert florida.substitution == "mandatory"
        assert "MEDICALLY NECESSARY" in florida.prescriber_override
        assert "465.025" in florida.statute_citation
        assert florida.patient_may_refuse is True

    def test_new_york_daw_box(self) -> None:
        new_york = rule_for("NY")
        assert new_york is not None
        assert new_york.substitution == "mandatory"
        assert "daw" in new_york.prescriber_override.lower()
        assert "6810" in new_york.statute_citation

    def test_massachusetts_mandatory(self) -> None:
        massachusetts = rule_for("MA")
        assert massachusetts is not None
        assert massachusetts.substitution == "mandatory"

    def test_connecticut_rule_present_and_cited(self) -> None:
        connecticut = rule_for("CT")
        assert connecticut is not None
        assert connecticut.substitution in ("mandatory", "permissive")
        assert connecticut.statute_citation


class TestPayload:
    def test_payload_shape_and_disclaimer(self) -> None:
        payload = statelaw_payload()
        assert payload["disclaimer"] == DISCLAIMER
        assert "Not legal advice" in payload["disclaimer"]
        assert len(payload["states"]) == len(STATE_RULES)
        if payload["states"]:
            first = payload["states"][0]
            assert set(first) == {
                "state", "name", "substitution", "patient_consent_required",
                "patient_notification_required", "patient_may_refuse",
                "prescriber_override", "statute_citation", "statute_url",
                "as_of",
            }
