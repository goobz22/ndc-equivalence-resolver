"""Cost Plus Drugs price lookup — OPERATOR-GATED, default OFF (SPEC §14).

Mark Cuban Cost Plus Drugs exposes a documented public price API keyed
by NDC. Their site ToS is unreadable to automated fetchers, so this
module ships DISABLED: the operator reads the ToS in a real browser,
live-checks the endpoint, and only then sets NDCRES_COSTPLUS=1 on the
deployment. Until then the endpoint answers 404 "not enabled" and
/api/meta reports the feature truthfully off. Never enabled by an
agent's inference — the enablement is a human decision (§17).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

# The documented public price endpoint (no auth, NDC-keyed). The
# operator's enablement checklist live-checks this before setting the
# flag, so shape drift is caught by a human before anything serves.
COSTPLUS_API = (
    "https://us-central1-costplusdrugs-publicapi.cloudfunctions.net/main"
)
_TIMEOUT_SECONDS = 5.0


def costplus_enabled() -> bool:
    return os.environ.get("NDCRES_COSTPLUS") == "1"


class CostplusError(RuntimeError):
    """Upstream unreachable or answered unusably."""


def _default_fetcher(url: str) -> Any:
    from ..ingest.fetch import _ssl_context  # OS-native verify (§ ingest)

    request = urllib.request.Request(
        url, headers={"accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 — fixed https host
            request, timeout=_TIMEOUT_SECONDS, context=_ssl_context()
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise CostplusError(f"Cost Plus unreachable: {error}") from error


def price_for_ndc(
    ndc11: str, fetch: Callable[[str], Any] | None = None
) -> dict[str, Any]:
    fetcher = fetch or _default_fetcher
    query = urllib.parse.urlencode({"ndc": ndc11})
    payload = fetcher(f"{COSTPLUS_API}?{query}")
    results = (
        payload.get("results") if isinstance(payload, dict) else payload
    ) or []
    matches = [
        {
            "medication": row.get("medication_name"),
            "quantity": row.get("quantity"),
            "unit_price": row.get("unit_price"),
            "requires_membership": row.get("requires_membership"),
            "url": row.get("url"),
        }
        for row in results
        if isinstance(row, dict)
    ]
    return {
        "ndc11": ndc11,
        "matches": matches,
        "attribution": (
            "Mark Cuban Cost Plus Drug Company public price API. "
            "Prices change; the pharmacy's own site controls."
        ),
        "disclaimer": (
            "Not medical advice. A price listing is not a stock claim."
        ),
    }
