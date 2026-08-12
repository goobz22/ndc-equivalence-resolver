"""FDA Orange Book ingest (products.txt from the EOBZIP).

Verified format facts (July 2026 edition):

- ``~``-delimited, 14 columns, ASCII, CRLF (last line unterminated).
- ``Appl_No`` zero-padded 6 chars; ``Product_No`` 3 chars — NOT ordered
  by strength.
- ``Type`` ∈ RX / DISCN / OTC; discontinued rows live in the same file,
  mostly with blank TE codes.
- 2,408 rows append a ``**Federal Register determination ...**`` suffix
  inside the Strength field.
- ``Approval_Date`` is 'Mon D, YYYY' or the literal
  'Approved Prior to Jan 1, 1982'.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from ..strength import normalize_ob_strength, strip_fr_suffix
from ..tecode import parse_te_code

_COLUMNS = [
    "Ingredient",
    "DF;Route",
    "Trade_Name",
    "Applicant",
    "Strength",
    "Appl_Type",
    "Appl_No",
    "Product_No",
    "TE_Code",
    "Approval_Date",
    "RLD",
    "RS",
    "Type",
    "Applicant_Full_Name",
]

_PRE_1982 = "Approved Prior to Jan 1, 1982"


def _approval_date(raw: str) -> str | None:
    value = raw.strip()
    if not value:
        return None
    if value == _PRE_1982:
        return "pre-1982"
    try:
        return datetime.strptime(value, "%b %d, %Y").date().isoformat()
    except ValueError:
        return value  # preserve unknown spellings verbatim rather than drop


def _ingredient_set(ingredient: str) -> str:
    parts = [p.strip().upper() for p in ingredient.split(";") if p.strip()]
    return "|".join(sorted(parts))


def ingest(conn: sqlite3.Connection, run_id: int, products_path: Path) -> int:
    text = products_path.read_text(encoding="cp1252")
    lines = [line for line in text.replace("\r\n", "\n").split("\n") if line]
    header = lines[0].split("~")
    if header != _COLUMNS:
        raise ValueError(
            f"{products_path.name}: header drifted from the verified layout; "
            "refusing to guess column positions"
        )

    count = 0
    for line in lines[1:]:
        fields = line.split("~")
        if len(fields) != len(_COLUMNS):
            raise ValueError(
                f"{products_path.name}: row with {len(fields)} fields: {line[:80]!r}"
            )
        row = dict(zip(_COLUMNS, fields))
        te = parse_te_code(row["TE_Code"])
        conn.execute(
            """
            INSERT OR REPLACE INTO ob_product (
              appl_type, appl_no, product_no, ingredient_raw, ingredient_set,
              df_route, trade_name, applicant, applicant_full, strength_raw,
              strength_norm, te_code, te_class, te_subscript, rld, rs,
              ob_type, approval_date, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["Appl_Type"].strip(),
                row["Appl_No"].strip(),
                row["Product_No"].strip(),
                row["Ingredient"].strip(),
                _ingredient_set(row["Ingredient"]),
                row["DF;Route"].strip(),
                row["Trade_Name"].strip() or None,
                row["Applicant"].strip() or None,
                row["Applicant_Full_Name"].strip() or None,
                strip_fr_suffix(row["Strength"]) or None,
                normalize_ob_strength(row["Strength"]) if row["Strength"].strip() else None,
                te.full if te else None,
                te.letter_class if te else None,
                te.subscript if te else None,
                1 if row["RLD"].strip() == "Yes" else 0,
                1 if row["RS"].strip() == "Yes" else 0,
                row["Type"].strip(),
                _approval_date(row["Approval_Date"]),
                run_id,
            ),
        )
        count += 1
    return count
