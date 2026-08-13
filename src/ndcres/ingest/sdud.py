"""Medicaid State Drug Utilization Data (SDUD) ingest — the demand axis.

SDUD reports actual dispensed volume (units and prescription counts) per
NDC per state per quarter. We aggregate to national (ndc11, year,
quarter) totals at ingest, because the resolver's question is "is the
national dispensed volume of this drug collapsing while its price
rises?" — the classic public fingerprint of a supply constraint.

Format facts:

- CSV with a header; the NDC column is 11-digit hyphenless (the same
  canonical form NADAC uses).
- Small counts are SUPPRESSED for privacy: `Suppression Used` is
  "true"/"false" and suppressed rows carry blank measures — they are
  skipped (they represent negligible volume by construction).
- Column order has varied across vintages, so columns are located by
  header name, case-insensitively, not by position.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Sequence

_REQUIRED = ("ndc", "year", "quarter", "units reimbursed", "suppression used")


def _header_index(header: list[str]) -> dict[str, int]:
    lookup = {name.strip().lower(): index for index, name in enumerate(header)}
    missing = [name for name in _REQUIRED if name not in lookup]
    if missing:
        raise ValueError(
            f"SDUD header is missing expected column(s) {missing}; refusing "
            "to guess positions"
        )
    return lookup


def ingest(conn: sqlite3.Connection, run_id: int, csv_paths: Sequence[Path]) -> int:
    totals: dict[tuple[str, int, int], list[float]] = {}
    for path in csv_paths:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header is None:
                continue
            lookup = _header_index(header)
            ndc_i = lookup["ndc"]
            year_i = lookup["year"]
            quarter_i = lookup["quarter"]
            units_i = lookup["units reimbursed"]
            suppressed_i = lookup["suppression used"]
            rx_i = lookup.get("number of prescriptions")

            for fields in reader:
                if len(fields) <= max(ndc_i, year_i, quarter_i, units_i, suppressed_i):
                    continue
                if fields[suppressed_i].strip().lower() == "true":
                    continue
                ndc11 = fields[ndc_i].strip()
                if len(ndc11) != 11 or not ndc11.isdigit():
                    continue
                try:
                    year = int(fields[year_i])
                    quarter = int(fields[quarter_i])
                    units = float(fields[units_i] or 0)
                    prescriptions = (
                        float(fields[rx_i] or 0) if rx_i is not None else 0.0
                    )
                except ValueError:
                    continue
                key = (ndc11, year, quarter)
                bucket = totals.setdefault(key, [0.0, 0.0, 0.0])
                bucket[0] += units
                bucket[1] += prescriptions
                bucket[2] += 1

    for (ndc11, year, quarter), (units, prescriptions, state_rows) in totals.items():
        conn.execute(
            """
            INSERT OR REPLACE INTO sdud
              (ndc11, year, quarter, units, prescriptions, state_rows, run_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ndc11, year, quarter, units, prescriptions, int(state_rows), run_id),
        )
    return len(totals)
