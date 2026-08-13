"""NADAC ingest (weekly acquisition-cost CSVs from data.medicaid.gov).

Verified format facts (2026 dataset):

- CSV with quoted fields — ``Explanation Code`` can be a quoted
  comma-list ("1, 5, 6"), so a real CSV parser is mandatory.
- ``NDC`` is 11-digit zero-padded hyphenless TEXT — the canonical join
  key of this whole system.
- CSV dates are MM/DD/YYYY (the datastore API returns ISO for the same
  rows — two formats for one dataset).
- Weekly files are full replacements that re-state unchanged prices, so
  rows are merged on (ndc11, effective_date) with as_of_first/as_of_last
  bookkeeping — this table intentionally accumulates history (the
  survey-dropout signal needs it; the official Comparison dataset does
  NOT reflect NDC terminations).
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Sequence

_EXPECTED_HEADER = [
    "NDC Description",
    "NDC",
    "NADAC Per Unit",
    "Effective Date",
    "Pricing Unit",
    "Pharmacy Type Indicator",
    "OTC",
    "Explanation Code",
    "Classification for Rate Setting",
    "Corresponding Generic Drug NADAC Per Unit",
    "Corresponding Generic Drug Effective Date",
    "As of Date",
]


def _iso(us_date: str) -> str | None:
    """MM/DD/YYYY → ISO; ISO passes through (datastore-API exports)."""
    value = us_date.strip()
    if not value:
        return None
    if len(value) == 10 and value[4] == "-":
        return value
    parts = value.split("/")
    if len(parts) != 3:
        return None
    month, day, year = parts
    if not (month.isdigit() and day.isdigit() and year.isdigit()):
        return None
    return f"{year}-{int(month):02d}-{int(day):02d}"


def ingest(conn: sqlite3.Connection, run_id: int, csv_paths: Sequence[Path]) -> int:
    count = 0
    for path in csv_paths:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            # CMS respelled the columns across vintages — spaces
            # ("NADAC Per Unit", 2024+), Title_Case underscores
            # (2021-2023), and lowercase snake_case (2019-2020) — same
            # columns, same order every time (verified against the
            # 2018-2026 yearly datasets). All three spellings are
            # ACCEPTED explicitly by case/underscore normalization; a
            # different column set or order still refuses.
            normalized = (
                [column.replace("_", " ").strip().lower() for column in header]
                if header is not None
                else None
            )
            expected_normalized = [column.lower() for column in _EXPECTED_HEADER]
            if normalized != expected_normalized:
                raise ValueError(
                    f"{path.name}: header drifted from the verified NADAC layout; "
                    "refusing to guess column positions"
                )
            for fields in reader:
                if len(fields) != len(_EXPECTED_HEADER):
                    continue
                row = dict(zip(_EXPECTED_HEADER, fields))
                ndc11 = row["NDC"].strip()
                if len(ndc11) != 11 or not ndc11.isdigit():
                    continue
                effective = _iso(row["Effective Date"])
                as_of = _iso(row["As of Date"])
                if effective is None or as_of is None:
                    continue
                try:
                    price = float(row["NADAC Per Unit"])
                except ValueError:
                    continue
                explanation = ",".join(
                    part.strip()
                    for part in row["Explanation Code"].split(",")
                    if part.strip()
                )
                conn.execute(
                    """
                    INSERT INTO nadac (
                      ndc11, effective_date, price, pricing_unit, description,
                      classification, explanation_codes, as_of_first,
                      as_of_last, run_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (ndc11, effective_date) DO UPDATE SET
                      price = excluded.price,
                      pricing_unit = excluded.pricing_unit,
                      description = excluded.description,
                      classification = excluded.classification,
                      explanation_codes = excluded.explanation_codes,
                      as_of_first = min(as_of_first, excluded.as_of_first),
                      as_of_last = max(as_of_last, excluded.as_of_last),
                      run_id = excluded.run_id
                    """,
                    (
                        ndc11,
                        effective,
                        price,
                        row["Pricing Unit"].strip() or None,
                        row["NDC Description"].strip() or None,
                        row["Classification for Rate Setting"].strip() or None,
                        explanation or None,
                        as_of,
                        as_of,
                        run_id,
                    ),
                )
                count += 1
    return count
