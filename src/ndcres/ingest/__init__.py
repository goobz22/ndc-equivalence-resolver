"""Ingest orchestration.

``refresh`` is the single entry point: it fetches (unless given a local
directory of pre-downloaded files), ingests each requested source inside
one atomic transaction, and rebuilds the Orange-Book link table whenever
a source that feeds it changed.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .. import link, search
from ..db import clear_mirror_tables, finish_run, start_run
from . import enforcement, nadac, ndc_directory, orangebook, rxnorm, sdud, shortage
from .fetch import (
    fetch_enforcement,
    fetch_nadac,
    fetch_ndc_directory,
    fetch_orange_book,
    fetch_rxnorm_prescribable,
    fetch_sdud,
    fetch_shortages,
)

SOURCES = ("ndc", "orangebook", "rxnorm", "nadac", "shortage", "sdud", "enforcement")

# Sources whose rows feed product_ob_link.
_LINK_INPUTS = {"ndc", "orangebook"}

# Sources whose rows feed search_doc ("link" so TE-code changes propagate).
_SEARCH_INPUTS = {"ndc", "orangebook", "rxnorm", "nadac", "link"}


@dataclass(frozen=True)
class SourceFiles:
    """Local files for one source, plus provenance for source_run."""

    paths: dict[str, Path]
    source_url: str
    dataset_vintage: str | None = None
    file_sha256: str | None = None


# Filenames looked for under --from-dir, per source.
_FROM_DIR_LAYOUT: dict[str, dict[str, str]] = {
    "ndc": {"product": "product.txt", "package": "package.txt"},
    "orangebook": {"products": "products.txt"},
    "rxnorm": {
        "conso": "RXNCONSO.RRF",
        "rel": "RXNREL.RRF",
        "sat": "RXNSAT.RRF",
    },
    "shortage": {"json": "shortages.json"},
    "enforcement": {"json": "enforcement.json"},
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _from_dir_files(source: str, from_dir: Path) -> SourceFiles:
    if source in ("nadac", "sdud"):
        csvs = sorted(from_dir.glob(f"{source}*.csv"))
        if not csvs:
            raise FileNotFoundError(f"no {source}*.csv files under {from_dir}")
        return SourceFiles(
            paths={f"csv{i}": p for i, p in enumerate(csvs)},
            source_url=f"file://{from_dir}",
        )
    layout = _FROM_DIR_LAYOUT[source]
    paths: dict[str, Path] = {}
    for key, name in layout.items():
        candidate = from_dir / name
        if not candidate.exists():
            raise FileNotFoundError(f"{source}: expected {name} under {from_dir}")
        paths[key] = candidate
    return SourceFiles(paths=paths, source_url=f"file://{from_dir}")


def _fetch_files(source: str, data_dir: Path) -> SourceFiles:
    fetchers: dict[str, Callable[[Path], SourceFiles]] = {
        "ndc": fetch_ndc_directory,
        "orangebook": fetch_orange_book,
        "rxnorm": fetch_rxnorm_prescribable,
        "nadac": fetch_nadac,
        "shortage": fetch_shortages,
        "sdud": fetch_sdud,
        "enforcement": fetch_enforcement,
    }
    return fetchers[source](data_dir)


def refresh(
    conn: sqlite3.Connection,
    *,
    sources: tuple[str, ...] | None = None,
    from_dir: Path | None = None,
    data_dir: Path | None = None,
) -> dict[str, int]:
    """Fetch (or read from_dir) and ingest the requested sources.

    Returns row counts per ingested source. Each source is one atomic
    transaction: clear mirrored rows, insert, record provenance.
    """
    wanted = sources or SOURCES
    unknown = set(wanted) - set(SOURCES)
    if unknown:
        raise ValueError(f"unknown source(s): {', '.join(sorted(unknown))}")

    counts: dict[str, int] = {}
    for source in SOURCES:  # canonical order regardless of input order
        if source not in wanted:
            continue
        if from_dir is not None:
            files = _from_dir_files(source, from_dir)
        else:
            resolved_data_dir = data_dir or (Path.home() / ".ndcres" / "raw")
            files = _fetch_files(source, resolved_data_dir)
        counts[source] = _ingest_one(conn, source, files)

    if _LINK_INPUTS & set(counts):
        counts["link"] = _rebuild_link(conn)
    if _SEARCH_INPUTS & set(counts):
        counts["search"] = _rebuild_search(conn)
    return counts


def _ingest_one(conn: sqlite3.Connection, source: str, files: SourceFiles) -> int:
    with conn:
        run_id = start_run(
            conn,
            source=source,
            source_url=files.source_url,
            fetched_at=_now(),
            file_sha256=files.file_sha256,
            dataset_vintage=files.dataset_vintage,
        )
        if source != "nadac":
            clear_mirror_tables(conn, source)
        if source == "ndc":
            count = ndc_directory.ingest(
                conn, run_id, files.paths["product"], files.paths["package"]
            )
        elif source == "orangebook":
            count = orangebook.ingest(conn, run_id, files.paths["products"])
        elif source == "rxnorm":
            count = rxnorm.ingest(
                conn, run_id, files.paths["conso"], files.paths["rel"], files.paths["sat"]
            )
        elif source == "nadac":
            count = nadac.ingest(conn, run_id, tuple(files.paths.values()))
        elif source == "shortage":
            count = shortage.ingest(conn, run_id, files.paths["json"])
        elif source == "sdud":
            count = sdud.ingest(conn, run_id, tuple(files.paths.values()))
        elif source == "enforcement":
            count = enforcement.ingest(conn, run_id, files.paths["json"])
        else:  # pragma: no cover - guarded by SOURCES check
            raise AssertionError(source)
        finish_run(conn, run_id, row_count=count)
    return count


def _rebuild_link(conn: sqlite3.Connection) -> int:
    with conn:
        run_id = start_run(
            conn,
            source="link",
            source_url="derived://product_ob_link",
            fetched_at=_now(),
        )
        clear_mirror_tables(conn, "link")
        count = link.build_product_ob_link(conn, run_id)
        finish_run(conn, run_id, row_count=count)
    return count


def _rebuild_search(conn: sqlite3.Connection) -> int:
    # After the link rebuild, so TE codes land in the docs.
    with conn:
        run_id = start_run(
            conn,
            source="search",
            source_url="derived://search_doc",
            fetched_at=_now(),
        )
        clear_mirror_tables(conn, "search")
        count = search.build_search_docs(conn, run_id)
        finish_run(conn, run_id, row_count=count)
    return count
