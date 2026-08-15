"""Canonical class addresses (SPEC §14/§15): stable slugs, no storage.

Every TE-rated equivalence class gets a URL like

    /class/estradiol-system-transdermal-0-05-mg-24hr-ab1-1a2b3c4d

The slug is a PURE FUNCTION of the class key — a human-readable head
(first two ingredients, form;route, humanized strength, TE code,
lowercased, non-alphanumerics collapsed to '-', capped) plus an 8-hex
sha1 suffix of the full joined key. The suffix is what makes it a
reliable address: class keys contain characters slugification must
drop (`RAW:0.05%` vs `RAW:005`, parentheses, apostrophes), and two keys
that collide after cleaning still differ in the hash. Nothing is
stored; the slug index is computed over the latest sweep's ~2,900 rows
in milliseconds and cached per (database, sweep) — the serving database
is immutable per deploy, so the cache can never go stale there.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from typing import Any

_SLUG_CLEAN_RE = re.compile(r"[^a-z0-9]+")
_HUMAN_HEAD_CAP = 80

ClassKey = tuple[str, str, str, str]


def human_strength(strength_norm: str) -> str:
    """Human-first rendering of a canonical strength key.

    The single Python home of the labeling rules the gaps page uses;
    unparsed upstream strengths render verbatim, honestly labeled.
    """
    if strength_norm.startswith("UG24H:"):
        return f"{strength_norm[6:]} mcg/24hr"
    if strength_norm.startswith("UG:"):
        value = strength_norm[3:]
        try:
            micrograms = float(value)
        except ValueError:
            return f"{value} mcg"
        if micrograms >= 1000:
            milligrams = micrograms / 1000
            return f"{milligrams:g} mg"
        return f"{value} mcg"
    if strength_norm.startswith("PCT:"):
        return f"{strength_norm[4:].split(';')[0]}%"
    if strength_norm.startswith("RAW:"):
        return f"{strength_norm[4:]} (as filed)"
    return strength_norm or "?"


def class_slug(
    ingredient_set: str, df_route: str, strength_norm: str, te_code: str
) -> str:
    ingredients = ingredient_set.split("|")[:2]
    head_source = " ".join(
        [*ingredients, df_route, human_strength(strength_norm), te_code]
    ).lower()
    head = _SLUG_CLEAN_RE.sub("-", head_source).strip("-")[:_HUMAN_HEAD_CAP]
    head = head.rstrip("-")
    joined = "|".join((ingredient_set, df_route, strength_norm, te_code))
    suffix = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:8]
    return f"{head}-{suffix}"


# Cache key: (database path or id, sweep_id). The serving database is
# immutable per deploy; locally a new sweep gets a new sweep_id, which
# invalidates naturally.
_INDEX_CACHE: dict[tuple[str, int], dict[str, dict[str, Any]]] = {}


def _db_identity(conn: sqlite3.Connection) -> str:
    rows = conn.execute("PRAGMA database_list").fetchall()
    return rows[0]["file"] if rows and rows[0]["file"] else "memory"


def slug_index(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """slug -> latest-sweep class row (as a plain dict) for every class."""
    from .sweep import latest_sweep_id

    sweep_id = latest_sweep_id(conn)
    if sweep_id is None:
        return {}
    cache_key = (_db_identity(conn), sweep_id)
    cached = _INDEX_CACHE.get(cache_key)
    if cached is not None:
        return cached
    index: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        "SELECT * FROM sweep_class WHERE sweep_id = ?", (sweep_id,)
    ):
        slug = class_slug(
            row["ingredient_set"],
            row["df_route"],
            row["strength_norm"],
            row["te_code"],
        )
        index[slug] = {**dict(row), "slug": slug}
    _INDEX_CACHE.clear()  # never hold more than the current sweep's map
    _INDEX_CACHE[cache_key] = index
    return index
