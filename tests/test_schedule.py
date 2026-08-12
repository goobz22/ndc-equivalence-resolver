"""Schedule-derivation ladder tests."""

from ndcres.schedule import ONCE_WEEKLY, TWICE_WEEKLY, derive_schedule


class TestIndividualRungs:
    def test_rxnorm_scd_84hr_is_twice_weekly(self) -> None:
        result = derive_schedule(
            rx_scd_name="84 HR estradiol 0.00208 MG/HR Transdermal System"
        )
        assert result.value == TWICE_WEEKLY
        assert result.confidence == "rxnorm-scd"
        assert not result.conflict

    def test_rxnorm_scd_168hr_is_once_weekly(self) -> None:
        result = derive_schedule(
            rx_scd_name="168 HR estradiol 0.00208 MG/HR Transdermal System"
        )
        assert result.value == ONCE_WEEKLY

    def test_rxnorm_other_durations_are_not_mapped(self) -> None:
        # 72 HR (fentanyl-style) is neither weekly schedule.
        result = derive_schedule(rx_scd_name="72 HR fentanyl 0.075 MG/HR Transdermal System")
        assert result.value is None

    def test_pack_wear_duration(self) -> None:
        assert derive_schedule(wear_hours=84.0).value == TWICE_WEEKLY
        assert derive_schedule(wear_hours=168.0).value == ONCE_WEEKLY

    def test_nadac_description_markers(self) -> None:
        result = derive_schedule(
            nadac_descriptions=["ESTRADIOL 0.05 MG PATCH (2/WK)"]
        )
        assert result.value == TWICE_WEEKLY
        assert result.confidence == "nadac-desc"
        assert (
            derive_schedule(nadac_descriptions=["ESTRADIOL 0.05 MG PATCH (1/WK)"]).value
            == ONCE_WEEKLY
        )

    def test_name_marker(self) -> None:
        result = derive_schedule(
            proprietary_name="Estradiol Transdermal System",
            proprietary_suffix="(Twice-Weekly)",
        )
        assert result.value == TWICE_WEEKLY
        assert result.confidence == "brand-map"

    def test_curated_brand_map(self) -> None:
        assert derive_schedule(proprietary_name="LYLLANA").value == TWICE_WEEKLY
        assert derive_schedule(proprietary_name="DOTTI").value == TWICE_WEEKLY
        assert derive_schedule(proprietary_name="Climara").value == ONCE_WEEKLY
        assert derive_schedule(proprietary_name="Menostar").value == ONCE_WEEKLY
        assert derive_schedule(proprietary_name="Vivelle-Dot").value == TWICE_WEEKLY

    def test_pack_count_heuristic_scoped_to_patches(self) -> None:
        assert (
            derive_schedule(pack_count=8, form_family="patch").value == TWICE_WEEKLY
        )
        assert derive_schedule(pack_count=4, form_family="patch").value == ONCE_WEEKLY
        assert derive_schedule(pack_count=8, form_family="gel").value is None
        assert derive_schedule(pack_count=30, form_family="patch").value is None


class TestLadderInteraction:
    def test_higher_rung_wins(self) -> None:
        result = derive_schedule(
            rx_scd_name="84 HR estradiol 0.00208 MG/HR Transdermal System",
            pack_count=8,
            form_family="patch",
        )
        assert result.value == TWICE_WEEKLY
        assert result.confidence == "rxnorm-scd"
        assert len(result.evidence) == 2
        assert not result.conflict

    def test_conflict_is_flagged_but_top_rung_decides(self) -> None:
        result = derive_schedule(
            rx_scd_name="84 HR estradiol 0.00208 MG/HR Transdermal System",
            pack_count=4,  # disagrees with the SCD rung
            form_family="patch",
        )
        assert result.value == TWICE_WEEKLY
        assert result.conflict

    def test_no_evidence_is_unknown_not_guessed(self) -> None:
        result = derive_schedule()
        assert result.value is None
        assert result.confidence is None
        assert not result.conflict
        assert result.evidence == ()

    def test_every_finding_carries_citable_detail(self) -> None:
        result = derive_schedule(
            nadac_descriptions=["LYLLANA 0.05 MG PATCH"],
            proprietary_name="LYLLANA",
            pack_count=8,
            form_family="patch",
        )
        assert result.value == TWICE_WEEKLY
        assert all(e.detail for e in result.evidence)
