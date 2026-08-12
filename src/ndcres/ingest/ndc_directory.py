"""FDA NDC Directory ingest (product.txt + package.txt from ndctext.zip).

Verified format facts (2026-08-12 snapshot):

- Tab-delimited, CRLF, no quoting or escaping anywhere.
- ``product.txt`` is **cp1252** (0x92 smart quotes in labeler names —
  UTF-8 decoding crashes, latin-1 renders C1 controls). ``package.txt``
  is ASCII; decoded as cp1252 for uniformity.
- ``NDC_EXCLUDE_FLAG`` is 'N' on 100% of rows — carries no signal.
- Discontinued brands are ABSENT from the file, not end-dated.
- Dates are YYYYMMDD, blank when unset.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ..db import special_case_value
from ..formfamily import form_family
from ..ndc import NdcError, parse_ndc, product_ndc_to_ndc9
from ..packaging import parse_package_description
from ..strength import normalize_ndc_strength

_PRODUCT_COLUMNS = [
    "PRODUCTID",
    "PRODUCTNDC",
    "PRODUCTTYPENAME",
    "PROPRIETARYNAME",
    "PROPRIETARYNAMESUFFIX",
    "NONPROPRIETARYNAME",
    "DOSAGEFORMNAME",
    "ROUTENAME",
    "STARTMARKETINGDATE",
    "ENDMARKETINGDATE",
    "MARKETINGCATEGORYNAME",
    "APPLICATIONNUMBER",
    "LABELERNAME",
    "SUBSTANCENAME",
    "ACTIVE_NUMERATOR_STRENGTH",
    "ACTIVE_INGRED_UNIT",
    "PHARM_CLASSES",
    "DEASCHEDULE",
    "NDC_EXCLUDE_FLAG",
    "LISTING_RECORD_CERTIFIED_THROUGH",
]

_PACKAGE_COLUMNS = [
    "PRODUCTID",
    "PRODUCTNDC",
    "NDCPACKAGECODE",
    "PACKAGEDESCRIPTION",
    "STARTMARKETINGDATE",
    "ENDMARKETINGDATE",
    "NDC_EXCLUDE_FLAG",
    "SAMPLE_PACKAGE",
]


def _read_rows(path: Path, expected_columns: list[str]) -> list[dict[str, str]]:
    text = path.read_text(encoding="cp1252")
    lines = text.split("\r\n") if "\r\n" in text else text.splitlines()
    header = lines[0].split("\t")
    if header != expected_columns:
        raise ValueError(
            f"{path.name}: header drifted from the verified layout; "
            f"got {header[:5]}... — refusing to guess column positions"
        )
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        if not line:
            continue
        fields = line.split("\t")
        if len(fields) != len(expected_columns):
            raise ValueError(
                f"{path.name}: row with {len(fields)} fields "
                f"(expected {len(expected_columns)}): {line[:80]!r}"
            )
        rows.append(dict(zip(expected_columns, fields)))
    return rows


def _iso_date(yyyymmdd: str) -> str | None:
    value = yyyymmdd.strip()
    if not value:
        return None
    if len(value) != 8 or not value.isdigit():
        return None
    return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"


def _parse_application(raw: str) -> tuple[str | None, str | None]:
    """'ANDA211293' → ('A', '211293'); non-application values → (None, None)."""
    value = raw.strip()
    if value.startswith("ANDA") and value[4:].isdigit() and len(value) == 10:
        return "A", value[4:]
    if value.startswith("NDA") and value[3:].isdigit() and len(value) == 9:
        return "N", value[3:]
    return None, None


def _ingredient_set(substance: str) -> tuple[str | None, int]:
    parts = [p.strip().upper() for p in substance.split(";") if p.strip()]
    if not parts:
        return None, 0
    return "|".join(sorted(parts)), len(parts)


def ingest(
    conn: sqlite3.Connection, run_id: int, product_path: Path, package_path: Path
) -> int:
    """Ingest both files; returns total rows written."""
    count = 0
    for row in _read_rows(product_path, _PRODUCT_COLUMNS):
        try:
            ndc9 = product_ndc_to_ndc9(row["PRODUCTNDC"])
        except NdcError:
            continue  # 6-digit labelers etc. — none exist today
        ingredient_set, ingredient_count = _ingredient_set(row["SUBSTANCENAME"])
        numerator = row["ACTIVE_NUMERATOR_STRENGTH"].strip()
        unit = row["ACTIVE_INGRED_UNIT"].strip()
        if ingredient_count == 1 and numerator and unit:
            strength_norm: str | None = normalize_ndc_strength(numerator, unit)
        else:
            strength_norm = None

        appl_type, appl_no_raw = _parse_application(row["APPLICATIONNUMBER"])
        appl_no, _corrected = special_case_value(
            conn, "product", ndc9, "appl_no", appl_no_raw
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO product (
              ndc9, product_ndc_filed, product_type, proprietary_name,
              proprietary_suffix, nonproprietary_name, dosage_form_raw,
              route_raw, marketing_category, appl_type, appl_no, appl_no_raw,
              labeler_name, substance_raw, ingredient_set, ingredient_count,
              strength_numerator, strength_unit, strength_norm, form_family,
              dea_schedule, start_marketing, end_marketing, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ndc9,
                row["PRODUCTNDC"].strip(),
                row["PRODUCTTYPENAME"].strip() or None,
                row["PROPRIETARYNAME"].strip() or None,
                row["PROPRIETARYNAMESUFFIX"].strip() or None,
                row["NONPROPRIETARYNAME"].strip() or None,
                row["DOSAGEFORMNAME"].strip() or None,
                row["ROUTENAME"].strip() or None,
                row["MARKETINGCATEGORYNAME"].strip() or None,
                appl_type,
                appl_no,
                appl_no_raw,
                row["LABELERNAME"].strip() or None,
                row["SUBSTANCENAME"].strip() or None,
                ingredient_set,
                ingredient_count,
                numerator or None,
                unit or None,
                strength_norm,
                form_family(row["DOSAGEFORMNAME"], row["ROUTENAME"]),
                row["DEASCHEDULE"].strip() or None,
                _iso_date(row["STARTMARKETINGDATE"]),
                _iso_date(row["ENDMARKETINGDATE"]),
                run_id,
            ),
        )
        count += 1

    for row in _read_rows(package_path, _PACKAGE_COLUMNS):
        code = row["NDCPACKAGECODE"].strip()
        try:
            query = parse_ndc(code)
            ndc11 = query.ndc11
            ndc9 = product_ndc_to_ndc9(row["PRODUCTNDC"])
        except NdcError:
            continue
        info = parse_package_description(row["PACKAGEDESCRIPTION"])
        conn.execute(
            """
            INSERT OR REPLACE INTO package (
              ndc11, ndc9, package_ndc_filed, ndc_shape, package_descr_raw,
              pack_count, pack_unit, wear_hours, sample_package,
              start_marketing, end_marketing, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ndc11,
                ndc9,
                code,
                query.shape,
                row["PACKAGEDESCRIPTION"].strip() or None,
                info.pack_count,
                info.pack_unit,
                info.wear_hours,
                1 if row["SAMPLE_PACKAGE"].strip().upper() == "Y" else 0,
                _iso_date(row["STARTMARKETINGDATE"]),
                _iso_date(row["ENDMARKETINGDATE"]),
                run_id,
            ),
        )
        count += 1
    return count
