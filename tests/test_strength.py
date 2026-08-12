"""Strength canonicalization tests.

Every input string below is verbatim from the 2026-08-12 FDA NDC
Directory or the July 2026 Orange Book.
"""

from ndcres.strength import (
    normalize_ndc_strength,
    normalize_ob_strength,
    strengths_match,
    strip_fr_suffix,
)

_FR_ROW = (
    "0.5MG **Federal Register determination that product was not "
    "discontinued or withdrawn for safety or effectiveness reasons**"
)


class TestNdcDirectorySide:
    def test_patch_rate_leading_dot(self) -> None:
        assert normalize_ndc_strength(".05", "mg/d") == "UG24H:50"

    def test_menostar_microgram_unit(self) -> None:
        # Menostar files '14' + 'ug/d' while its Zydus generic files
        # '.014' + 'mg/d' — the same strength in different units.
        assert normalize_ndc_strength("14", "ug/d") == "UG24H:14"
        assert normalize_ndc_strength(".014", "mg/d") == "UG24H:14"

    def test_tablet_mass(self) -> None:
        assert normalize_ndc_strength("1", "mg/1") == "UG:1000"

    def test_spray_mass(self) -> None:
        assert normalize_ndc_strength("1.53", "mg/1") == "UG:1530"

    def test_gel_concentration_divigel(self) -> None:
        assert normalize_ndc_strength(".25", "mg/.25g") == "PCT:0.1;G:0.25"

    def test_gel_concentration_per_gram(self) -> None:
        assert normalize_ndc_strength("1", "mg/g") == "PCT:0.1;G:1"

    def test_gel_concentration_estrogel(self) -> None:
        assert normalize_ndc_strength(".75", "mg/1.25g") == "PCT:0.06;G:1.25"

    def test_unrecognized_goes_raw(self) -> None:
        assert normalize_ndc_strength("5", "furlongs").startswith("RAW:")


class TestOrangeBookSide:
    def test_patch_rate(self) -> None:
        assert normalize_ob_strength("0.05MG/24HR") == "UG24H:50"

    def test_menostar_rate(self) -> None:
        assert normalize_ob_strength("0.014MG/24HR") == "UG24H:14"

    def test_fr_suffix_stripped(self) -> None:
        assert strip_fr_suffix(_FR_ROW) == "0.5MG"
        assert normalize_ob_strength(_FR_ROW) == "UG:500"
        assert normalize_ob_strength(_FR_ROW) == normalize_ob_strength("0.5MG")

    def test_eq_base_prefix(self) -> None:
        assert normalize_ob_strength("EQ 0.05MG BASE/24HR") == "UG24H:50"

    def test_gel_packet(self) -> None:
        assert normalize_ob_strength("0.1% (0.25GM/PACKET)") == "PCT:0.1;G:0.25"

    def test_gel_activation(self) -> None:
        assert normalize_ob_strength("0.06% (1.25GM/ACTIVATION)") == "PCT:0.06;G:1.25"

    def test_spray(self) -> None:
        assert normalize_ob_strength("1.53MG/SPRAY") == "UG:1530"

    def test_mcg_tablet(self) -> None:
        assert normalize_ob_strength("25MCG") == "UG:25"


class TestCrossSourceJoins:
    def test_anchor_patch_matches(self) -> None:
        assert strengths_match(
            normalize_ndc_strength(".05", "mg/d"),
            normalize_ob_strength("0.05MG/24HR"),
        )

    def test_menostar_cross_unit_matches(self) -> None:
        assert strengths_match(
            normalize_ndc_strength("14", "ug/d"),
            normalize_ob_strength("0.014MG/24HR"),
        )

    def test_divigel_concentration_matches(self) -> None:
        assert strengths_match(
            normalize_ndc_strength(".25", "mg/.25g"),
            normalize_ob_strength("0.1% (0.25GM/PACKET)"),
        )

    def test_estrogel_concentration_matches(self) -> None:
        assert strengths_match(
            normalize_ndc_strength(".75", "mg/1.25g"),
            normalize_ob_strength("0.06% (1.25GM/ACTIVATION)"),
        )

    def test_evamist_matches(self) -> None:
        assert strengths_match(
            normalize_ndc_strength("1.53", "mg/1"),
            normalize_ob_strength("1.53MG/SPRAY"),
        )

    def test_different_strengths_do_not_match(self) -> None:
        assert not strengths_match(
            normalize_ndc_strength(".05", "mg/d"),
            normalize_ob_strength("0.0375MG/24HR"),
        )

    def test_rate_never_matches_mass(self) -> None:
        # 50 ug/24hr is not 50 ug per tablet.
        assert not strengths_match("UG24H:50", "UG:50")

    def test_none_never_matches(self) -> None:
        assert not strengths_match(None, "UG24H:50")
