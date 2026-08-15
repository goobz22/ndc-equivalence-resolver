"""Evidence dossier (SPEC §11): one class, every ingested fact, cited.

Two renderers over one dataset:

  dossier_markdown  — the PUBLIC case study. Operator decision #4: every
    claim in it derives from data ingested into this resolver, each
    section stamped with its source_run vintage, ending with the
    commands that reproduce it. ZERO external URLs in the evidence
    chain (the only links are the ingested sources' own landing pages
    from the provenance registry).

  dossier_exhibits  — the petition-shaped exhibit pack (21 CFR 10.30
    structure): requested action, statement of grounds, exhibits A–E
    from ingested data, and a clearly-separated appendix of EXTERNAL
    references (labeled "externally reported — not pipeline data").
    FILING IS THE OPERATOR'S DECISION; this module only formats
    evidence, and the header says a lawyer should read it first.

Language discipline: verdict wording flows from VERDICT_LANGUAGE;
"evidence consistent with", never "shortage confirmed".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from .provenance import SOURCE_REGISTRY, source_refs
from .resolve import ResolveError, resolve, resolve_input_ndc11
from .signals import VERDICT_FDA_LISTED, ClassAssessment, class_supply_assessment


@dataclass(frozen=True)
class ExternalReference:
    label: str
    url: str
    accessed: str
    note: str


# Used ONLY by the exhibit pack's separated appendix — never by the
# public case study (operator decision #4: the public evidence chain is
# ingested data only).
EXTERNAL_REFERENCES: tuple[ExternalReference, ...] = (
    ExternalReference(
        "Australia TGA: Estradot listed Limited Availability through Dec 2026, "
        "s19A overseas substitution approved",
        "https://apps.tga.gov.au/prod/MSI/search",
        "2026-08-13",
        "mandatory-reporting regime",
    ),
    ExternalReference(
        "Australia TGA: dedicated page on the transdermal HRT patch shortage",
        "https://www.tga.gov.au/safety/shortages-and-supply-disruptions/"
        "medicine-shortages/major-or-ongoing-medicine-shortages/"
        "about-shortage-transdermal-hrt-patches",
        "2026-08-13",
        "mandatory-reporting regime",
    ),
    ExternalReference(
        "UK: Serious Shortage Protocols SSP079-082 for Estradot 25/50/75/100 "
        "mcg, repeatedly extended to 2026-10-02 (pharmacist emergency "
        "substitution authorized)",
        "https://cpe.org.uk/our-news/ssps-for-estradot-patches-ssp079-ssp080-"
        "ssp081-ssp082-further-extended/",
        "2026-08-13",
        "national emergency protocol",
    ),
    ExternalReference(
        "Canada Health Product Shortages: multiple active Estradot shortage "
        "reports (mandatory reporting since 2017)",
        "https://healthproductshortages.ca/",
        "2026-08-13",
        "mandatory-reporting regime",
    ),
    ExternalReference(
        "ASHP drug shortage bulletin: Estradiol Transdermal System, created "
        "2026-01-30 (practitioner-reported US list)",
        "https://www.ashp.org/drug-shortages/current-shortages/"
        "drug-shortage-detail.aspx?id=1206",
        "2026-08-13",
        "US practitioner-run list; terms allow citation only",
    ),
    ExternalReference(
        "FDA/Premier presentation documenting ASHP-before-FDA listing lags of "
        "129 days (oxytocin) and 114 days (Pitocin)",
        "https://www.fda.gov/media/179066/download",
        "2026-08-13",
        "prior art on FDA-list lag",
    ),
    ExternalReference(
        "HHS/ASPE 'Analysis of Drug Shortages 2018-2023': HHS reconstructed "
        "FDA shortage history from Internet Archive snapshots",
        "https://www.ncbi.nlm.nih.gov/books/NBK611681/",
        "2026-08-13",
        "federal acknowledgment the list keeps no history",
    ),
    ExternalReference(
        "GAO-25-107110: FDA medical-product oversight added to GAO's "
        "High-Risk List; shortages lasting longer",
        "https://files.gao.gov/reports/GAO-25-107110/index.html",
        "2026-08-13",
        "prior art",
    ),
)


@dataclass(frozen=True)
class Dossier:
    class_key: tuple[str, str, str, str]
    rep_ndc11: str
    members: tuple[dict[str, Any], ...]
    assessment: ClassAssessment
    fda_active: tuple[dict[str, Any], ...]
    nadac_series: dict[str, tuple[dict[str, Any], ...]]
    sdud_trend: tuple[dict[str, Any], ...]
    recall_lines: tuple[dict[str, Any], ...]
    sweep_history: tuple[dict[str, Any], ...]
    sources: dict[str, dict[str, Any]]


def build_dossier(conn: sqlite3.Connection, ndc_text: str) -> Dossier:
    """Assemble everything the database knows about one class."""
    ndc11 = resolve_input_ndc11(conn, ndc_text)
    resolution = resolve(conn, ndc_text)
    seed = resolution.seed_annotation
    if seed is None or seed.dims.eq_group is None:
        raise ResolveError(
            f"{ndc_text}: no TE-rated equivalence class to build a dossier for"
        )
    key = seed.dims.eq_group

    members: list[dict[str, Any]] = []
    member_ndc11s: list[str] = []
    for annotated in [seed, *resolution.tiers["T1"], *resolution.tiers["T2"]]:
        dims = annotated.dims
        if dims.ndc11 is None:
            continue
        member_ndc11s.append(dims.ndc11)
        members.append(
            {
                "ndc11": dims.ndc11,
                "ndc_as_filed": dims.package_ndc_filed,
                "name": dims.proprietary_name,
                "labeler": dims.labeler_name,
                "application": dims.appl_display,
                "te_code": dims.te_code,
                "marketed": dims.marketed,
                "pack_count": dims.pack_count,
            }
        )
    assessment = class_supply_assessment(
        conn, tuple(member_ndc11s), class_key=key
    )

    placeholders = ",".join("?" for _ in member_ndc11s)
    fda_active = tuple(
        dict(row)
        for row in conn.execute(
            f"SELECT ndc11, generic_name, status, availability, "  # noqa: S608
            f"initial_posting, update_date FROM shortage "
            f"WHERE ndc11 IN ({placeholders}) ORDER BY ndc11",
            member_ndc11s,
        )
    )

    nadac_series: dict[str, tuple[dict[str, Any], ...]] = {}
    for member in member_ndc11s:
        series = tuple(
            dict(row)
            for row in conn.execute(
                "SELECT effective_date, price, as_of_last FROM nadac "
                "WHERE ndc11 = ? ORDER BY effective_date",
                (member,),
            )
        )
        if series:
            nadac_series[member] = series

    sdud_trend = tuple(
        dict(row)
        for row in conn.execute(
            f"SELECT year, quarter, sum(units) AS units, "  # noqa: S608
            f"sum(prescriptions) AS prescriptions FROM sdud "
            f"WHERE ndc11 IN ({placeholders}) "
            "GROUP BY year, quarter ORDER BY year, quarter",
            member_ndc11s,
        )
    )

    ndc9s = sorted({m[:9] for m in member_ndc11s})
    ndc9_placeholders = ",".join("?" for _ in ndc9s)
    recall_lines = tuple(
        dict(row)
        for row in conn.execute(
            f"SELECT ndc9, classification, status, recall_initiation, "  # noqa: S608
            f"reason FROM enforcement WHERE ndc9 IN ({ndc9_placeholders}) "
            "ORDER BY recall_initiation DESC LIMIT 25",
            ndc9s,
        )
    )

    sweep_history = tuple(
        dict(row)
        for row in conn.execute(
            """
            SELECT r.run_date, c.verdict, c.fingerprints, c.drift_pct,
                   c.volume_change_pct, c.fda_listed_members
            FROM sweep_class c JOIN sweep_run r USING (sweep_id)
            WHERE c.ingredient_set = ? AND c.df_route = ?
              AND c.strength_norm = ? AND c.te_code = ?
            ORDER BY r.sweep_id
            """,
            key,
        )
    )

    return Dossier(
        class_key=key,
        rep_ndc11=ndc11,
        members=tuple(members),
        assessment=assessment,
        fda_active=fda_active,
        nadac_series=nadac_series,
        sdud_trend=sdud_trend,
        recall_lines=recall_lines,
        sweep_history=sweep_history,
        sources=source_refs(conn),
    )


def _vintage(dossier: Dossier, source: str) -> str:
    ref = dossier.sources.get(source, {})
    fetched = ref.get("fetched_at")
    return f"fetched {fetched[:10]}" if fetched else "not ingested"


def _header(dossier: Dossier) -> list[str]:
    ingredient, df_route, strength, te_code = dossier.class_key
    return [
        f"# Supply evidence: {ingredient.title()} — {df_route} — "
        f"{strength or '?'} — TE {te_code}",
        "",
        f"Representative NDC: {dossier.rep_ndc11}. "
        f"Class verdict: **{dossier.assessment.verdict}**.",
        "",
        f"> {dossier.assessment.verdict_language}",
        "",
    ]


def _evidence_sections(dossier: Dossier) -> list[str]:
    lines: list[str] = []
    a = dossier.assessment

    lines.append(f"## The class ({_vintage(dossier, 'ndc')}, "
                 f"Orange Book {_vintage(dossier, 'orangebook')})")
    lines.append("")
    lines.append("| NDC | product | labeler | application | TE | marketed |")
    lines.append("|---|---|---|---|---|---|")
    for member in dossier.members:
        lines.append(
            f"| {member['ndc_as_filed']} | {member['name'] or '?'} "
            f"| {member['labeler'] or '?'} | {member['application'] or '?'} "
            f"| {member['te_code'] or '?'} "
            f"| {'yes' if member['marketed'] else 'no'} |"
        )
    lines.append("")

    lines.append(f"## FDA shortage list ({_vintage(dossier, 'shortage')})")
    lines.append("")
    if dossier.fda_active:
        for row in dossier.fda_active:
            lines.append(
                f"- {row['ndc11']}: {row['status']} "
                f"(posted {row['initial_posting']}, updated {row['update_date']})"
            )
    else:
        lines.append(
            f"- **No entry for any of the {a.member_count} class members.** "
            "The list is manufacturer-self-reported and lagging; absence is "
            "not availability."
        )
    lines.append("")

    lines.append(f"## Acquisition-cost trend ({_vintage(dossier, 'nadac')})")
    lines.append("")
    if a.drift_pct is not None:
        lines.append(
            f"- Class acquisition cost **{a.drift_pct:+.1%}** over the "
            "trailing year on the CMS-damped NADAC index."
        )
    for member_ndc11, series in sorted(dossier.nadac_series.items()):
        first, last = series[0], series[-1]
        lines.append(
            f"- {member_ndc11}: ${first['price']:.5f} ({first['effective_date']}) "
            f"-> ${last['price']:.5f} ({last['effective_date']}), "
            f"{len(series)} rate changes on record"
        )
    if a.surveyed_count:
        lines.append(
            f"- {a.dropout_members} of {a.surveyed_count} surveyed members "
            "have stopped appearing in the weekly pharmacy survey."
        )
    lines.append("")

    lines.append(f"## Dispensed volume ({_vintage(dossier, 'sdud')})")
    lines.append("")
    for row in dossier.sdud_trend:
        lines.append(
            f"- {row['year']}Q{row['quarter']}: {row['units']:,.0f} units "
            f"({row['prescriptions']:,.0f} prescriptions), Medicaid national"
        )
    if a.volume_change_pct is not None:
        lines.append(
            f"- Year-over-year change in {a.volume_quarter}: "
            f"**{a.volume_change_pct:+.1%}**."
        )
    lines.append("")

    lines.append(f"## Recalls ({_vintage(dossier, 'enforcement')})")
    lines.append("")
    if dossier.recall_lines:
        for row in dossier.recall_lines[:10]:
            lines.append(
                f"- {row['recall_initiation']}: {row['classification']} "
                f"({row['status']}), product {row['ndc9']} — "
                f"{(row['reason'] or '')[:140]}"
            )
    else:
        lines.append("- No recall records against class members.")
    lines.append("")

    lines.append("## Assessment (all inputs above)")
    lines.append("")
    lines.append(
        f"- Independent evidence axes firing: **{a.fingerprints} of 4** "
        "(price drift, survey dropout, volume movement, recalls)."
    )
    for line in a.lines:
        lines.append(f"- {line}")
    lines.append("")

    if dossier.sweep_history:
        lines.append("## This class across sweep history")
        lines.append("")
        for row in dossier.sweep_history:
            lines.append(
                f"- {row['run_date']}: {row['verdict']} "
                f"({row['fingerprints']} fingerprints)"
            )
        lines.append("")
    return lines


def dossier_markdown(dossier: Dossier) -> str:
    """The PUBLIC case study — ingested data only (operator decision #4)."""
    lines = _header(dossier)
    lines += _evidence_sections(dossier)
    lines.append("## Reproduce this")
    lines.append("")
    lines.append("```console")
    lines.append("$ pip install uv && git clone "
                 "https://github.com/goobz22/ndc-equivalence-resolver")
    lines.append("$ uv sync && uv run ndcres refresh")
    lines.append("$ uv run ndcres sweep")
    lines.append(f"$ uv run ndcres dossier {dossier.rep_ndc11}")
    lines.append("```")
    lines.append("")
    lines.append("## Sources (every number above)")
    lines.append("")
    for key in ("ndc", "orangebook", "rxnorm", "shortage", "nadac", "sdud",
                "enforcement"):
        ref = dossier.sources.get(key)
        if ref:
            lines.append(
                f"- {ref['name']} — {ref['publisher']} — {ref['url']} "
                f"({_vintage(dossier, key)})"
            )
    lines.append("")
    lines.append(
        "*Not medical advice. Verdicts are inferences from independent "
        "public datasets — evidence consistent with a supply constraint, "
        "never a confirmed shortage and never a statement of availability. "
        "Substitution decisions belong to pharmacist and prescriber.*"
    )
    return "\n".join(lines)


def dossier_exhibits(dossier: Dossier) -> str:
    """Petition-shaped exhibit pack. Filing is the operator's decision."""
    ingredient = dossier.class_key[0].title()
    listed = dossier.assessment.verdict == VERDICT_FDA_LISTED
    lines = [
        "# DRAFT — Citizen Petition exhibit pack (21 CFR 10.30 structure)",
        "",
        "> **This is a formatted evidence draft, not legal advice and not a",
        "> filed document. Have a lawyer review before any submission.**",
        "> Petitions are filed to docket FDA-2013-S-0610 on regulations.gov;",
        "> FDA must respond within 180 days (21 CFR 10.30(e)(2)).",
        "",
        "## Requested action",
        "",
        (
            f"List {ingredient} ({dossier.class_key[1]}, "
            f"{dossier.class_key[2] or 'all strengths'}) on the FDA drug "
            "shortage database, or publish the supply/demand determination "
            "supporting its non-listing."
            if not listed
            else f"Maintain and backdate the listing for {ingredient} with "
            "the evidence below."
        ),
        "",
        "## Statement of grounds",
        "",
        "The attached exhibits, drawn ENTIRELY from federal public data "
        "(each stamped with its dataset vintage), show independent evidence "
        "consistent with a supply constraint that the voluntary shortage "
        "list does not reflect.",
        "",
    ]
    lines += _evidence_sections(dossier)
    lines += [
        "## Appendix: externally reported references — NOT pipeline data",
        "",
        "The following are corroborating reports from third parties. They "
        "are cited for completeness and are NOT part of the reproducible "
        "evidence chain above.",
        "",
    ]
    for ref in EXTERNAL_REFERENCES:
        lines.append(f"- {ref.label} ({ref.note}) — {ref.url} "
                     f"[accessed {ref.accessed}]")
    lines += [
        "",
        "## Certification (21 CFR 10.30(b))",
        "",
        "[To be completed by the petitioner upon filing: the undersigned "
        "certifies that, to the best knowledge and belief of the "
        "undersigned, this petition includes all information and views on "
        "which the petition relies, and that it includes representative "
        "data and information known to the petitioner which are "
        "unfavorable to the petition.]",
        "",
    ]
    return "\n".join(lines)


def dossier_dict(dossier: Dossier) -> dict[str, Any]:
    from .serialize import DISCLAIMER, class_assessment_dict

    ingredient, df_route, strength, te_code = dossier.class_key
    return {
        "class_key": {
            "ingredient_set": ingredient,
            "df_route": df_route,
            "strength_norm": strength,
            "te_code": te_code,
        },
        "rep_ndc11": dossier.rep_ndc11,
        "members": list(dossier.members),
        "assessment": class_assessment_dict(dossier.assessment),
        "fda_active": list(dossier.fda_active),
        "nadac_series": {
            k: list(v) for k, v in sorted(dossier.nadac_series.items())
        },
        "sdud_trend": list(dossier.sdud_trend),
        "recalls": list(dossier.recall_lines),
        "sweep_history": list(dossier.sweep_history),
        "sources": dossier.sources,
        "disclaimer": DISCLAIMER,
    }
