"""Independent-listing corroborations (SPEC §12): citation-only.

Curated, dated citations showing that a class this instrument flags is
ALSO listed by another public shortage regime (ASHP; the mandatory-
reporting lists in Australia / Canada / the UK). They are the output of
the recorded precision audit (docs/dossiers/), follow the same
separation rule as the dossier's EXTERNAL_REFERENCES — externally
reported, NOT pipeline data — and are rendered with their source and
access date, worded "also listed by", never "confirmed".

HARD RULE (pinned by test): corroborations never feed a verdict, a
fingerprint, or a ranking. They annotate the gap report; the US
evidence stands on its own.

Rows key on the equivalence-class key. Staleness policy: access dates
are always rendered; re-verification happens with the recorded gaps
re-review triggers (threshold changes; top-10 composition shifts), not
a wall-clock timer.
"""

from __future__ import annotations

from dataclasses import dataclass

ClassKey = tuple[str, str, str, str]


@dataclass(frozen=True)
class CorroborationSource:
    source: str  # 'ashp' | 'au-tga' | 'ca-hps' | 'uk-dhsc'
    url: str
    accessed: str  # YYYY-MM-DD
    note: str


@dataclass(frozen=True)
class Corroboration:
    class_key: ClassKey
    sources: tuple[CorroborationSource, ...]


SOURCE_LABELS: dict[str, str] = {
    "ashp": "ASHP (US practitioner-reported list)",
    "au-tga": "Australia TGA (mandatory reporting)",
    "ca-hps": "Health Product Shortages Canada (mandatory reporting)",
    "uk-dhsc": "UK DHSC/NHS supply notifications",
}

# Populated by the precision audit (docs/dossiers/2026-08-gaps-precision-
# audit.md is the recorded evidence for every entry).
CORROBORATIONS: tuple[Corroboration, ...] = (
    Corroboration(
        class_key=('TEMOZOLOMIDE', 'CAPSULE;ORAL', 'UG:180000', 'AB'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://apps.tga.gov.au/Prod/msi/Search/Details/temozolomide',
                accessed='2026-08-14',
                note='Temizole 140 mg capsules Limited Availability to 2026-09-30; Temodal discontinuations (same molecule and form)',
            ),
        ),
    ),
    Corroboration(
        class_key=('CINACALCET HYDROCHLORIDE', 'TABLET;ORAL', 'UG:60000', 'AB'),
        sources=(
            CorroborationSource(
                source='ca-hps',
                url='https://www.drugshortagescanada.ca/shortage/215865',
                accessed='2026-08-14',
                note='JAMP and Teva cinacalcet tablet shortage reports under the mandatory-reporting regime; current live status behind a registration wall',
            ),
        ),
    ),
    Corroboration(
        class_key=('CINACALCET HYDROCHLORIDE', 'TABLET;ORAL', 'UG:90000', 'AB'),
        sources=(
            CorroborationSource(
                source='ca-hps',
                url='https://www.drugshortagescanada.ca/shortage/215865',
                accessed='2026-08-14',
                note='JAMP and Teva cinacalcet tablet shortage reports under the mandatory-reporting regime; current live status behind a registration wall',
            ),
        ),
    ),
    Corroboration(
        class_key=('CHLORTHALIDONE', 'TABLET;ORAL', 'UG:25000', 'AB'),
        sources=(
            CorroborationSource(
                source='ca-hps',
                url='https://healthproductshortages.ca/shortage/246071',
                accessed='2026-08-14',
                note='APO-Chlorthalidone shortage report updated 2025-08-22; provincial interchangeability notices through late 2025 (25 mg strengths named)',
            ),
        ),
    ),
    Corroboration(
        class_key=('TRIAMCINOLONE ACETONIDE', 'INJECTABLE;INJECTION', 'RAW:40MG/ML', 'AB'),
        sources=(
            CorroborationSource(
                source='ashp',
                url='https://www.ashp.org/drug-shortages/current-shortages/drug-shortage-detail.aspx?id=1163',
                accessed='2026-08-14',
                note='Triamcinolone acetonide injectable suspension bulletin, updated 2026-04-21: allocation and backorders across manufacturers',
            ),
            CorroborationSource(
                source='ca-hps',
                url='https://healthproductshortages.ca/shortage/255147',
                accessed='2026-08-14',
                note='Kenalog-40 shortage report updated 2026-04-14',
            ),
        ),
    ),
    Corroboration(
        class_key=('CHLORTHALIDONE', 'TABLET;ORAL', 'UG:50000', 'AB'),
        sources=(
            CorroborationSource(
                source='ca-hps',
                url='https://healthproductshortages.ca/shortage/246071',
                accessed='2026-08-14',
                note='APO-Chlorthalidone shortage report updated 2025-08-22; provincial interchangeability notices through late 2025 (25 mg strengths named)',
            ),
        ),
    ),
    Corroboration(
        class_key=('ENALAPRIL MALEATE', 'TABLET;ORAL', 'UG:5000', 'AB'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://apps.tga.gov.au/shortages/search/Details/enalapril-maleate',
                accessed='2026-08-14',
                note='Renitec 20 mg Limited Availability; Acetec 5 mg anticipated shortage into 2027 (same molecule and form)',
            ),
        ),
    ),
    Corroboration(
        class_key=('GLIMEPIRIDE', 'TABLET;ORAL', 'UG:4000', 'AB'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://apps.tga.gov.au/Prod/msi/Search/Details/glimepiride',
                accessed='2026-08-14',
                note='Glimepiride Sandoz 2 mg tablet shortage Dec 2025 - Jun 2026, since resolved (same molecule and form)',
            ),
        ),
    ),
    Corroboration(
        class_key=('ENALAPRIL MALEATE', 'TABLET;ORAL', 'UG:2500', 'AB'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://apps.tga.gov.au/shortages/search/Details/enalapril-maleate',
                accessed='2026-08-14',
                note='Renitec 20 mg Limited Availability; Acetec 5 mg anticipated shortage into 2027 (same molecule and form)',
            ),
        ),
    ),
    Corroboration(
        class_key=('GLIMEPIRIDE', 'TABLET;ORAL', 'UG:2000', 'AB'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://apps.tga.gov.au/Prod/msi/Search/Details/glimepiride',
                accessed='2026-08-14',
                note='Glimepiride Sandoz 2 mg tablet shortage Dec 2025 - Jun 2026, since resolved (same molecule and form)',
            ),
        ),
    ),
    Corroboration(
        class_key=('DILTIAZEM HYDROCHLORIDE', 'CAPSULE, EXTENDED RELEASE;ORAL', 'UG:180000', 'AB3'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://apps.tga.gov.au/Prod/msi/Search/Details/diltiazem%20hydrochloride',
                accessed='2026-08-14',
                note='Cardizem CD 360 mg modified-release discontinued 2026-06; successor to-be-discontinued Nov 2026 (same molecule and form; supply-exit)',
            ),
        ),
    ),
    Corroboration(
        class_key=('TEMOZOLOMIDE', 'CAPSULE;ORAL', 'UG:140000', 'AB'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://apps.tga.gov.au/Prod/msi/Search/Details/temozolomide',
                accessed='2026-08-14',
                note='Temizole 140 mg capsules Limited Availability to 2026-09-30 (matching strength and form)',
            ),
        ),
    ),
    Corroboration(
        class_key=('VARENICLINE TARTRATE', 'TABLET;ORAL', 'UG:500', 'AB'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://www.tga.gov.au/safety-and-shortages/safety-monitoring-and-information/safety-alerts/varenicline-champix',
                accessed='2026-08-14',
                note='Champix 1 mg tablets Unavailable, expected supply unknown (same molecule and form; adjacent strength)',
            ),
        ),
    ),
    Corroboration(
        class_key=('DILTIAZEM HYDROCHLORIDE', 'TABLET, EXTENDED RELEASE;ORAL', 'UG:180000', 'AB'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://apps.tga.gov.au/Prod/msi/Search/Details/diltiazem%20hydrochloride',
                accessed='2026-08-14',
                note='Cardizem CD 360 mg modified-release discontinued 2026-06; successor to-be-discontinued Nov 2026 (same molecule and form; supply-exit)',
            ),
        ),
    ),
    Corroboration(
        class_key=('COLESEVELAM HYDROCHLORIDE', 'TABLET;ORAL', 'UG:625000', 'AB'),
        sources=(
            CorroborationSource(
                source='ca-hps',
                url='https://medsask.usask.ca/sites/medsask/files/2024-07/dpeb-892-US-colesevelam.pdf',
                accessed='2026-08-14',
                note='Health Canada critical shortage with exceptional importation of US-labelled 625 mg tablets (2024 peak; recency caveat)',
            ),
        ),
    ),
    Corroboration(
        class_key=('LABETALOL HYDROCHLORIDE', 'INJECTABLE;INJECTION', 'RAW:5MG/ML', 'AP'),
        sources=(
            CorroborationSource(
                source='ashp',
                url='https://www.ashp.org/drug-shortages/current-shortages/drug-shortage-detail.aspx?id=793',
                accessed='2026-08-14',
                note='Labetalol injection bulletin, updated 2026-04-21: manufacturing delays and backorders with no release date',
            ),
        ),
    ),
    Corroboration(
        class_key=('PIMECROLIMUS', 'CREAM;TOPICAL', 'RAW:1%', 'AB'),
        sources=(
            CorroborationSource(
                source='ashp',
                url='https://www.ashp.org/drug-shortages/current-shortages/drug-shortage-detail.aspx?id=1137',
                accessed='2026-08-14',
                note='Pimecrolimus cream bulletin: one manufacturer in shortage, reason not given',
            ),
        ),
    ),
    Corroboration(
        class_key=('TERIFLUNOMIDE', 'TABLET;ORAL', 'UG:7000', 'AB'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://apps.tga.gov.au/Prod/msi/Search/Details/teriflunomide',
                accessed='2026-08-14',
                note='Teriflunomide Sandoz 14 mg Limited Availability to Nov 2026 (same molecule and form; adjacent strength)',
            ),
        ),
    ),
    Corroboration(
        class_key=('DILTIAZEM HYDROCHLORIDE', 'TABLET, EXTENDED RELEASE;ORAL', 'UG:420000', 'AB'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://apps.tga.gov.au/Prod/msi/Search/Details/diltiazem%20hydrochloride',
                accessed='2026-08-14',
                note='Cardizem CD 360 mg modified-release discontinued 2026-06; successor to-be-discontinued Nov 2026 (same molecule and form; supply-exit)',
            ),
        ),
    ),
    Corroboration(
        class_key=('DILTIAZEM HYDROCHLORIDE', 'TABLET, EXTENDED RELEASE;ORAL', 'UG:300000', 'AB'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://apps.tga.gov.au/Prod/msi/Search/Details/diltiazem%20hydrochloride',
                accessed='2026-08-14',
                note='Cardizem CD 360 mg modified-release discontinued 2026-06; successor to-be-discontinued Nov 2026 (same molecule and form; supply-exit)',
            ),
        ),
    ),
    Corroboration(
        class_key=('DILTIAZEM HYDROCHLORIDE', 'TABLET, EXTENDED RELEASE;ORAL', 'UG:120000', 'AB'),
        sources=(
            CorroborationSource(
                source='au-tga',
                url='https://apps.tga.gov.au/Prod/msi/Search/Details/diltiazem%20hydrochloride',
                accessed='2026-08-14',
                note='Cardizem CD 360 mg modified-release discontinued 2026-06; successor to-be-discontinued Nov 2026 (same molecule and form; supply-exit)',
            ),
        ),
    ),
    Corroboration(
        class_key=('CALCIUM CHLORIDE|POTASSIUM CHLORIDE|SODIUM CHLORIDE|SODIUM LACTATE', 'INJECTABLE;INJECTION', 'RAW:20MG/100ML;30MG/100ML;600MG/100ML;310MG/100ML', 'AP'),
        sources=(
            CorroborationSource(
                source='ashp',
                url='https://www.ashp.org/drug-shortages/current-shortages/drug-shortage-detail.aspx?id=1099',
                accessed='2026-08-14',
                note="Lactated Ringer's irrigation bulletin, created 2024-10, updated 2025-07",
            ),
            CorroborationSource(
                source='au-tga',
                url='https://www.tga.gov.au/safety/shortages-and-supply-disruptions/medicine-shortages/major-or-ongoing-medicine-shortages/about-shortage-intravenous-iv-fluids',
                accessed='2026-08-14',
                note="Hartmann's solution national shortage 2024-2025 with Section 19A overseas substitution",
            ),
        ),
    ),
    Corroboration(
        class_key=('PREDNISONE', 'TABLET;ORAL', 'UG:50000', 'AB'),
        sources=(
            CorroborationSource(
                source='ashp',
                url='https://www.ashp.org/drug-shortages/current-shortages/drug-shortage-detail.aspx?id=563',
                accessed='2026-08-14',
                note='Prednisone tablets bulletin, updated 2026-05-19: 10 mg backordered; 50 mg listed available by one manufacturer (molecule and form bulletin; strength caveat)',
            ),
        ),
    ),
    Corroboration(
        class_key=('LANTHANUM CARBONATE', 'TABLET, CHEWABLE;ORAL', 'UG:750000', 'AB'),
        sources=(
            CorroborationSource(
                source='ashp',
                url='https://www.ashp.org/drug-shortages/current-shortages/drug-shortage-detail.aspx?id=1145',
                accessed='2026-08-14',
                note='Lanthanum carbonate oral presentations bulletin, updated 2025-12-16: 750 and 1000 mg intermittent backorder',
            ),
        ),
    ),
    Corroboration(
        class_key=('ESTRADIOL', 'SYSTEM;TRANSDERMAL', 'UG24H:25', 'AB1'),
        sources=(
            CorroborationSource(
                source='ashp',
                url='https://www.ashp.org/drug-shortages/current-shortages/drug-shortage-detail.aspx?id=1206',
                accessed='2026-08-14',
                note='Estradiol transdermal system bulletin, created 2026-01-30, updated 2026-04-22: 14 twice-weekly patch products on backorder or allocation',
            ),
            CorroborationSource(
                source='au-tga',
                url='https://www.tga.gov.au/safety/shortages-and-supply-disruptions/medicine-shortages/major-or-ongoing-medicine-shortages/about-shortage-transdermal-hrt-patches',
                accessed='2026-08-14',
                note='Estradot patches Limited Availability with expected supply Dec 2026; Section 19A overseas substitution approved',
            ),
            CorroborationSource(
                source='uk-dhsc',
                url='https://cpe.org.uk/our-news/ssps-for-estradot-patches-ssp079-ssp080-ssp081-ssp082-further-extended/',
                accessed='2026-08-14',
                note='Serious Shortage Protocols SSP079-082 for Estradot patches, repeatedly extended to 2026-10-02',
            ),
            CorroborationSource(
                source='ca-hps',
                url='https://healthproductshortages.ca/ingredient/1290',
                accessed='2026-08-14',
                note='Multiple active Estradot shortage reports under the mandatory-reporting regime',
            ),
        ),
    ),
    Corroboration(
        class_key=('ESTRADIOL', 'SYSTEM;TRANSDERMAL', 'UG24H:50', 'AB1'),
        sources=(
            CorroborationSource(
                source='ashp',
                url='https://www.ashp.org/drug-shortages/current-shortages/drug-shortage-detail.aspx?id=1206',
                accessed='2026-08-14',
                note='Estradiol transdermal system bulletin, created 2026-01-30, updated 2026-04-22: 14 twice-weekly patch products on backorder or allocation',
            ),
            CorroborationSource(
                source='au-tga',
                url='https://www.tga.gov.au/safety/shortages-and-supply-disruptions/medicine-shortages/major-or-ongoing-medicine-shortages/about-shortage-transdermal-hrt-patches',
                accessed='2026-08-14',
                note='Estradot patches Limited Availability with expected supply Dec 2026; Section 19A overseas substitution approved',
            ),
            CorroborationSource(
                source='uk-dhsc',
                url='https://cpe.org.uk/our-news/ssps-for-estradot-patches-ssp079-ssp080-ssp081-ssp082-further-extended/',
                accessed='2026-08-14',
                note='Serious Shortage Protocols SSP079-082 for Estradot patches, repeatedly extended to 2026-10-02',
            ),
            CorroborationSource(
                source='ca-hps',
                url='https://healthproductshortages.ca/ingredient/1290',
                accessed='2026-08-14',
                note='Multiple active Estradot shortage reports under the mandatory-reporting regime',
            ),
        ),
    ),
    Corroboration(
        class_key=('ESTRADIOL', 'SYSTEM;TRANSDERMAL', 'UG24H:37.5', 'AB1'),
        sources=(
            CorroborationSource(
                source='ashp',
                url='https://www.ashp.org/drug-shortages/current-shortages/drug-shortage-detail.aspx?id=1206',
                accessed='2026-08-14',
                note='Estradiol transdermal system bulletin, created 2026-01-30, updated 2026-04-22: 14 twice-weekly patch products on backorder or allocation',
            ),
            CorroborationSource(
                source='au-tga',
                url='https://www.tga.gov.au/safety/shortages-and-supply-disruptions/medicine-shortages/major-or-ongoing-medicine-shortages/about-shortage-transdermal-hrt-patches',
                accessed='2026-08-14',
                note='Twice-weekly patch family listed; the 37.5 mcg strength itself marked resolved in Australia',
            ),
        ),
    ),
    Corroboration(
        class_key=('ESTRADIOL', 'SYSTEM;TRANSDERMAL', 'UG24H:75', 'AB1'),
        sources=(
            CorroborationSource(
                source='ashp',
                url='https://www.ashp.org/drug-shortages/current-shortages/drug-shortage-detail.aspx?id=1206',
                accessed='2026-08-14',
                note='Estradiol transdermal system bulletin, created 2026-01-30, updated 2026-04-22: 14 twice-weekly patch products on backorder or allocation',
            ),
            CorroborationSource(
                source='au-tga',
                url='https://www.tga.gov.au/safety/shortages-and-supply-disruptions/medicine-shortages/major-or-ongoing-medicine-shortages/about-shortage-transdermal-hrt-patches',
                accessed='2026-08-14',
                note='Estradot patches Limited Availability with expected supply Dec 2026; Section 19A overseas substitution approved',
            ),
            CorroborationSource(
                source='uk-dhsc',
                url='https://cpe.org.uk/our-news/ssps-for-estradot-patches-ssp079-ssp080-ssp081-ssp082-further-extended/',
                accessed='2026-08-14',
                note='Serious Shortage Protocols SSP079-082 for Estradot patches, repeatedly extended to 2026-10-02',
            ),
            CorroborationSource(
                source='ca-hps',
                url='https://healthproductshortages.ca/ingredient/1290',
                accessed='2026-08-14',
                note='Multiple active Estradot shortage reports under the mandatory-reporting regime',
            ),
        ),
    ),
)

_INDEX: dict[ClassKey, tuple[CorroborationSource, ...]] = {
    entry.class_key: entry.sources for entry in CORROBORATIONS
}


def corroborations_for(class_key: ClassKey) -> tuple[CorroborationSource, ...]:
    return _INDEX.get(class_key, ())
