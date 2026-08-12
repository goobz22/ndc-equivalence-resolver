"""openFDA drug-shortages ingest.

Always the whole bulk export (0.42MB zip / small JSON), never the
paginated API — the unauthenticated cap is 1,000 requests/day/IP and the
dataset is tiny (~1,600 records).

Verified format facts (2026-08-12):

- ``package_ndc`` is 10-digit hyphenated in the labeler's NATIVE
  segmentation (5-3-2 / 4-4-2 / 5-4-1 coexist; two records are already
  5-4-2) — normalized here via the standard parser, which is
  deterministic because the hyphens are present.
- ``package_ndc`` is NOT unique (47 duplicates) — the primary key is a
  hash of the whole canonicalized record.
- ``status`` ∈ Current / To Be Discontinued / Resolved. ``availability``
  includes a literal upstream typo value "Unvailable" and is null on
  ~28% of records — stored verbatim, never repaired or interpreted.
- Dates are MM/DD/YYYY.
- Absence of a record means "no known shortage record" — never
  "available". Zero estradiol records exist at all as of 2026-08-12.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Any

from ..ndc import NdcError, parse_ndc


def _iso(us_date: str | None) -> str | None:
    if not us_date:
        return None
    parts = us_date.strip().split("/")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return us_date.strip()  # keep unknown spellings verbatim
    month, day, year = parts
    return f"{year}-{int(month):02d}-{int(day):02d}"


def _load_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.endswith(".json")]
            if not names:
                raise ValueError(f"{path.name}: no JSON member in zip")
            payload = json.loads(archive.read(names[0]))
    else:
        payload = json.loads(path.read_text(encoding="utf-8"))
    results = payload.get("results", payload)
    if not isinstance(results, list):
        raise ValueError(f"{path.name}: expected a results array")
    return results


def ingest(conn: sqlite3.Connection, run_id: int, json_path: Path) -> int:
    count = 0
    for record in _load_records(json_path):
        raw_json = json.dumps(record, sort_keys=True, separators=(",", ":"))
        record_hash = hashlib.sha256(raw_json.encode("utf-8")).hexdigest()

        ndc11: str | None = None
        package_ndc = record.get("package_ndc")
        if isinstance(package_ndc, str) and package_ndc.strip():
            try:
                query = parse_ndc(package_ndc)
                if not query.ambiguous:
                    ndc11 = query.ndc11
            except NdcError:
                ndc11 = None

        conn.execute(
            """
            INSERT OR REPLACE INTO shortage (
              record_hash, ndc11, ndc9, generic_name, company_name, status,
              availability, shortage_reason, initial_posting, update_date,
              raw_json, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_hash,
                ndc11,
                ndc11[:9] if ndc11 else None,
                record.get("generic_name"),
                record.get("company_name"),
                record.get("status"),
                record.get("availability"),
                record.get("shortage_reason"),
                _iso(record.get("initial_posting_date")),
                _iso(record.get("update_date")),
                raw_json,
                run_id,
            ),
        )
        count += 1
    return count
