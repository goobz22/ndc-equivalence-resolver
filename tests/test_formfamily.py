"""Form-family mapping tests — the cross-source delivery-class vocabulary."""

from ndcres.formfamily import form_family, ob_form_family


class TestNdcDirectoryStrings:
    def test_all_three_patch_spellings_map_to_patch(self) -> None:
        assert form_family("PATCH", "TRANSDERMAL") == "patch"
        assert form_family("PATCH, EXTENDED RELEASE", "TRANSDERMAL") == "patch"
        assert form_family("FILM, EXTENDED RELEASE", "TRANSDERMAL") == "patch"

    def test_buccal_film_is_not_a_patch(self) -> None:
        assert form_family("FILM, EXTENDED RELEASE", "BUCCAL") != "patch"

    def test_gel_regardless_of_route_disagreement(self) -> None:
        # Divigel is TOPICAL in the NDC Directory, TRANSDERMAL in the OB.
        assert form_family("GEL", "TOPICAL") == "gel"
        assert form_family("GEL", "TRANSDERMAL") == "gel"
        assert form_family("GEL, METERED", "TOPICAL") == "gel"

    def test_spray(self) -> None:
        assert form_family("SPRAY", "TRANSDERMAL") == "spray"

    def test_oral_tablet(self) -> None:
        assert form_family("TABLET", "ORAL") == "oral-solid"

    def test_unknown_forms_are_distinct_not_none(self) -> None:
        assert form_family("LOZENGE", "ORAL") == "other:lozenge"

    def test_missing_form_is_none(self) -> None:
        assert form_family(None, "ORAL") is None
        assert form_family("", "ORAL") is None


class TestOrangeBookStrings:
    def test_system_transdermal(self) -> None:
        assert ob_form_family("SYSTEM;TRANSDERMAL") == "patch"

    def test_film_er_transdermal(self) -> None:
        assert ob_form_family("FILM, EXTENDED RELEASE;TRANSDERMAL") == "patch"

    def test_gels(self) -> None:
        assert ob_form_family("GEL;TRANSDERMAL") == "gel"
        assert ob_form_family("GEL, METERED;TRANSDERMAL") == "gel"

    def test_spray(self) -> None:
        assert ob_form_family("SPRAY;TRANSDERMAL") == "spray"

    def test_oral(self) -> None:
        assert ob_form_family("TABLET;ORAL") == "oral-solid"

    def test_cross_source_patch_agreement(self) -> None:
        # The whole point: NDC 'PATCH' and OB 'SYSTEM;TRANSDERMAL' and OB
        # 'FILM, EXTENDED RELEASE;TRANSDERMAL' are all one family.
        assert (
            form_family("PATCH", "TRANSDERMAL")
            == ob_form_family("SYSTEM;TRANSDERMAL")
            == ob_form_family("FILM, EXTENDED RELEASE;TRANSDERMAL")
        )
