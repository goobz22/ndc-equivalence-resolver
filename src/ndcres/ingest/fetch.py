"""Network fetch layer — the ONLY module that touches the internet.

Every download lands in a local data directory and is then ingested from
disk, so `refresh --from-dir` can bypass this module entirely (fixtures,
air-gapped machines, CI).

Sources and verified URLs (2026-08-12):

- FDA NDC Directory:  https://www.accessdata.fda.gov/cder/ndctext.zip
- FDA Orange Book:    https://www.fda.gov/media/76860/download?attachment
- RxNorm Prescribable Content (the credential-free release; the full
  release is UTS-gated and unsupported here):
  https://download.nlm.nih.gov/rxnorm/RxNorm_full_prescribe_current.zip
- openFDA shortages bulk export (never the paginated API):
  https://download.open.fda.gov/drug/shortages/drug-shortages-0001-of-0001.json.zip
- NADAC: the CSV downloadURL is date-stamped and rotates weekly, so it is
  discovered through the data.medicaid.gov metastore on every fetch.
"""

from __future__ import annotations

import hashlib
import json
import ssl
import urllib.request
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle guard for typing only
    from . import SourceFiles

_USER_AGENT = "ndcres/0.1 (+https://github.com/goobz22/ndc-equivalence-resolver)"


def _ssl_context() -> ssl.SSLContext:
    """Prefer OS-native certificate verification when available.

    Machines behind TLS-inspecting proxies/AV present interception CAs
    that the OS trusts but OpenSSL's stricter chain rules may reject
    (e.g. "Basic Constraints of CA cert not marked critical"). The
    optional `truststore` package (install extra: `ndcres[nativetls]`)
    delegates verification to the platform verifier, matching what
    browsers and curl-with-schannel accept. Verification is NEVER
    disabled either way.
    """
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()

NDC_DIRECTORY_URL = "https://www.accessdata.fda.gov/cder/ndctext.zip"
ORANGE_BOOK_URL = "https://www.fda.gov/media/76860/download?attachment"
RXNORM_PRESCRIBABLE_URL = (
    "https://download.nlm.nih.gov/rxnorm/RxNorm_full_prescribe_current.zip"
)
SHORTAGES_BULK_URL = (
    "https://download.open.fda.gov/drug/shortages/drug-shortages-0001-of-0001.json.zip"
)
MEDICAID_METASTORE_URL = (
    "https://data.medicaid.gov/api/1/metastore/schemas/dataset/items"
)


def _download(url: str, dest: Path) -> str:
    """Download url → dest, returning the file's sha256."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    context = _ssl_context()
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, context=context) as response:  # noqa: S310
        with dest.open("wb") as handle:
            while True:
                chunk = response.read(1 << 20)
                if not chunk:
                    break
                digest.update(chunk)
                handle.write(chunk)
    return digest.hexdigest()


def _extract(zip_path: Path, members: dict[str, str], dest_dir: Path) -> dict[str, Path]:
    """Extract selected members (by case-insensitive basename) from a zip.

    ``members`` maps logical key → expected basename.
    """
    out: dict[str, Path] = {}
    with zipfile.ZipFile(zip_path) as archive:
        by_basename = {Path(name).name.lower(): name for name in archive.namelist()}
        for key, basename in members.items():
            member = by_basename.get(basename.lower())
            if member is None:
                raise FileNotFoundError(
                    f"{zip_path.name}: expected member {basename!r} not found"
                )
            target = dest_dir / basename
            with archive.open(member) as src, target.open("wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)
            out[key] = target
    return out


def fetch_ndc_directory(data_dir: Path) -> "SourceFiles":
    from . import SourceFiles

    zip_path = data_dir / "ndctext.zip"
    sha = _download(NDC_DIRECTORY_URL, zip_path)
    paths = _extract(
        zip_path, {"product": "product.txt", "package": "package.txt"}, data_dir
    )
    return SourceFiles(paths=paths, source_url=NDC_DIRECTORY_URL, file_sha256=sha)


def fetch_orange_book(data_dir: Path) -> "SourceFiles":
    from . import SourceFiles

    zip_path = data_dir / "eobzip.zip"
    sha = _download(ORANGE_BOOK_URL, zip_path)
    paths = _extract(zip_path, {"products": "products.txt"}, data_dir)
    return SourceFiles(paths=paths, source_url=ORANGE_BOOK_URL, file_sha256=sha)


def fetch_rxnorm_prescribable(data_dir: Path) -> "SourceFiles":
    from . import SourceFiles

    zip_path = data_dir / "rxnorm_prescribe.zip"
    sha = _download(RXNORM_PRESCRIBABLE_URL, zip_path)
    paths = _extract(
        zip_path,
        {"conso": "RXNCONSO.RRF", "rel": "RXNREL.RRF", "sat": "RXNSAT.RRF"},
        data_dir,
    )
    return SourceFiles(
        paths=paths, source_url=RXNORM_PRESCRIBABLE_URL, file_sha256=sha
    )


def fetch_shortages(data_dir: Path) -> "SourceFiles":
    from . import SourceFiles

    zip_path = data_dir / "drug-shortages.json.zip"
    sha = _download(SHORTAGES_BULK_URL, zip_path)
    # The shortage ingester reads the zip directly.
    return SourceFiles(
        paths={"json": zip_path}, source_url=SHORTAGES_BULK_URL, file_sha256=sha
    )


ENFORCEMENT_DOWNLOAD_INDEX = "https://api.fda.gov/download.json"


def fetch_enforcement(data_dir: Path) -> "SourceFiles":
    """openFDA drug enforcement (recalls) via the bulk export index."""
    from . import SourceFiles

    request = urllib.request.Request(
        ENFORCEMENT_DOWNLOAD_INDEX, headers={"User-Agent": _USER_AGENT}
    )
    with urllib.request.urlopen(request, context=_ssl_context()) as response:  # noqa: S310
        index = json.load(response)
    partitions = (
        index.get("results", {})
        .get("drug", {})
        .get("enforcement", {})
        .get("partitions", [])
    )
    if not partitions:
        raise RuntimeError("openFDA download index lists no enforcement partitions")

    merged: list[Any] = []
    sha = None
    for number, partition in enumerate(partitions):
        url = partition["file"]
        zip_path = data_dir / f"drug-enforcement-{number}.json.zip"
        sha = _download(url, zip_path)
        with zipfile.ZipFile(zip_path) as archive:
            for name in archive.namelist():
                if name.endswith(".json"):
                    payload = json.loads(archive.read(name))
                    merged.extend(payload.get("results", []))
    combined = data_dir / "enforcement.json"
    combined.write_text(json.dumps({"results": merged}), encoding="utf-8")
    return SourceFiles(
        paths={"json": combined},
        source_url=ENFORCEMENT_DOWNLOAD_INDEX,
        file_sha256=sha,
        dataset_vintage=str(index.get("results", {}).get("drug", {}).get(
            "enforcement", {}
        ).get("export_date")),
    )


def _discover_medicaid_datasets(title_prefix: str) -> list[dict[str, Any]]:
    """Metastore datasets whose title starts with the prefix, newest first.

    Returns dicts with 'title', 'identifier', 'modified', 'downloadURL'.
    (The downloadURL rotates weekly with a date-stamped filename — it must
    be re-discovered on every fetch, never hardcoded.)
    """
    request = urllib.request.Request(
        MEDICAID_METASTORE_URL, headers={"User-Agent": _USER_AGENT}
    )
    context = _ssl_context()
    with urllib.request.urlopen(request, context=context) as response:  # noqa: S310
        items = json.load(response)

    found: list[dict[str, Any]] = []
    for item in items:
        title = item.get("title", "")
        if not title.startswith(title_prefix):
            continue
        distributions = item.get("distribution") or []
        url = None
        for dist in distributions:
            url = dist.get("downloadURL")
            if url:
                break
        if url is None:
            continue
        found.append(
            {
                "title": title,
                "identifier": item.get("identifier"),
                "modified": item.get("modified"),
                "downloadURL": url,
            }
        )
    found.sort(key=lambda d: str(d["title"]), reverse=True)
    return found


def discover_nadac_datasets() -> list[dict[str, Any]]:
    return _discover_medicaid_datasets(
        "NADAC (National Average Drug Acquisition Cost)"
    )


def _fetch_medicaid_years(
    data_dir: Path, *, title_prefix: str, stem: str, years: int
) -> "SourceFiles":
    from . import SourceFiles

    datasets = _discover_medicaid_datasets(title_prefix)
    # Exclude non-yearly variants (e.g. "State Drug Utilization Data —
    # RESTATED", NADAC comparison files): yearly titles end with a year.
    yearly = [d for d in datasets if str(d["title"]).rstrip()[-4:].isdigit()]
    if not yearly:
        raise RuntimeError(f"{title_prefix!r} dataset discovery returned nothing")
    yearly.sort(key=lambda d: str(d["title"])[-4:], reverse=True)
    chosen = yearly[:years]
    paths: dict[str, Path] = {}
    vintages: list[str] = []
    for index, dataset in enumerate(chosen):
        dest = data_dir / f"{stem}_{index}.csv"
        _download(str(dataset["downloadURL"]), dest)
        paths[f"csv{index}"] = dest
        vintages.append(f"{dataset['title']} (modified {dataset['modified']})")
    return SourceFiles(
        paths=paths,
        source_url="; ".join(str(d["downloadURL"]) for d in chosen),
        dataset_vintage="; ".join(vintages),
    )


def fetch_nadac(data_dir: Path, *, years: int = 2) -> "SourceFiles":
    """Fetch the newest `years` NADAC yearly CSVs (cross-year drift needs 2)."""
    return _fetch_medicaid_years(
        data_dir,
        title_prefix="NADAC (National Average Drug Acquisition Cost)",
        stem="nadac",
        years=years,
    )


def fetch_sdud(data_dir: Path, *, years: int = 3) -> "SourceFiles":
    """Fetch the newest `years` State Drug Utilization yearly CSVs.

    Three years: SDUD publishes quarters with a lag, and the volume-trend
    signal compares year-over-year quarters, so two complete prior years
    plus the partial current year is the useful window.
    """
    return _fetch_medicaid_years(
        data_dir,
        title_prefix="State Drug Utilization Data",
        stem="sdud",
        years=years,
    )
