"""Vercel Python serverless entry.

Vercel routes /api/* here (see vercel.json). The ASGI app receives the
ORIGINAL request path, so the FastAPI routes in ndcres.web.app match
unchanged. The database is a read-only build-time artifact fetched into
data/web.db by scripts/fetch-db.mjs during `next build`.
"""

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "src"))
os.environ.setdefault("NDCRES_DB", str(_ROOT / "data" / "web.db"))

from ndcres.web.app import app  # noqa: E402,F401
