"""PACKAGEDESCRIPTION parser tests.

Every description below is verbatim (including irregular double spaces
and trailing spaces) from the 2026-08-12 FDA NDC Directory.
"""

from ndcres.packaging import parse_package_description


class TestPatchCartons:
    def test_anchor_mylan_twice_weekly(self) -> None:
        info = parse_package_description(
            "8 POUCH in 1 CARTON (0378-4642-26)  / 1 PATCH in 1 POUCH "
            "(0378-4642-16)  / 3.5 d in 1 PATCH"
        )
        assert info.pack_count == 8
        assert info.wear_hours == 84.0

    def test_climara_once_weekly(self) -> None:
        info = parse_package_description(
            "4 PATCH in 1 CARTON (50419-451-04)  / 7 d in 1 PATCH (50419-451-01) "
        )
        assert info.pack_count == 4
        assert info.wear_hours == 168.0

    def test_amneal_one_day_pouch_is_not_wear_evidence(self) -> None:
        # Amneal rows say "1 d in 1 POUCH" — junk data, not a wear duration.
        info = parse_package_description(
            "8 POUCH in 1 CARTON (65162-993-08)  / 1 d in 1 POUCH (65162-993-04) "
        )
        assert info.pack_count == 8
        assert info.wear_hours is None

    def test_vivelle_dot_box_container(self) -> None:
        info = parse_package_description(
            "8 POUCH in 1 BOX (66758-147-83)  / 1 PATCH in 1 POUCH "
            "(66758-147-58)  / 3.5 d in 1 PATCH"
        )
        assert info.pack_count == 8
        assert info.wear_hours == 84.0

    def test_minivelle_packet_container(self) -> None:
        info = parse_package_description(
            "8 POUCH in 1 PACKET (68968-6650-8)  / 1 d in 1 POUCH"
        )
        assert info.pack_count == 8
        assert info.wear_hours is None

    def test_single_spaced_variant_without_inner_code(self) -> None:
        info = parse_package_description(
            "4 POUCH in 1 CARTON (50090-7611-0)  / 1 PATCH in 1 POUCH / 7 d in 1 PATCH"
        )
        assert info.pack_count == 4
        assert info.wear_hours == 168.0

    def test_multiplicative_nesting(self) -> None:
        info = parse_package_description("2 POUCH in 1 CARTON / 4 PATCH in 1 POUCH")
        assert info.pack_count == 8


class TestNonPatchForms:
    def test_evamist_spray_vial(self) -> None:
        info = parse_package_description("56 SPRAY in 1 VIAL, MULTI-DOSE (0574-2067-27) ")
        assert info.pack_count == 56
        assert info.pack_unit == "SPRAY"

    def test_gel_pump_bottle_counts_bottles_not_grams(self) -> None:
        info = parse_package_description(
            "1 BOTTLE, PUMP in 1 CARTON (21922-015-40)  / 50 g in 1 BOTTLE, PUMP"
        )
        assert info.pack_count == 1

    def test_divigel_packets(self) -> None:
        info = parse_package_description(
            "30 PACKET in 1 CARTON (68025-065-30)  / .25 g in 1 PACKET"
        )
        assert info.pack_count == 30

    def test_tablet_bottle(self) -> None:
        info = parse_package_description("100 TABLET in 1 BOTTLE (0555-0886-02) ")
        assert info.pack_count == 100

    def test_measure_dispensed_has_no_count(self) -> None:
        info = parse_package_description(".21 L in 1 CYLINDER (10014-001-07) ")
        assert info.pack_count is None


class TestDegenerateInput:
    def test_empty(self) -> None:
        info = parse_package_description("")
        assert info.pack_count is None
        assert info.wear_hours is None
        assert info.levels == ()

    def test_none(self) -> None:
        assert parse_package_description(None).pack_count is None

    def test_unparseable_text_does_not_crash(self) -> None:
        info = parse_package_description("A MYSTERY BOX OF UNKNOWN PROVENANCE")
        assert info.pack_count is None
