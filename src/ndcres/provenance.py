"""Provenance registry: every datum names its source, with a URL (SPEC §9).

The single home for source identity. Static identity (publisher, landing
URL, license posture) lives in SOURCE_REGISTRY; live state (vintage,
fetched_at, sha256) comes from the source_run table each row already
references. `source_refs(conn)` merges the two into the JSON-shaped refs
that every serialized payload carries and every UI data block renders as
a "Source: … · vintage … ↗" line.

Deep links point INTO the upstream system where it has a stable URL
scheme (the Orange Book's per-application results page, RxNav's
per-RXCUI browser). These are outbound citation links only — nothing is
fetched from them.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any, TypedDict


class SourceIdentity(TypedDict):
    name: str
    publisher: str
    url: str
    license: str


SOURCE_REGISTRY: dict[str, SourceIdentity] = {
    "ndc": {
        "name": "FDA National Drug Code Directory",
        "publisher": "U.S. Food & Drug Administration",
        "url": (
            "https://www.fda.gov/drugs/drug-approvals-and-databases/"
            "national-drug-code-directory"
        ),
        "license": "U.S. government work (public domain)",
    },
    "orangebook": {
        "name": "FDA Orange Book (Approved Drug Products with Therapeutic "
        "Equivalence Evaluations)",
        "publisher": "U.S. Food & Drug Administration",
        "url": (
            "https://www.fda.gov/drugs/drug-approvals-and-databases/"
            "approved-drug-products-therapeutic-equivalence-evaluations-orange-book"
        ),
        "license": "U.S. government work (public domain)",
    },
    "rxnorm": {
        "name": "RxNorm (Current Prescribable Content)",
        "publisher": "U.S. National Library of Medicine",
        "url": "https://www.nlm.nih.gov/research/umls/rxnorm/docs/prescribe.html",
        "license": "No license required (courtesy attribution to NLM)",
    },
    "shortage": {
        "name": "FDA Drug Shortages database (via openFDA)",
        "publisher": "U.S. Food & Drug Administration",
        "url": "https://dps.fda.gov/drugshortages",
        "license": "U.S. government work (public domain)",
    },
    "nadac": {
        "name": "NADAC (National Average Drug Acquisition Cost)",
        "publisher": "Centers for Medicare & Medicaid Services",
        "url": "https://data.medicaid.gov/datasets?fulltext=NADAC",
        "license": "U.S. government open data",
    },
    "sdud": {
        "name": "Medicaid State Drug Utilization Data",
        "publisher": "Centers for Medicare & Medicaid Services",
        "url": (
            "https://www.medicaid.gov/medicaid/prescription-drugs/"
            "state-drug-utilization-data/index.html"
        ),
        "license": "U.S. government open data",
    },
    "enforcement": {
        "name": "FDA drug recall enforcement reports (via openFDA)",
        "publisher": "U.S. Food & Drug Administration",
        "url": "https://open.fda.gov/apis/drug/enforcement/",
        "license": "U.S. government work (public domain)",
    },
    # Derived tables: computed here from the sources above; they cite this
    # repository's own build step so a ref is never silently missing.
    "link": {
        "name": "NDC-to-Orange-Book application link (derived)",
        "publisher": "ndc-equivalence-resolver build step",
        "url": "https://github.com/goobz22/ndc-equivalence-resolver",
        "license": "MIT (derived from public-domain sources)",
    },
    "search": {
        "name": "Search index (derived)",
        "publisher": "ndc-equivalence-resolver build step",
        "url": "https://github.com/goobz22/ndc-equivalence-resolver",
        "license": "MIT (derived from public-domain sources)",
    },
}

_APPL_RE = re.compile(r"^(ANDA|NDA|BLA)\s*0*(\d+)$", re.IGNORECASE)


def ob_application_url(appl_display: str | None) -> str | None:
    """Deep link to the Orange Book results page for one application.

    Accepts the display form the resolver emits ("ANDA201675",
    "NDA020538") and returns the accessdata search-results URL — the
    page that shows the application's products WITH their TE codes,
    i.e. the primary citation for every TE claim.
    """
    if not appl_display:
        return None
    match = _APPL_RE.match(appl_display.strip())
    if not match:
        return None
    kind = match.group(1).upper()
    appl_type = "A" if kind == "ANDA" else "N"
    number = match.group(2).zfill(6)
    return (
        "https://www.accessdata.fda.gov/scripts/cder/ob/results_product.cfm"
        f"?Appl_Type={appl_type}&Appl_No={number}"
    )


def rxnav_url(rxcui: str | None) -> str | None:
    """Deep link to RxNav's concept browser for one RXCUI."""
    if not rxcui:
        return None
    return f"https://mor.nlm.nih.gov/RxNav/search?searchBy=RXCUI&searchTerm={rxcui}"


def source_refs(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """Registry identity merged with the latest source_run per source.

    Every serialized payload carries this map (SPEC §9); a source that
    has never been ingested still appears with its identity and null
    vintage — absence of data is shown, never hidden.
    """
    runs: dict[str, sqlite3.Row] = {}
    for row in conn.execute(
        """
        SELECT source, fetched_at, dataset_vintage, file_sha256,
               MAX(run_id) AS run_id
        FROM source_run
        GROUP BY source
        """
    ):
        runs[row["source"]] = row
    refs: dict[str, dict[str, Any]] = {}
    for key, identity in SOURCE_REGISTRY.items():
        run = runs.get(key)
        refs[key] = {
            "name": identity["name"],
            "publisher": identity["publisher"],
            "url": identity["url"],
            "license": identity["license"],
            "vintage": run["dataset_vintage"] if run else None,
            "fetched_at": run["fetched_at"] if run else None,
            "sha256": run["file_sha256"] if run else None,
        }
    return refs
