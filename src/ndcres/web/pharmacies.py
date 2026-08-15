"""Pharmacy locator via the NPI Registry (SPEC §14, §17).

CMS's NPI Registry API is credential-free public data (FOIA-mandated
disclosure, 72 FR 30011) with no redisplay prohibition — the ONLY
pharmacy directory this project will touch (chain sites are ToS/CFAA
walls, §17). An NPI record is a REGISTRATION, never a stock claim; the
payload says so.

PRIVACY (§17): the ZIP the visitor types is used for the single
upstream query and never stored, logged, or joined to anything.

Transport is stdlib urllib (no runtime dependency; the API layer calls
through FastAPI's threadpool). The fetcher is injectable so tests
exercise every branch with zero network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Protocol

NPI_API = "https://npiregistry.cms.hhs.gov/api/"
_TIMEOUT_SECONDS = 5.0

# NUCC taxonomy codes for NPI-2 pharmacy organizations.
_TAXONOMY_KINDS = {
    "3336C0003X": "retail",
    "3336M0002X": "mail-order",
    "3336S0011X": "specialty",
}


class UpstreamError(RuntimeError):
    """The registry could not be reached or answered unusably."""


class Fetcher(Protocol):
    def __call__(self, url: str) -> dict[str, Any]: ...


def _default_fetcher(url: str) -> dict[str, Any]:
    from ..ingest.fetch import _ssl_context  # OS-native verify (§ ingest)

    request = urllib.request.Request(
        url, headers={"accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 — fixed https host
            request, timeout=_TIMEOUT_SECONDS, context=_ssl_context()
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as error:
        raise UpstreamError(f"NPI registry unreachable: {error}") from error
    if not isinstance(payload, dict):
        raise UpstreamError("NPI registry returned a non-object payload")
    return payload


def _query_url(postal_code: str) -> str:
    params = urllib.parse.urlencode(
        {
            "version": "2.1",
            "enumeration_type": "NPI-2",
            "taxonomy_description": "pharmacy",
            "postal_code": postal_code,
            "limit": "200",
        }
    )
    return f"{NPI_API}?{params}"


def _kind(result: dict[str, Any]) -> str:
    for taxonomy in result.get("taxonomies") or []:
        label = _TAXONOMY_KINDS.get(taxonomy.get("code", ""))
        if label:
            return label
    return "pharmacy"


def _location_address(result: dict[str, Any]) -> dict[str, Any] | None:
    # LOCATION only: MAILING addresses route to corporate offices.
    addresses: list[dict[str, Any]] = list(result.get("addresses") or [])
    for address in addresses:
        if address.get("address_purpose") == "LOCATION":
            return address
    return None


def _entry(result: dict[str, Any]) -> dict[str, Any] | None:
    address = _location_address(result)
    if address is None:
        return None
    basic = result.get("basic") or {}
    name = basic.get("organization_name") or basic.get("name")
    if not name:
        return None
    lines = [address.get("address_1"), address.get("address_2")]
    return {
        "name": name,
        "kind": _kind(result),
        "address": ", ".join(part for part in lines if part),
        "city": address.get("city"),
        "state": address.get("state"),
        "zip": (address.get("postal_code") or "")[:5],
        "phone": address.get("telephone_number"),
    }


_KIND_ORDER = {"retail": 0, "pharmacy": 1, "specialty": 2, "mail-order": 3}


def find_pharmacies(
    zip5: str, fetch: Fetcher | None = None
) -> dict[str, Any]:
    """One upstream query (+ one ZIP-prefix widen on zero results)."""
    fetcher: Callable[[str], dict[str, Any]] = fetch or _default_fetcher
    widened = False
    payload = fetcher(_query_url(zip5))
    results = payload.get("results") or []
    if not results:
        widened = True
        payload = fetcher(_query_url(f"{zip5[:3]}*"))
        results = payload.get("results") or []
    entries = [e for e in (_entry(r) for r in results) if e is not None]
    entries.sort(
        key=lambda e: (_KIND_ORDER.get(e["kind"], 1), e["name"] or "")
    )
    return {
        "zip": zip5,
        "widened": widened,
        "pharmacies": entries,
        "attribution": (
            "CMS National Plan and Provider Enumeration System (NPPES) "
            "NPI Registry - public data, FOIA-mandated disclosure "
            "(72 FR 30011)."
        ),
        "note": (
            "An NPI record is a provider REGISTRATION, not a statement "
            "that the pharmacy is open or has any product in stock. "
            "Call first - the note and call script exist for exactly "
            "that conversation."
        ),
        "disclaimer": (
            "Not medical advice. Reference information from public "
            "federal data."
        ),
    }
