"""Vercel Python serverless entry.

Vercel routes /api/* here (see vercel.json). The ASGI app receives the
ORIGINAL request path, so the FastAPI routes in ndcres.web.app match
unchanged. The database is a read-only build-time artifact fetched into
data/web.db by scripts/fetch-db.mjs during `next build`.

If the bundle is broken (missing package, missing database), the import
failure is surfaced as a JSON 500 carrying the traceback instead of an
opaque platform error page — a broken deploy must say WHY.
"""

import json
import os
import sys
import traceback
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
os.environ.setdefault("NDCRES_DB", str(_ROOT / "data" / "web.db"))

try:
    from ndcres.web.app import app  # noqa: F401
except Exception:  # pragma: no cover - deploy-diagnostics path
    _error = traceback.format_exc()
    _listing = {
        str(p): sorted(x.name for x in p.iterdir())[:20] if p.is_dir() else "missing"
        for p in (_ROOT, _ROOT / "src", _ROOT / "data")
    }

    async def app(scope, receive, send):  # type: ignore[misc,no-redef]
        if scope["type"] != "http":
            return
        body = json.dumps(
            {
                "error": "ndcres failed to load inside the serverless bundle",
                "traceback": _error,
                "bundle": _listing,
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
