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

from fastapi import Depends, FastAPI, HTTPException, Query, Response

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


@app.get("/api/classes")
def api_classes(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    from ..classpage import slug_index
    from ..sweep import latest_sweep_id

    sweep_id = latest_sweep_id(conn)
    if sweep_id is None:
        raise HTTPException(
            status_code=404,
            detail="no sweep in this database — class pages need one",
        )
    run = conn.execute(
        "SELECT run_date FROM sweep_run WHERE sweep_id = ?", (sweep_id,)
    ).fetchone()
    index = slug_index(conn)
    return {
        "sweep": {"sweep_id": sweep_id, "run_date": run["run_date"]},
        "count": len(index),
        "classes": [
            {
                "slug": entry["slug"],
                "ingredient_set": entry["ingredient_set"],
                "df_route": entry["df_route"],
                "strength_norm": entry["strength_norm"],
                "te_code": entry["te_code"],
                "rep_ndc11": entry["rep_ndc11"],
                "verdict": entry["verdict"],
            }
            for entry in index.values()
        ],
        "sources": source_refs(conn),
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/class/{slug}")
def api_class(
    slug: str, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, Any]:
    from ..classpage import slug_index

    entry = slug_index(conn).get(slug)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "no equivalence class with this address in the latest sweep "
                "— it may have left the market, or the link is stale"
            ),
        )
    return {
        "slug": slug,
        "class": {
            key: value
            for key, value in entry.items()
            if key not in ("slug", "sweep_id")
        },
        "resolution": resolution_dict(
            run_resolve(conn, entry["rep_ndc11"]), sources=source_refs(conn)
        ),
        "sources": source_refs(conn),
        "disclaimer": DISCLAIMER,
    }


@app.get("/api/gaps")
def api_gaps(
    limit: int = Query(default=100, ge=1, le=500),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    from ..gaps import GapError, gap_report
    from ..serialize import gap_report_dict

    try:
        report = gap_report(conn)
    except GapError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return gap_report_dict(report, sources=source_refs(conn), limit=limit)


@app.get("/api/dossier/{ndc}")
def api_dossier(
    ndc: str, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, Any]:
    from ..dossier import build_dossier, dossier_dict

    try:
        return dossier_dict(build_dossier(conn, ndc))
    except (NdcError, ResolveError) as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/api/feeds/gaps.xml")
def api_feed_gaps(conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    from ..feeds import gaps_transitions, render_rss

    body = render_rss(
        title="NDC Equivalence Resolver - gap-report changes",
        link="https://ndc-equivalence-resolver.vercel.app/gaps",
        description=(
            "Equivalence classes entering or leaving the "
            "unlisted-constraint set (or the FDA shortage list) between "
            "weekly sweeps. Probabilistic evidence from public data."
        ),
        items=gaps_transitions(conn),
    )
    return Response(
        content=body,
        media_type="application/rss+xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/feeds/class/{slug}.xml")
def api_feed_class(
    slug: str, conn: sqlite3.Connection = Depends(get_conn)
) -> Response:
    from ..feeds import class_history_items, render_rss

    items = class_history_items(conn, slug)
    if items is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown class slug {slug!r} - see /api/classes",
        )
    body = render_rss(
        title=f"NDC Equivalence Resolver - class watch: {slug}",
        link=f"https://ndc-equivalence-resolver.vercel.app/class/{slug}",
        description=(
            "Weekly verdict history for one equivalence class. "
            "Probabilistic evidence from public data - never a statement "
            "of availability."
        ),
        items=items,
    )
    return Response(
        content=body,
        media_type="application/rss+xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/api/statelaw")
def api_statelaw() -> dict[str, Any]:
    # Curated public-law reference (SPEC §20) — no DB dependency.
    from ..statelaw import statelaw_payload

    return statelaw_payload()


@app.get("/api/pharmacies")
async def api_pharmacies(
    zip: str = Query(pattern=r"^\d{5}$"),
) -> Any:
    from fastapi.concurrency import run_in_threadpool
    from fastapi.responses import JSONResponse

    from .pharmacies import UpstreamError, find_pharmacies

    try:
        payload = await run_in_threadpool(find_pharmacies, zip)
    except UpstreamError as error:
        return JSONResponse(
            status_code=503,
            content={"detail": str(error)},
            headers={"Retry-After": "60"},
        )
    return JSONResponse(
        content=payload,
        # The 24h CDN cache IS the rate-limit posture: one upstream
        # query (+1 widen) per ZIP per day, not per visitor.
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.get("/api/costplus/{ndc}")
async def api_costplus(ndc: str) -> Any:
    from fastapi.concurrency import run_in_threadpool
    from fastapi.responses import JSONResponse

    from ..ndc import parse_ndc
    from .costplus import CostplusError, costplus_enabled, price_for_ndc

    if not costplus_enabled():
        raise HTTPException(
            status_code=404,
            detail=(
                "Cost Plus lookup is not enabled on this deployment "
                "(operator-gated; see SPEC section 14)"
            ),
        )
    try:
        ndc11 = parse_ndc(ndc).ndc11  # ambiguous bare-10 raises NdcError
    except NdcError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    try:
        payload = await run_in_threadpool(price_for_ndc, ndc11)
    except CostplusError as error:
        return JSONResponse(
            status_code=503,
            content={"detail": str(error)},
            headers={"Retry-After": "60"},
        )
    return JSONResponse(
        content=payload, headers={"Cache-Control": "public, max-age=86400"}
    )


@app.get("/api/meta")
def api_meta(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    from .costplus import costplus_enabled

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
        # Truthful feature flags (T11 discipline: never advertise what
        # is off; never silently ship what is undeclared).
        "features": {
            "pharmacy_locator": True,
            "costplus": costplus_enabled(),
        },
        "disclaimer": DISCLAIMER,
    }
