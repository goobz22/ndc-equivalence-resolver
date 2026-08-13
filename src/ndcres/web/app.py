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

import os
import sqlite3
from typing import Any, Iterator

from fastapi import Depends, FastAPI, HTTPException, Query

from ..db import connect_readonly, default_db_path
from ..explain import explain as run_explain
from ..ndc import NdcError
from ..provenance import source_refs
from ..resolve import ResolveError, resolve as run_resolve, resolve_input_ndc11
from ..search import search as run_search
from ..serialize import (
    DISCLAIMER,
    explanation_dict,
    resolution_dict,
    search_results_dict,
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
    # NDCRES_IMMUTABLE=1 (set by the serverless entrypoint) skips SQLite
    # locking entirely — safe there because the bundle is read-only. Local
    # dev serves a database a refresh may write in place, so it stays off.
    try:
        conn = connect_readonly(
            default_db_path(),
            immutable=os.environ.get("NDCRES_IMMUTABLE") == "1",
        )
    except FileNotFoundError as error:
        # A missing database is a broken deploy — say so instead of a
        # bare 500.
        raise HTTPException(status_code=500, detail=str(error)) from error
    try:
        yield conn
    finally:
        conn.close()


@app.get("/api/resolve/{ndc}")
def api_resolve(
    ndc: str, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, Any]:
    try:
        return resolution_dict(run_resolve(conn, ndc), sources=source_refs(conn))
    except (NdcError, ResolveError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/explain/{ndc_a}/{ndc_b}")
def api_explain(
    ndc_a: str, ndc_b: str, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, Any]:
    try:
        return explanation_dict(
            run_explain(conn, ndc_a, ndc_b), sources=source_refs(conn)
        )
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
    return signal_dict(signal_report(conn, ndc11), sources=source_refs(conn))


@app.get("/api/search")
def api_search(
    q: str = Query(min_length=2, max_length=80),
    limit: int = Query(default=25, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    return search_results_dict(
        q, run_search(conn, q, limit=limit), sources=source_refs(conn)
    )


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
        # Full identity + latest-run state per source — the /sources page
        # and per-block SourceTags render from this (SPEC §9).
        "registry": source_refs(conn),
        "disclaimer": DISCLAIMER,
    }
