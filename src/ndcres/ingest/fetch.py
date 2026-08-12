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
    context = ssl.create_default_context()
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


def discover_nadac_datasets() -> list[dict[str, Any]]:
    """All NADAC yearly datasets from the metastore, newest first.

    Returns dicts with 'title', 'identifier', 'modified', 'downloadURL'.
    """
    request = urllib.request.Request(
        MEDICAID_METASTORE_URL, headers={"User-Agent": _USER_AGENT}
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, context=context) as response:  # noqa: S310
        items = json.load(response)

    found: list[dict[str, Any]] = []
    for item in items:
        title = item.get("title", "")
        if not title.startswith("NADAC (National Average Drug Acquisition Cost)"):
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


def fetch_nadac(data_dir: Path, *, years: int = 2) -> "SourceFiles":
    """Fetch the newest `years` NADAC yearly CSVs (cross-year drift needs 2)."""
    from . import SourceFiles

    datasets = discover_nadac_datasets()
    if not datasets:
        raise RuntimeError("NADAC dataset discovery returned nothing")
    chosen = datasets[:years]
    paths: dict[str, Path] = {}
    vintages: list[str] = []
    for index, dataset in enumerate(chosen):
        dest = data_dir / f"nadac_{index}.csv"
        _download(str(dataset["downloadURL"]), dest)
        paths[f"csv{index}"] = dest
        vintages.append(f"{dataset['title']} (modified {dataset['modified']})")
    return SourceFiles(
        paths=paths,
        source_url="; ".join(str(d["downloadURL"]) for d in chosen),
        dataset_vintage="; ".join(vintages),
    )
