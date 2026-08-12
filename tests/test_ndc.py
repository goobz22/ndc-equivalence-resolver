"""NDC normalization tests.

Anchor examples are real codes from the 2026-08-12 FDA NDC Directory —
one per as-filed segmentation shape.
"""

import pytest

from ndcres.ndc import (
    NdcError,
    ndc9_of,
    ndc11_to_hipaa,
    parse_ndc,
    product_ndc_to_ndc9,
)


class TestHyphenatedShapes:
    def test_4_4_2_pads_labeler(self) -> None:
        query = parse_ndc("0378-4642-26")  # Mylan estradiol twice-weekly
        assert query.candidates == ("00378464226",)
        assert query.shape == "4-4-2"
        assert not query.ambiguous

    def test_5_3_2_pads_product(self) -> None:
        query = parse_ndc("65162-993-08")  # Amneal Dotti
        assert query.candidates == ("65162099308",)
        assert query.shape == "5-3-2"

    def test_5_4_1_pads_package(self) -> None:
        query = parse_ndc("68968-6650-8")  # Noven Minivelle
        assert query.candidates == ("68968665008",)
        assert query.shape == "5-4-1"

    def test_11_digit_hyphenated_hipaa_form(self) -> None:
        query = parse_ndc("00378-4642-26")
        assert query.ndc11 == "00378464226"
        assert query.shape == "5-4-2"

    def test_brief_style_reconstructed_hyphenation_accepted(self) -> None:
        # "65162-0149-08" exists in no FDA file (real form is 65162-149-08),
        # but as an 11-digit 5-4-2 spelling it normalizes identically.
        assert parse_ndc("65162-0149-08").ndc11 == parse_ndc("65162-149-08").ndc11

    def test_invalid_segmentation_rejected(self) -> None:
        with pytest.raises(NdcError):
            parse_ndc("123-45-6789")

    def test_two_segments_rejected(self) -> None:
        with pytest.raises(NdcError):
            parse_ndc("0378-4642")


class TestBareDigits:
    def test_bare_11_is_unambiguous(self) -> None:
        query = parse_ndc("00378464226")
        assert query.ndc11 == "00378464226"
        assert query.shape is None

    def test_bare_10_is_ambiguous_with_three_candidates(self) -> None:
        query = parse_ndc("0378464226")
        assert query.ambiguous
        assert query.candidates == (
            "00378464226",  # read as 4-4-2
            "03784064226",  # read as 5-3-2
            "03784642206",  # read as 5-4-1
        )
        with pytest.raises(NdcError, match="ambiguous"):
            _ = query.ndc11

    def test_bare_10_duplicate_candidates_collapse(self) -> None:
        query = parse_ndc("0000000000")
        assert query.candidates == ("00000000000",)
        assert not query.ambiguous

    @pytest.mark.parametrize("bad", ["", "  ", "12345", "123456789012", "03784x4226"])
    def test_rejects_non_ndc_strings(self, bad: str) -> None:
        with pytest.raises(NdcError):
            parse_ndc(bad)


class TestRoundTrips:
    @pytest.mark.parametrize(
        "filed",
        ["0378-4642-26", "65162-993-08", "65162-149-08", "68968-6650-8", "50419-451-04"],
    )
    def test_filed_to_ndc11_to_hipaa_is_stable(self, filed: str) -> None:
        ndc11 = parse_ndc(filed).ndc11
        hipaa = ndc11_to_hipaa(ndc11)
        assert parse_ndc(hipaa).ndc11 == ndc11
        assert parse_ndc(ndc11).ndc11 == ndc11

    def test_hipaa_rendering(self) -> None:
        assert ndc11_to_hipaa("00378464226") == "00378-4642-26"


class TestGrainHelpers:
    def test_ndc9_of(self) -> None:
        assert ndc9_of("00378464226") == "003784642"

    def test_product_ndc_4_4(self) -> None:
        assert product_ndc_to_ndc9("0378-4642") == "003784642"

    def test_product_ndc_5_3(self) -> None:
        assert product_ndc_to_ndc9("65162-149") == "651620149"

    def test_product_ndc_5_4(self) -> None:
        assert product_ndc_to_ndc9("68968-6650") == "689686650"

    def test_product_ndc_rejects_garbage(self) -> None:
        with pytest.raises(NdcError):
            product_ndc_to_ndc9("0378-4642-26")
