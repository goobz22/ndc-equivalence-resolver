"""Vercel Python serverless entry — standalone ndcres-api project.

This directory (apiserver/) deploys as its OWN Vercel project, separate
from the Next.js UI. The mixed Next+Python layout is unbuildable on
current Vercel (docs/DEPLOY_NOTES.md), and the Next preset cannot be
kept from claiming a repo whose root package.json contains "next" — so
the API ships from a directory containing no package.json at all, with
an explicit legacy `builds` config that creates exactly this function.

sync-assets.mjs copies the ndcres package and the web.db artifact next
to this file before deploy; the UI project proxies /api/* here via
NDCRES_API_PROXY (next.config.ts rewrite). The ASGI app receives the
ORIGINAL request path, so the FastAPI routes match unchanged.

If the bundle is broken (missing package, missing database), the import
failure is surfaced as a JSON 500 carrying the traceback instead of an
opaque platform error page — a broken deploy must say WHY.
"""

import json
import os
import sys
import traceback
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_UPLOAD_ROOT = _HERE.parent  # apiserver/ locally, the lambda root on Vercel
_REPO = _UPLOAD_ROOT.parent  # only meaningful when running in the repo tree
for _candidate in (_HERE, _UPLOAD_ROOT, _REPO / "src"):
    sys.path.insert(0, str(_candidate))
for _db in (_HERE / "web.db", _UPLOAD_ROOT / "web.db", _REPO / "data" / "web.db"):
    if _db.exists():
        os.environ.setdefault("NDCRES_DB", str(_db))
        break

def _load_app():  # -> ASGI application
    # The Vercel Python builder statically scans the entry file for a
    # TOP-LEVEL binding named "app" — a name bound inside try/except is
    # invisible to it, so the import happens here and the module ends
    # with a plain top-level assignment.
    try:
        from ndcres.web.app import app as _real_app

        return _real_app
    except Exception:  # pragma: no cover - deploy-diagnostics path
        error = traceback.format_exc()
        listing = sorted(p.name for p in _UPLOAD_ROOT.iterdir())[:30]

        async def _diagnostic(scope, receive, send):  # type: ignore[no-untyped-def]
            if scope["type"] != "http":
                return
            body = json.dumps(
                {
                    "error": "ndcres failed to load inside the serverless bundle",
                    "traceback": error,
                    "bundle_dir": listing,
                },
                indent=2,
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send({"type": "http.response.body", "body": body})

        return _diagnostic


app = _load_app()
