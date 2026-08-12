"""RxNorm ingest — three stream filters over the Current Prescribable
Content RRF files (the credential-free release; the full monthly release
is UTS-license-gated and deliberately unsupported).

We are not building a UMLS toolkit. Exactly three line filters:

- RXNCONSO.RRF: SAB=RXNORM atoms of the TTYs we traverse.
- RXNREL.RRF:   SAB=RXNORM rows whose RELA is one of the traversal
  relations. Direction conventions differ between UMLS docs — rows are
  stored verbatim (rxcui1, rela, rxcui2) and queried in both directions.
- RXNSAT.RRF:   ATN=NDC attribute rows. ATV is already the bare 11-digit
  zero-padded form (the same normalization NADAC uses natively).

RxNorm is the clinical-identity layer only — its concepts deliberately
span TE subgroups (Dotti and Lyllana share an SCD), so nothing here may
ever be read as legal substitutability. That comes from the Orange Book.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_KEEP_TTYS = {"SCD", "SBD", "GPCK", "BPCK", "IN", "PIN", "BN"}
_KEEP_RELAS = {
    "tradename_of",
    "has_tradename",
    "has_ingredient",
    "ingredient_of",
    "contains",
    "contained_in",
}

# RRF column positions (pipe-delimited, trailing pipe).
_CONSO_RXCUI, _CONSO_SAB, _CONSO_TTY, _CONSO_STR, _CONSO_SUPPRESS = 0, 11, 12, 14, 16
_REL_RXCUI1, _REL_RXCUI2, _REL_RELA, _REL_SAB = 0, 4, 7, 10
_SAT_RXCUI, _SAT_ATN, _SAT_SAB, _SAT_ATV = 0, 8, 9, 10


def ingest(
    conn: sqlite3.Connection,
    run_id: int,
    conso_path: Path,
    rel_path: Path,
    sat_path: Path,
) -> int:
    count = 0

    with conso_path.open(encoding="utf-8") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) <= _CONSO_SUPPRESS:
                continue
            if fields[_CONSO_SAB] != "RXNORM" or fields[_CONSO_TTY] not in _KEEP_TTYS:
                continue
            if fields[_CONSO_SUPPRESS] in {"Y", "O", "E"}:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO rx_concept (rxcui, tty, name, run_id) "
                "VALUES (?, ?, ?, ?)",
                (fields[_CONSO_RXCUI], fields[_CONSO_TTY], fields[_CONSO_STR], run_id),
            )
            count += 1

    with rel_path.open(encoding="utf-8") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) <= _REL_SAB:
                continue
            if fields[_REL_SAB] != "RXNORM" or fields[_REL_RELA] not in _KEEP_RELAS:
                continue
            conn.execute(
                "INSERT OR REPLACE INTO rx_rel (rxcui1, rela, rxcui2, run_id) "
                "VALUES (?, ?, ?, ?)",
                (fields[_REL_RXCUI1], fields[_REL_RELA], fields[_REL_RXCUI2], run_id),
            )
            count += 1

    with sat_path.open(encoding="utf-8") as handle:
        for line in handle:
            fields = line.rstrip("\n").split("|")
            if len(fields) <= _SAT_ATV:
                continue
            if fields[_SAT_ATN] != "NDC":
                continue
            ndc11 = fields[_SAT_ATV].strip()
            if len(ndc11) != 11 or not ndc11.isdigit():
                continue
            conn.execute(
                "INSERT OR REPLACE INTO rx_ndc (ndc11, rxcui, run_id) VALUES (?, ?, ?)",
                (ndc11, fields[_SAT_RXCUI], run_id),
            )
            count += 1
    return count
