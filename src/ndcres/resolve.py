"""The resolver: seed identification, dimension computation, tier
assignment, ranking.

Tier semantics (each result carries machine reason codes; wording for
humans lives in the CLI/web layers):

    T1  same equivalence group, same pack count, marketed — pharmacist-
        substitutable in most states without prescriber contact.
    T2  same equivalence group, different pack configuration — quantity
        change on the prescription.
    T3  same molecule and form family, NOT in the seed's equivalence
        group — requires prescriber authorization. Reasons are additive
        (different-te-subgroup / different-schedule / different-strength
        / no-te-code / not-in-orange-book / seed-no-te-rating /
        schedule-unknown / status-conflict).
    T4  same molecule, different delivery form family — informational,
        clinical decision.
    EXCLUDED  discontinued / not in the current directory / sample
        packages — reported with provenance, never ranked.

The equivalence group key is (ingredient_set, OB heading DF;Route,
canonical strength, full TE code). A NULL TE code NEVER forms a group —
otherwise every unrated product would cluster into a fake tier-1.
``assign_tier`` is a pure function over two ``Dims`` so it can be fuzzed
directly.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Literal

from .ndc import parse_ndc
from .schedule import ScheduleResult, derive_schedule
from .signals import signal_report

EqGroup = tuple[str, str, str, str]
Tier = Literal["T1", "T2", "T3", "T4", "EXCLUDED"]


@dataclass(frozen=True)
class Dims:
    """Comparison dimensions for one product/package. Pure data."""

    ndc9: str
    ndc11: str | None = None
    ingredient_set: str | None = None
    ingredient_count: int = 0
    form_family: str | None = None
    strength_norm: str | None = None
    eq_group: EqGroup | None = None
    te_code: str | None = None
    ob_type: str | None = None
    schedule: str | None = None
    schedule_confidence: str | None = None
    schedule_conflict: bool = False
    pack_count: int | None = None
    pack_unit: str | None = None
    marketed: bool = False
    sample_package: bool = False
    in_directory: bool = True
    # Display annotations (never used by assign_tier):
    proprietary_name: str | None = None
    proprietary_suffix: str | None = None
    labeler_name: str | None = None
    package_ndc_filed: str | None = None
    appl_display: str | None = None
    ob_heading: str | None = None
    link_method: str | None = None
    link_status: str | None = None


@dataclass(frozen=True)
class TierResult:
    tier: Tier
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Annotated:
    """A candidate with its tier and display annotations."""

    dims: Dims
    result: TierResult
    nadac_price: float | None = None
    nadac_effective: str | None = None
    nadac_as_of_last: str | None = None
    shortage_statuses: tuple[str, ...] = ()
    stress_score: float | None = None
    stress_evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class Resolution:
    seed: Dims
    seed_status: str  # 'package' | 'product-grain' | 'rxnorm-only'
    seed_annotation: Annotated | None
    tiers: dict[str, list[Annotated]] = field(default_factory=dict)
    excluded: list[Annotated] = field(default_factory=list)
    notes: tuple[str, ...] = ()


class ResolveError(ValueError):
    """Raised when an input cannot be resolved to a seed."""


# --------------------------------------------------------------- seed lookup


def resolve_input_ndc11(conn: sqlite3.Connection, text: str) -> str:
    """Turn user NDC text into one ndc11, using the DB to disambiguate
    bare-10 input. Raises ResolveError with candidates listed."""
    query = parse_ndc(text)
    if not query.ambiguous:
        return query.ndc11
    known = [
        candidate
        for candidate in query.candidates
        if _known_ndc11(conn, candidate)
    ]
    if len(known) == 1:
        return known[0]
    if not known:
        raise ResolveError(
            f"{text} is ambiguous without hyphens and none of its possible "
            f"normalizations are known: {', '.join(query.candidates)}"
        )
    raise ResolveError(
        f"{text} is ambiguous: multiple known NDCs match "
        f"({', '.join(known)}). Re-enter it with hyphens as printed."
    )


def _known_ndc11(conn: sqlite3.Connection, ndc11: str) -> bool:
    for table, column in (("package", "ndc11"), ("rx_ndc", "ndc11")):
        row = conn.execute(
            f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1",  # noqa: S608
            (ndc11,),
        ).fetchone()
        if row is not None:
            return True
    return False


# ---------------------------------------------------------------- dimensions


def compute_dimensions(
    conn: sqlite3.Connection, ndc9: str, ndc11: str | None
) -> Dims | None:
    """One dimension computation for seeds AND candidates — never two
    code paths. Returns None when ndc9 is absent from the directory."""
    product = conn.execute(
        "SELECT * FROM product WHERE ndc9 = ?", (ndc9,)
    ).fetchone()
    if product is None:
        return None

    package = None
    if ndc11 is not None:
        package = conn.execute(
            "SELECT * FROM package WHERE ndc11 = ?", (ndc11,)
        ).fetchone()

    ob_row = conn.execute(
        """
        SELECT o.*, l.match_method FROM product_ob_link l
        JOIN ob_product o USING (appl_type, appl_no, product_no)
        WHERE l.ndc9 = ?
        """,
        (ndc9,),
    ).fetchone()

    eq_group: EqGroup | None = None
    te_code = ob_row["te_code"] if ob_row is not None else None
    if ob_row is not None and te_code is not None:
        eq_group = (
            ob_row["ingredient_set"],
            ob_row["df_route"],
            ob_row["strength_norm"] or "",
            te_code,
        )

    schedule = _derive_schedule(conn, product, package)

    end_product = product["end_marketing"]
    end_package = package["end_marketing"] if package is not None else None
    sample = bool(package["sample_package"]) if package is not None else False
    marketed = end_product is None and end_package is None and not sample

    return Dims(
        ndc9=ndc9,
        ndc11=ndc11,
        ingredient_set=product["ingredient_set"],
        ingredient_count=product["ingredient_count"],
        form_family=product["form_family"],
        strength_norm=product["strength_norm"],
        eq_group=eq_group,
        te_code=te_code,
        ob_type=ob_row["ob_type"] if ob_row is not None else None,
        schedule=schedule.value,
        schedule_confidence=schedule.confidence,
        schedule_conflict=schedule.conflict,
        pack_count=package["pack_count"] if package is not None else None,
        pack_unit=package["pack_unit"] if package is not None else None,
        marketed=marketed,
        sample_package=sample,
        in_directory=True,
        proprietary_name=product["proprietary_name"],
        proprietary_suffix=product["proprietary_suffix"],
        labeler_name=product["labeler_name"],
        package_ndc_filed=package["package_ndc_filed"] if package is not None else None,
        appl_display=_appl_display(product),
        ob_heading=ob_row["df_route"] if ob_row is not None else None,
        link_method=ob_row["match_method"] if ob_row is not None else None,
        link_status=product["ob_link_status"],
    )


def _appl_display(product: sqlite3.Row) -> str | None:
    if product["appl_type"] is None or product["appl_no"] is None:
        return None
    prefix = "ANDA" if product["appl_type"] == "A" else "NDA"
    return f"{prefix}{product['appl_no']}"


def _derive_schedule(
    conn: sqlite3.Connection, product: sqlite3.Row, package: sqlite3.Row | None
) -> ScheduleResult:
    ndc9 = product["ndc9"]
    concept_name = None
    row = conn.execute(
        """
        SELECT c.name FROM rx_ndc n JOIN rx_concept c USING (rxcui)
        JOIN package p ON p.ndc11 = n.ndc11
        WHERE p.ndc9 = ? ORDER BY c.tty DESC LIMIT 1
        """,
        (ndc9,),
    ).fetchone()
    if row is not None:
        concept_name = row["name"]

    nadac_descriptions = [
        r["description"]
        for r in conn.execute(
            """
            SELECT DISTINCT n.description FROM nadac n
            JOIN package p ON p.ndc11 = n.ndc11
            WHERE p.ndc9 = ? AND n.description IS NOT NULL
            """,
            (ndc9,),
        )
    ]

    wear = None
    pack_count = None
    if package is not None:
        wear = package["wear_hours"]
        pack_count = package["pack_count"]
    else:
        any_package = conn.execute(
            "SELECT wear_hours, pack_count FROM package WHERE ndc9 = ? LIMIT 1",
            (ndc9,),
        ).fetchone()
        if any_package is not None:
            wear = any_package["wear_hours"]
            pack_count = any_package["pack_count"]

    return derive_schedule(
        rx_scd_name=concept_name,
        wear_hours=wear,
        nadac_descriptions=nadac_descriptions,
        proprietary_name=product["proprietary_name"],
        proprietary_suffix=product["proprietary_suffix"],
        pack_count=pack_count,
        form_family=product["form_family"],
    )


# ------------------------------------------------------------------ tiering


def assign_tier(seed: Dims, candidate: Dims) -> TierResult:
    """Pure tier assignment. Ordered predicates; first match wins."""
    # EXCLUDED first — never ranked, always reported with provenance.
    if not candidate.in_directory:
        return TierResult("EXCLUDED", ("not-in-current-ndc-directory",))
    if candidate.sample_package:
        return TierResult("EXCLUDED", ("sample-package",))
    if candidate.ob_type == "DISCN" and not candidate.marketed:
        return TierResult("EXCLUDED", ("discontinued-ob",))

    # Same equivalence group ⇒ same product design; schedule inherited.
    if seed.eq_group is not None and candidate.eq_group == seed.eq_group:
        if (
            candidate.pack_count is not None
            and seed.pack_count is not None
            and candidate.pack_count == seed.pack_count
            and candidate.marketed
        ):
            return TierResult("T1", ())
        reasons: list[str] = []
        if candidate.pack_count is None or seed.pack_count is None:
            reasons.append("pack-count-unknown")
        if not candidate.marketed:
            reasons.append("status-conflict")
        return TierResult("T2", tuple(reasons))

    # Different delivery class → informational only.
    if candidate.form_family != seed.form_family:
        return TierResult("T4", ("different-form-family",))

    # Same molecule + form family, outside the seed's group → prescriber.
    reasons = []
    if seed.eq_group is None:
        reasons.append("seed-no-te-rating")
    if candidate.eq_group is None:
        if candidate.ob_type is not None:
            reasons.append("no-te-code")
        else:
            reasons.append("not-in-orange-book")
    if seed.eq_group is not None and candidate.eq_group is not None:
        # The group key is (ingredient, heading, strength, TE code). When
        # the heading and full TE code agree and only the strength differs,
        # the products are the same TE family at another strength —
        # claiming a subgroup difference there would be a lie the
        # different-strength reason already covers.
        heading_or_code_differs = (
            seed.eq_group[0] != candidate.eq_group[0]
            or seed.eq_group[1] != candidate.eq_group[1]
            or seed.eq_group[3] != candidate.eq_group[3]
        )
        if heading_or_code_differs:
            reasons.append("different-te-subgroup")
    if candidate.schedule is not None and seed.schedule is not None:
        if candidate.schedule != seed.schedule:
            reasons.append("different-schedule")
    else:
        reasons.append("schedule-unknown")
    if (
        candidate.strength_norm is not None
        and seed.strength_norm is not None
        and candidate.strength_norm != seed.strength_norm
    ):
        reasons.append("different-strength")
    if candidate.ob_type == "DISCN" and candidate.marketed:
        reasons.append("status-conflict")
    return TierResult("T3", tuple(reasons))


# ------------------------------------------------------------------- gather


def gather_candidates(
    conn: sqlite3.Connection, seed: Dims
) -> list[tuple[str, str]]:
    """(ndc9, ndc11) pairs for every same-molecule package, minus the
    seed package. Union of the directory path (ingredient_set) and the
    RxNorm path (SCD → IN → single-ingredient concepts → NDCs)."""
    pairs: dict[str, str] = {}

    if seed.ingredient_set is not None:
        for row in conn.execute(
            """
            SELECT p.ndc9, k.ndc11 FROM product p
            JOIN package k USING (ndc9)
            WHERE p.ingredient_set = ?
            """,
            (seed.ingredient_set,),
        ):
            pairs[row["ndc11"]] = row["ndc9"]

    for ndc11 in _rxnorm_sibling_ndcs(conn, seed):
        if ndc11 not in pairs:
            pairs[ndc11] = ndc11[:9]

    if seed.ndc11 is not None:
        pairs.pop(seed.ndc11, None)
    return sorted((ndc9, ndc11) for ndc11, ndc9 in pairs.items())


def _rxnorm_sibling_ndcs(conn: sqlite3.Connection, seed: Dims) -> list[str]:
    if seed.ndc11 is None or seed.ingredient_count > 1:
        return []
    ingredient_cuis = conn.execute(
        """
        WITH seed_concepts AS (
          SELECT rxcui FROM rx_ndc WHERE ndc11 = ?
        ),
        scds AS (  -- normalize SBD → SCD (either relation direction)
          SELECT rxcui FROM seed_concepts
          UNION
          SELECT r.rxcui2 FROM rx_rel r JOIN seed_concepts s ON r.rxcui1 = s.rxcui
          WHERE r.rela IN ('tradename_of', 'has_tradename')
          UNION
          SELECT r.rxcui1 FROM rx_rel r JOIN seed_concepts s ON r.rxcui2 = s.rxcui
          WHERE r.rela IN ('tradename_of', 'has_tradename')
        )
        SELECT DISTINCT i.rxcui AS in_cui FROM rx_concept i
        JOIN rx_rel r ON (
          (r.rxcui1 IN (SELECT rxcui FROM scds) AND r.rxcui2 = i.rxcui)
          OR (r.rxcui2 IN (SELECT rxcui FROM scds) AND r.rxcui1 = i.rxcui)
        )
        WHERE i.tty = 'IN' AND r.rela IN ('has_ingredient', 'ingredient_of')
        """,
        (seed.ndc11,),
    ).fetchall()
    if len(ingredient_cuis) != 1:
        return []  # combo or unmapped — the RxNorm path only covers 1-IN drugs
    in_cui = ingredient_cuis[0]["in_cui"]

    return [
        row["ndc11"]
        for row in conn.execute(
            """
            WITH family_scds AS (
              SELECT DISTINCT s.rxcui FROM rx_concept s
              JOIN rx_rel r ON (
                (r.rxcui1 = s.rxcui AND r.rxcui2 = :in_cui)
                OR (r.rxcui2 = s.rxcui AND r.rxcui1 = :in_cui)
              )
              WHERE s.tty = 'SCD'
                AND r.rela IN ('has_ingredient', 'ingredient_of')
                -- single-ingredient guard: exactly one IN neighbour
                AND 1 = (
                  SELECT count(DISTINCT i2.rxcui) FROM rx_concept i2
                  JOIN rx_rel r2 ON (
                    (r2.rxcui1 = s.rxcui AND r2.rxcui2 = i2.rxcui)
                    OR (r2.rxcui2 = s.rxcui AND r2.rxcui1 = i2.rxcui)
                  )
                  WHERE i2.tty = 'IN'
                    AND r2.rela IN ('has_ingredient', 'ingredient_of')
                )
            ),
            family AS (
              SELECT rxcui FROM family_scds
              UNION
              SELECT r.rxcui1 FROM rx_rel r
              JOIN family_scds f ON r.rxcui2 = f.rxcui
              WHERE r.rela IN ('tradename_of', 'has_tradename')
              UNION
              SELECT r.rxcui2 FROM rx_rel r
              JOIN family_scds f ON r.rxcui1 = f.rxcui
              WHERE r.rela IN ('tradename_of', 'has_tradename')
            )
            SELECT DISTINCT n.ndc11 FROM rx_ndc n
            JOIN family f USING (rxcui)
            """,
            {"in_cui": in_cui},
        )
    ]


# ------------------------------------------------------------------ resolve


def resolve(conn: sqlite3.Connection, text: str) -> Resolution:
    ndc11 = resolve_input_ndc11(conn, text)

    package = conn.execute(
        "SELECT ndc9 FROM package WHERE ndc11 = ?", (ndc11,)
    ).fetchone()
    if package is not None:
        seed = compute_dimensions(conn, package["ndc9"], ndc11)
        assert seed is not None
        seed_status = "package"
    else:
        product = conn.execute(
            "SELECT ndc9 FROM product WHERE ndc9 = ?", (ndc11[:9],)
        ).fetchone()
        if product is not None:
            seed = compute_dimensions(conn, ndc11[:9], None)
            assert seed is not None
            seed_status = "product-grain"
        else:
            seed = _rxnorm_only_seed(conn, ndc11)
            if seed is None:
                raise ResolveError(
                    f"NDC {ndc11} is unknown to the current NDC Directory, "
                    "RxNorm prescribable content, and this database. "
                    "Check the spelling, or refresh the data."
                )
            seed_status = "rxnorm-only"

    candidates = gather_candidates(conn, seed)
    tiers: dict[str, list[Annotated]] = {"T1": [], "T2": [], "T3": [], "T4": []}
    excluded: list[Annotated] = []

    for ndc9, cand_ndc11 in candidates:
        dims = compute_dimensions(conn, ndc9, cand_ndc11)
        if dims is None:
            dims = Dims(ndc9=ndc9, ndc11=cand_ndc11, in_directory=False)
        result = assign_tier(seed, dims)
        annotated = _annotate(conn, dims, result)
        if result.tier == "EXCLUDED":
            excluded.append(annotated)
        else:
            tiers[result.tier].append(annotated)

    for tier_list in tiers.values():
        tier_list.sort(key=_rank_key)
    excluded.sort(key=_rank_key)

    notes: list[str] = []
    if seed_status != "package":
        notes.append(f"seed-status:{seed_status}")
    if seed.eq_group is None:
        notes.append(
            "seed has no therapeutic-equivalence rating; nothing can be "
            "tier 1 or 2 relative to it"
        )

    seed_annotation = _annotate(conn, seed, TierResult("T1", ())) if seed else None
    return Resolution(
        seed=seed,
        seed_status=seed_status,
        seed_annotation=seed_annotation,
        tiers=tiers,
        excluded=excluded,
        notes=tuple(notes),
    )


def _rxnorm_only_seed(conn: sqlite3.Connection, ndc11: str) -> Dims | None:
    row = conn.execute(
        """
        SELECT c.rxcui, c.tty, c.name FROM rx_ndc n
        JOIN rx_concept c USING (rxcui) WHERE n.ndc11 = ?
        """,
        (ndc11,),
    ).fetchone()
    if row is None:
        return None
    ingredients = conn.execute(
        """
        SELECT DISTINCT i.name FROM rx_concept i
        JOIN rx_rel r ON (
          (r.rxcui1 = ? AND r.rxcui2 = i.rxcui)
          OR (r.rxcui2 = ? AND r.rxcui1 = i.rxcui)
        )
        WHERE i.tty = 'IN' AND r.rela IN ('has_ingredient', 'ingredient_of')
        """,
        (row["rxcui"], row["rxcui"]),
    ).fetchall()
    ingredient_names = sorted(i["name"].upper() for i in ingredients)
    schedule = derive_schedule(rx_scd_name=row["name"])
    return Dims(
        ndc9=ndc11[:9],
        ndc11=ndc11,
        ingredient_set="|".join(ingredient_names) if ingredient_names else None,
        ingredient_count=len(ingredient_names),
        form_family="patch" if "Transdermal System" in row["name"] else None,
        schedule=schedule.value,
        schedule_confidence=schedule.confidence,
        marketed=False,
        in_directory=False,
        proprietary_name=row["name"],
    )


# ---------------------------------------------------------------- annotation


def _annotate(
    conn: sqlite3.Connection, dims: Dims, result: TierResult
) -> Annotated:
    nadac_price = nadac_effective = nadac_as_of = None
    shortage_statuses: tuple[str, ...] = ()
    if dims.ndc11 is not None:
        nadac_row = conn.execute(
            """
            SELECT price, effective_date, as_of_last FROM nadac
            WHERE ndc11 = ? ORDER BY effective_date DESC LIMIT 1
            """,
            (dims.ndc11,),
        ).fetchone()
        if nadac_row is not None:
            nadac_price = nadac_row["price"]
            nadac_effective = nadac_row["effective_date"]
            nadac_as_of = nadac_row["as_of_last"]
        shortage_statuses = tuple(
            row["status"]
            for row in conn.execute(
                "SELECT status FROM shortage WHERE ndc11 = ? OR ndc9 = ? "
                "ORDER BY update_date DESC",
                (dims.ndc11, dims.ndc9),
            )
            if row["status"]
        )
    stress_score: float | None = None
    stress_evidence: tuple[str, ...] = ()
    if dims.ndc11 is not None:
        report = signal_report(conn, dims.ndc11)
        stress_score = report.score
        stress_evidence = tuple(
            f"{c.name}: {c.evidence}" for c in report.components if c.fired
        )
    return Annotated(
        dims=dims,
        result=result,
        nadac_price=nadac_price,
        nadac_effective=nadac_effective,
        nadac_as_of_last=nadac_as_of,
        shortage_statuses=shortage_statuses,
        stress_score=stress_score,
        stress_evidence=stress_evidence,
    )


def _rank_key(annotated: Annotated) -> tuple[float, int, float, str, str]:
    """stress asc → NADAC recency desc → price asc → name → ndc11 (the
    deterministic tiebreak).

    Ranking-only nudge: products with NO NADAC presence at all (usually
    low-volume repackagers) sort behind surveyed products of similar
    stress — never being surveyed is weaker retail evidence than a mild
    price trend. This affects ordering only; the reported stress score is
    untouched.
    """
    stress = annotated.stress_score if annotated.stress_score is not None else 0.0
    if annotated.nadac_as_of_last is None:
        stress += 0.1
    recency = annotated.nadac_as_of_last
    # ISO dates sort numerically once the hyphens are dropped; negate so
    # more-recent survey presence ranks first. Absent NADAC ranks last.
    recency_rank = -int(recency.replace("-", "")) if recency else 0
    price = annotated.nadac_price if annotated.nadac_price is not None else float("inf")
    name = annotated.dims.proprietary_name or ""
    return (stress, recency_rank, price, name, annotated.dims.ndc11 or "")
