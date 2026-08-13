"""Vercel Python serverless entry.

Vercel routes /api/* here (vercel.json rewrites). The ASGI app receives
the ORIGINAL request path, so the FastAPI routes in ndcres.web.app match
unchanged. scripts/prepare-api.mjs makes this directory self-contained
at build time: the ndcres package and the read-only web.db artifact are
copied in (Vercel's Python builder bundles exactly this directory).

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
_ROOT = _HERE.parent
# Two possible bundle layouts, depending on how the platform packaged us:
# self-contained api/ (prepare-api.mjs) or includeFiles-relative paths.
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_ROOT / "src"))
_db = _HERE / "web.db"
if not _db.exists():
    _db = _ROOT / "data" / "web.db"
os.environ.setdefault("NDCRES_DB", str(_db))

try:
    from ndcres.web.app import app  # noqa: F401
except Exception:  # pragma: no cover - deploy-diagnostics path
    _error = traceback.format_exc()
    _listing = sorted(p.name for p in _HERE.iterdir())[:30]

    async def app(scope, receive, send):  # type: ignore[misc,no-redef]
        if scope["type"] != "http":
            return
        body = json.dumps(
            {
                "error": "ndcres failed to load inside the serverless bundle",
                "traceback": _error,
                "bundle_dir": _listing,
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
