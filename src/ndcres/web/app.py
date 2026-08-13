"""FastAPI application.

    GET /api/resolve/{ndc}        ranked, tiered alternatives
    GET /api/explain/{a}/{b}      dimension-by-dimension rationale
    GET /api/signal/{ndc}         supply-stress components + score
    GET /api/search?q=...         product search by name / NDC prefix
    GET /api/meta                 data vintages + disclaimer

Read-only by design: the database is a build-time artifact on serverless
hosts. The connection is opened per request (SQLite read concurrency is
fine at this scale) against NDCRES_DB.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Iterator

from fastapi import Depends, FastAPI, HTTPException, Query

from ..db import connect, default_db_path
from ..explain import explain as run_explain
from ..ndc import NdcError
from ..resolve import ResolveError, resolve as run_resolve, resolve_input_ndc11
from ..serialize import (
    DISCLAIMER,
    explanation_dict,
    resolution_dict,
    signal_dict,
)
from ..signals import signal_report

app = FastAPI(
    title="NDC Equivalence Resolver",
    description=(
        "Therapeutic-equivalence and supply-stress lookup over public "
        "FDA/NLM/CMS data. " + DISCLAIMER
    ),
    version="0.1.0",
)


def get_conn() -> Iterator[sqlite3.Connection]:
    conn = connect(default_db_path())
    try:
        yield conn
    finally:
        conn.close()


@app.get("/api/resolve/{ndc}")
def api_resolve(
    ndc: str, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, Any]:
    try:
        return resolution_dict(run_resolve(conn, ndc))
    except (NdcError, ResolveError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/explain/{ndc_a}/{ndc_b}")
def api_explain(
    ndc_a: str, ndc_b: str, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, Any]:
    try:
        return explanation_dict(run_explain(conn, ndc_a, ndc_b))
    except (NdcError, ResolveError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/signal/{ndc}")
def api_signal(
    ndc: str, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, Any]:
    try:
        ndc11 = resolve_input_ndc11(conn, ndc)
    except (NdcError, ResolveError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return signal_dict(signal_report(conn, ndc11))


@app.get("/api/search")
def api_search(
    q: str = Query(min_length=2, max_length=80),
    limit: int = Query(default=25, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    needle = f"%{q.strip()}%"
    rows = conn.execute(
        """
        SELECT p.ndc9, p.proprietary_name, p.proprietary_suffix,
               p.nonproprietary_name, p.labeler_name, p.dosage_form_raw,
               p.strength_numerator, p.strength_unit,
               k.ndc11, k.package_ndc_filed, k.pack_count
        FROM product p JOIN package k USING (ndc9)
        WHERE p.proprietary_name LIKE ? COLLATE NOCASE
           OR p.nonproprietary_name LIKE ? COLLATE NOCASE
           OR k.package_ndc_filed LIKE ?
           OR k.ndc11 LIKE ?
        ORDER BY p.proprietary_name, k.ndc11
        LIMIT ?
        """,
        (needle, needle, needle, needle, limit),
    ).fetchall()
    return {
        "query": q,
        "results": [
            {
                "ndc11": row["ndc11"],
                "ndc_as_filed": row["package_ndc_filed"],
                "name": row["proprietary_name"],
                "name_suffix": row["proprietary_suffix"],
                "generic_name": row["nonproprietary_name"],
                "labeler": row["labeler_name"],
                "dosage_form": row["dosage_form_raw"],
                "strength": (
                    f"{row['strength_numerator']} {row['strength_unit']}"
                    if row["strength_numerator"]
                    else None
                ),
                "pack_count": row["pack_count"],
            }
            for row in rows
        ],
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/meta")
def api_meta(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    rows = conn.execute(
        """
        SELECT source, max(fetched_at) AS fetched_at, dataset_vintage,
               row_count
        FROM source_run WHERE status = 'ok' GROUP BY source
        """
    ).fetchall()
    return {
        "sources": [
            {
                "source": row["source"],
                "fetched_at": row["fetched_at"],
                "vintage": row["dataset_vintage"],
                "rows": row["row_count"],
            }
            for row in rows
        ],
        "disclaimer": DISCLAIMER,
    }
