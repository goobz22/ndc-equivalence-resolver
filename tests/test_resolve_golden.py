"""Golden resolution tests — the estradiol family, tiered correctly.

The load-bearing assertions encode the corrigendum this project's own
brief fell into: at 0.05 mg/day, DOTTI (AB1) is a direct substitute for
the Mylan anchor `0378-4642-26` (AB1), while LYLLANA (AB3) — same
manufacturer as Dotti, same schedule, same strength, same 8-count — is
NOT, and must land in the prescriber-authorization tier.
"""

import sqlite3

import pytest

from ndcres.resolve import (
    Dims,
    ResolveError,
    assign_tier,
    compute_dimensions,
    resolve,
    resolve_input_ndc11,
)


def _tier_ndcs(resolution, tier: str) -> set[str]:  # type: ignore[no-untyped-def]
    return {a.dims.ndc11 for a in resolution.tiers[tier]}


def _reasons_for(resolution, tier: str, ndc11: str) -> tuple[str, ...]:  # type: ignore[no-untyped-def]
    for annotated in resolution.tiers[tier]:
        if annotated.dims.ndc11 == ndc11:
            return annotated.result.reasons
    raise AssertionError(f"{ndc11} not in {tier}")


@pytest.fixture(scope="module")
def anchor_resolution(loaded_conn: sqlite3.Connection):  # type: ignore[no-untyped-def]
    return resolve(loaded_conn, "0378-4642-26")


@pytest.fixture(scope="module")
def lyllana_resolution(loaded_conn: sqlite3.Connection):  # type: ignore[no-untyped-def]
    return resolve(loaded_conn, "65162-149-08")


class TestAnchorGolden:
    """resolve 0378-4642-26 — the motivating real-world case."""

    @pytest.fixture()
    def resolution(self, anchor_resolution):  # type: ignore[no-untyped-def]
        return anchor_resolution

    def test_seed_identity(self, resolution) -> None:  # type: ignore[no-untyped-def]
        assert resolution.seed.ndc11 == "00378464226"
        assert resolution.seed.te_code == "AB1"
        assert resolution.seed.schedule == "2/wk"
        assert resolution.seed.pack_count == 8
        assert resolution.seed_status == "package"

    def test_tier1_is_exactly_the_ab1_eight_counts(self, resolution) -> None:  # type: ignore[no-untyped-def]
        assert _tier_ndcs(resolution, "T1") == {
            "65162099308",  # DOTTI — Amneal, AB1
            "70710119308",  # Zydus, AB1
            "00781714483",  # Sandoz authorized generic of Vivelle-Dot, AB1
            "66758014783",  # Vivelle-Dot brand, AB1 RLD
        }

    def test_lyllana_is_tier3_different_subgroup(self, resolution) -> None:  # type: ignore[no-untyped-def]
        assert "65162014908" in _tier_ndcs(resolution, "T3")
        reasons = _reasons_for(resolution, "T3", "65162014908")
        assert reasons == ("different-te-subgroup",)

    def test_mylan_own_ab3_product_is_tier3(self, resolution) -> None:  # type: ignore[no-untyped-def]
        # Same labeler, same strength, same schedule, same pack count —
        # AB3 vs AB1 → still not interchangeable.
        assert "00378462126" in _tier_ndcs(resolution, "T3")
        assert _reasons_for(resolution, "T3", "00378462126") == (
            "different-te-subgroup",
        )

    def test_climara_group_is_tier3_schedule_change(self, resolution) -> None:  # type: ignore[no-untyped-def]
        for ndc11 in ("50419045104", "00378335099", "68382032604", "00781713354"):
            reasons = _reasons_for(resolution, "T3", ndc11)
            assert "different-te-subgroup" in reasons
            assert "different-schedule" in reasons

    def test_menostar_is_tier3_multi_reason(self, resolution) -> None:  # type: ignore[no-untyped-def]
        reasons = _reasons_for(resolution, "T3", "50419045504")
        assert "different-te-subgroup" in reasons
        assert "different-schedule" in reasons
        assert "different-strength" in reasons

    def test_minivelle_is_tier3_not_tier1(self, resolution) -> None:  # type: ignore[no-untyped-def]
        assert "68968665008" in _tier_ndcs(resolution, "T3")

    def test_tier4_gel_spray_oral(self, resolution) -> None:  # type: ignore[no-untyped-def]
        t4 = _tier_ndcs(resolution, "T4")
        assert {"68025006507", "68025006530", "00574206727", "00555088602",
                "00555088604", "21922001540"} <= t4
        for annotated in resolution.tiers["T4"]:
            assert annotated.result.reasons == ("different-form-family",)

    def test_combo_product_never_gathered(self, resolution) -> None:  # type: ignore[no-untyped-def]
        everything = set().union(
            *(_tier_ndcs(resolution, t) for t in ("T1", "T2", "T3", "T4")),
            {a.dims.ndc11 for a in resolution.excluded},
        )
        assert "50419049104" not in everything  # Climara Pro (combo)

    def test_sample_package_excluded(self, resolution) -> None:  # type: ignore[no-untyped-def]
        excluded = {a.dims.ndc11: a.result.reasons for a in resolution.excluded}
        assert excluded.get("00574206700") == ("sample-package",)

    def test_alora_surfaces_as_excluded_via_rxnorm(self, resolution) -> None:  # type: ignore[no-untyped-def]
        excluded = {a.dims.ndc11: a.result.reasons for a in resolution.excluded}
        assert excluded.get("52544047108") == ("not-in-current-ndc-directory",)

    def test_partition_no_candidate_in_two_tiers(self, resolution) -> None:  # type: ignore[no-untyped-def]
        buckets = [
            _tier_ndcs(resolution, t) for t in ("T1", "T2", "T3", "T4")
        ] + [{a.dims.ndc11 for a in resolution.excluded}]
        total = sum(len(b) for b in buckets)
        assert len(set().union(*buckets)) == total

    def test_seed_never_its_own_candidate(self, resolution) -> None:  # type: ignore[no-untyped-def]
        everything = set().union(
            *(_tier_ndcs(resolution, t) for t in ("T1", "T2", "T3", "T4")),
            {a.dims.ndc11 for a in resolution.excluded},
        )
        assert "00378464226" not in everything


class TestSymmetryGolden:
    """resolve 65162-149-08 (Lyllana as seed) — no seed-privileging."""

    @pytest.fixture()
    def resolution(self, lyllana_resolution):  # type: ignore[no-untyped-def]
        return lyllana_resolution

    def test_tier1_is_the_ab3_group(self, resolution) -> None:  # type: ignore[no-untyped-def]
        assert _tier_ndcs(resolution, "T1") == {
            "68968665008",  # Minivelle brand, AB3 RLD
            "00378462126",  # Mylan ANDA206685, AB3
        }

    def test_original_anchor_lands_in_tier3(self, resolution) -> None:  # type: ignore[no-untyped-def]
        assert _reasons_for(resolution, "T3", "00378464226") == (
            "different-te-subgroup",
        )


class TestSpellingGolden:
    ANCHOR_SPELLINGS = ("0378-4642-26", "00378-4642-26", "00378464226", "0378464226")

    def test_all_spellings_resolve_identically(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        outputs = []
        for spelling in self.ANCHOR_SPELLINGS:
            resolution = resolve(loaded_conn, spelling)
            outputs.append(
                {
                    tier: [a.dims.ndc11 for a in members]
                    for tier, members in resolution.tiers.items()
                }
            )
        assert all(output == outputs[0] for output in outputs)

    def test_bare10_disambiguates_against_db(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        assert resolve_input_ndc11(loaded_conn, "0378464226") == "00378464226"

    def test_unknown_ndc_errors_helpfully(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        with pytest.raises(ResolveError, match="unknown"):
            resolve(loaded_conn, "9999-9999-99")


class TestTier2:
    def test_same_product_other_pack_is_tier2(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        # Divigel 7-packet → Divigel 30-packet: same eq_group, pack differs.
        resolution = resolve(loaded_conn, "68025-065-07")
        assert "68025006530" in _tier_ndcs(resolution, "T2")


class TestDiscontinuedSeed:
    def test_alora_ndc_resolves_via_rxnorm_only(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        resolution = resolve(loaded_conn, "52544-471-08")
        assert resolution.seed_status == "rxnorm-only"
        assert resolution.tiers["T1"] == []
        assert resolution.tiers["T2"] == []
        reasons = _reasons_for(resolution, "T3", "65162099308")
        assert "seed-no-te-rating" in reasons


class TestProperties:
    _FAMILY_005_PATCHES = (
        "00378464226", "00378462126", "00378335099", "65162014908",
        "65162099308", "66758014783", "68968665008", "50419045104",
        "00781714483", "00781713354", "70710119308", "68382032604",
    )

    def _dims(self, conn: sqlite3.Connection, ndc11: str) -> Dims:
        row = conn.execute(
            "SELECT ndc9 FROM package WHERE ndc11 = ?", (ndc11,)
        ).fetchone()
        dims = compute_dimensions(conn, row["ndc9"], ndc11)
        assert dims is not None
        return dims

    def test_tier1_is_symmetric(self, loaded_conn: sqlite3.Connection) -> None:
        dims = {n: self._dims(loaded_conn, n) for n in self._FAMILY_005_PATCHES}
        for a in self._FAMILY_005_PATCHES:
            for b in self._FAMILY_005_PATCHES:
                if a == b:
                    continue
                forward = assign_tier(dims[a], dims[b]).tier == "T1"
                backward = assign_tier(dims[b], dims[a]).tier == "T1"
                assert forward == backward, (a, b)

    def test_resolution_is_deterministic(
        self, loaded_conn: sqlite3.Connection
    ) -> None:
        def snapshot():  # type: ignore[no-untyped-def]
            resolution = resolve(loaded_conn, "0378-4642-26")
            return {
                tier: [(a.dims.ndc11, a.result.reasons) for a in members]
                for tier, members in resolution.tiers.items()
            }

        assert snapshot() == snapshot()

    def test_blank_te_never_groups(self) -> None:
        # Two unrated products, identical ingredient/form/strength/pack —
        # they must NOT read as tier-1/2 to each other.
        left = Dims(
            ndc9="111110001", ndc11="11111000101", ingredient_set="ESTRADIOL",
            ingredient_count=1, form_family="patch", strength_norm="UG24H:50",
            eq_group=None, te_code=None, pack_count=8, marketed=True,
        )
        right = Dims(
            ndc9="222220001", ndc11="22222000101", ingredient_set="ESTRADIOL",
            ingredient_count=1, form_family="patch", strength_norm="UG24H:50",
            eq_group=None, te_code=None, ob_type="RX", pack_count=8,
            marketed=True,
        )
        result = assign_tier(left, right)
        assert result.tier == "T3"
        assert "seed-no-te-rating" in result.reasons
        assert "no-te-code" in result.reasons  # OB row present, TE blank

    def test_unknown_schedule_blocks_nothing_within_group(self) -> None:
        # Same eq_group ⇒ schedule inherited ⇒ T1 even if underivable.
        group = ("ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:50", "AB1")
        seed = Dims(
            ndc9="111110001", ndc11="11111000101", ingredient_set="ESTRADIOL",
            ingredient_count=1, form_family="patch", strength_norm="UG24H:50",
            eq_group=group, te_code="AB1", schedule="2/wk", pack_count=8,
            marketed=True,
        )
        candidate = Dims(
            ndc9="222220001", ndc11="22222000101", ingredient_set="ESTRADIOL",
            ingredient_count=1, form_family="patch", strength_norm="UG24H:50",
            eq_group=group, te_code="AB1", schedule=None, pack_count=8,
            marketed=True,
        )
        assert assign_tier(seed, candidate).tier == "T1"

    def test_same_te_family_other_strength_is_only_different_strength(
        self,
    ) -> None:
        # Live-data regression: Dotti 0.075 vs the 0.05 anchor — same
        # heading, same AB1 code, different strength. The reason must be
        # different-strength ALONE; claiming different-te-subgroup there
        # is false (the TE family is the same).
        seed = Dims(
            ndc9="111110001", ndc11="11111000101", ingredient_set="ESTRADIOL",
            ingredient_count=1, form_family="patch", strength_norm="UG24H:50",
            eq_group=("ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:50", "AB1"),
            te_code="AB1", schedule="2/wk", pack_count=8, marketed=True,
        )
        candidate = Dims(
            ndc9="222220001", ndc11="22222000101", ingredient_set="ESTRADIOL",
            ingredient_count=1, form_family="patch", strength_norm="UG24H:75",
            eq_group=("ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:75", "AB1"),
            te_code="AB1", schedule="2/wk", pack_count=8, marketed=True,
        )
        result = assign_tier(seed, candidate)
        assert result.tier == "T3"
        assert result.reasons == ("different-strength",)

    def test_unknown_schedule_blocks_tier_across_groups(self) -> None:
        seed = Dims(
            ndc9="111110001", ndc11="11111000101", ingredient_set="ESTRADIOL",
            ingredient_count=1, form_family="patch", strength_norm="UG24H:50",
            eq_group=("ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:50", "AB1"),
            te_code="AB1", schedule="2/wk", pack_count=8, marketed=True,
        )
        candidate = Dims(
            ndc9="222220001", ndc11="22222000101", ingredient_set="ESTRADIOL",
            ingredient_count=1, form_family="patch", strength_norm="UG24H:50",
            eq_group=("ESTRADIOL", "SYSTEM;TRANSDERMAL", "UG24H:50", "AB9"),
            te_code="AB9", schedule=None, pack_count=8, marketed=True,
        )
        result = assign_tier(seed, candidate)
        assert result.tier == "T3"
        assert "schedule-unknown" in result.reasons
