"""openFDA drug enforcement (recall) ingest — supply-shock evidence.

A recall hitting a product family both explains current scarcity and
predicts more of it. Ingested from the openFDA bulk export (same
credential-free pattern as shortages; never the rate-limited API).

Recall records identify products loosely: `openfda.product_ndc` when
present (an array of 9-digit hyphenated product NDCs), otherwise only
free text. We index every product NDC a record carries; free-text-only
records are kept but unindexed (still countable per class by text
search, deliberately not attempted — no fuzzy matching in a tool whose
value is being right).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from ..ndc import NdcError, product_ndc_to_ndc9


def _iso(us_date: str | None) -> str | None:
    if not us_date:
        return None
    value = us_date.strip()
    # Bulk enforcement dates are YYYYMMDD; some payloads use MM/DD/YYYY.
    if len(value) == 8 and value.isdigit():
        return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
    parts = value.split("/")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        month, day, year = parts
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return value


def _load_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.endswith(".json")]
            records: list[dict[str, Any]] = []
            for name in names:
                payload = json.loads(archive.read(name))
                records.extend(payload.get("results", []))
            return records
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = payload.get("results", payload)
    if not isinstance(results, list):
        raise ValueError(f"{path.name}: expected a results array")
    return results


def ingest(conn: sqlite3.Connection, run_id: int, json_path: Path) -> int:
    count = 0
    for record in _load_records(json_path):
        raw = json.dumps(record, sort_keys=True, separators=(",", ":"))
        record_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        openfda = record.get("openfda") or {}
        product_ndcs = openfda.get("product_ndc") or []
        ndc9s: list[str] = []
        for product_ndc in product_ndcs:
            try:
                ndc9s.append(product_ndc_to_ndc9(str(product_ndc)))
            except NdcError:
                continue

        # One row per indexed ndc9 (so the class join is a plain lookup),
        # or a single unindexed row when the record names no product NDC.
        targets: list[str | None] = list(dict.fromkeys(ndc9s)) or [None]
        for index, ndc9 in enumerate(targets):
            conn.execute(
                """
                INSERT OR REPLACE INTO enforcement (
                  record_hash, ndc9, product_ndcs, classification, status,
                  recall_initiation, product_description, reason, run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{record_hash}:{index}",
                    ndc9,
                    ",".join(product_ndcs) or None,
                    record.get("classification"),
                    record.get("status"),
                    _iso(record.get("recall_initiation_date")),
                    (record.get("product_description") or "")[:400] or None,
                    (record.get("reason_for_recall") or "")[:400] or None,
                    run_id,
                ),
            )
            count += 1
    return count
