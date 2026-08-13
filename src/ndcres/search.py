"""Structured drug search (SPEC §8).

The old search was a single whole-string LIKE, so "estradiol .05" — an
ingredient plus a strength — matched nothing. Here the query is parsed
into CLASSIFIED tokens that AND together across their field classes:

  - NDC-ish tokens (digits/hyphens) match ndc9/ndc11 prefixes, using the
    real segmentation rules from ndc.py (hyphenated forms normalize; a
    bare 8-digit string also tries the 4-4 filed shape's padding).
  - strength-ish tokens (".05", "0.05 mg", "50 mcg", "0.06%") generate
    canonical-key candidates AT QUERY TIME via the same decimal
    canonicalization the ingest pipeline uses (strength.py), and match
    product.strength_norm exactly — aliases live in the parser, never in
    the database.
  - form words ("patch", "gel", "tablet") filter on the curated
    form_family (formfamily.py) with a raw dosage-form fallback.
  - everything else is a name term matched against proprietary name +
    suffix, generic name, ingredient set, labeler, and the best RxNorm
    concept name.

Token order never matters ("estradiol .05" == ".05 estradiol"). Results
are PRODUCT-grain (one card per ndc9 with a representative package),
ranked deterministically: text-match quality, then marketed before
discontinued, then NADAC-surveyed (mainstream) products, then name/ndc9.

The search_doc side table carries the per-product derived bits (best
RxNorm name, TE code, marketed flag, NADAC presence, representative
package, package count). It is rebuilt after every refresh — a derived
mirror, like product_ob_link — and ships in the web export.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .ndc import NdcError, parse_ndc, product_ndc_to_ndc9
from .strength import _fmt

_FETCH_CAP = 500

# Query words that mean a form family. The family values are the ones
# formfamily.form_family emits — keep this map in sync with that module.
_FORM_WORDS = {
    "patch": "patch",
    "patches": "patch",
    "gel": "gel",
    "gels": "gel",
    "spray": "spray",
    "sprays": "spray",
    "tablet": "oral-solid",
    "tablets": "oral-solid",
    "tab": "oral-solid",
    "tabs": "oral-solid",
    "capsule": "oral-solid",
    "capsules": "oral-solid",
    "pill": "oral-solid",
    "pills": "oral-solid",
    "cream": "cream",
    "ointment": "cream",
    "lotion": "cream",
    "injection": "injection",
    "injectable": "injection",
    "ring": "vaginal",
    "insert": "vaginal",
}

_NUMBER_RE = re.compile(r"^(\d+\.?\d*|\.\d+)$")
_NUMBER_UNIT_RE = re.compile(
    r"^(\d+\.?\d*|\.\d+)\s*(mg|mcg|ug|µg|%)(?:/(?:day|d|24hr|24h|hr))?$",
    re.IGNORECASE,
)
_UNIT_WORDS = {"mg", "mcg", "ug", "µg", "%", "percent"}
_NDC_CHARS_RE = re.compile(r"^\d[\d-]*$")


@dataclass(frozen=True)
class SearchHit:
    ndc9: str
    rep_ndc11: str | None
    ndc_as_filed: str
    name: str | None
    name_suffix: str | None
    generic_name: str | None
    labeler: str | None
    dosage_form: str | None
    form_family: str | None
    strength: str | None
    te_code: str | None
    marketed: bool
    package_count: int


@dataclass(frozen=True)
class _Token:
    kind: str  # 'name' | 'form' | 'strength' | 'ndc' | 'ndc-or-strength'
    text: str
    number: str | None = None
    unit: str | None = None


def _tokenize(query: str) -> list[_Token]:
    words = query.strip().split()
    tokens: list[_Token] = []
    index = 0
    while index < len(words):
        word = words[index].strip().strip(",")
        nxt = words[index + 1].strip().strip(",").lower() if index + 1 < len(words) else None
        lowered = word.lower()
        if not word:
            index += 1
            continue
        # number followed by a unit word: "0.05 mg" is ONE strength token
        if _NUMBER_RE.match(word) and nxt in _UNIT_WORDS:
            tokens.append(_Token("strength", f"{word} {nxt}", number=word, unit=nxt))
            index += 2
            continue
        glued = _NUMBER_UNIT_RE.match(word)
        if glued:
            tokens.append(
                _Token("strength", word, number=glued.group(1), unit=glued.group(2))
            )
            index += 1
            continue
        if lowered in _FORM_WORDS:
            tokens.append(_Token("form", lowered))
            index += 1
            continue
        if _NDC_CHARS_RE.match(word):
            digits = word.replace("-", "")
            if "-" in word or len(digits) >= 8:
                tokens.append(_Token("ndc", word))
            elif len(digits) >= 4:
                # "4642" could be an NDC fragment OR a strength (1000 mg);
                # the token matches if EITHER interpretation does.
                tokens.append(_Token("ndc-or-strength", word, number=word, unit=None))
            else:
                tokens.append(_Token("strength", word, number=word, unit=None))
            index += 1
            continue
        if _NUMBER_RE.match(word):
            tokens.append(_Token("strength", word, number=word, unit=None))
            index += 1
            continue
        tokens.append(_Token("name", word))
        index += 1
    return tokens


def _strength_keys(number: str, unit: str | None) -> tuple[set[str], set[str]]:
    """(exact strength_norm keys, PCT prefixes) a query token can mean."""
    try:
        value = Decimal(number)
    except InvalidOperation:
        return set(), set()
    exact: set[str] = set()
    prefixes: set[str] = set()

    def add_micrograms(micrograms: Decimal) -> None:
        exact.add(f"UG24H:{_fmt(micrograms)}")
        exact.add(f"UG:{_fmt(micrograms)}")

    unit_norm = (unit or "").lower()
    if unit_norm == "mg":
        add_micrograms(value * 1000)
    elif unit_norm in {"mcg", "ug", "µg"}:
        add_micrograms(value)
    elif unit_norm in {"%", "percent"}:
        prefixes.add(f"PCT:{_fmt(value)};")
    else:
        # Bare number: the user did not say the unit, so both readings of
        # a patch-family number apply (".05" = 0.05 mg/day = 50 µg).
        add_micrograms(value * 1000)
        add_micrograms(value)
        prefixes.add(f"PCT:{_fmt(value)};")
    return exact, prefixes


def _ndc_variants(token: str) -> set[str]:
    """Prefix strings a user-typed NDC fragment can mean (padded forms)."""
    if "-" in token:
        segments = token.split("-")
        if len(segments) == 3:
            try:
                return set(parse_ndc(token).candidates)
            except NdcError:
                pass
        if len(segments) == 2:
            try:
                return {product_ndc_to_ndc9(token)}
            except NdcError:
                pass
        return {token.replace("-", "")}
    digits = token
    variants = {digits}
    if len(digits) == 8:
        # A bare 8-digit product NDC could be either filed shape:
        # 4-4 pads the labeler (0378 4642 -> 003784642), 5-3 pads the
        # product segment (12345 678 -> 123450678).
        variants.add("0" + digits)
        variants.add(digits[:5] + "0" + digits[5:])
    if len(digits) in (10, 11):
        try:
            variants |= set(parse_ndc(digits).candidates)
        except NdcError:
            pass
    return variants


def _ndc_condition(token: str, params: list[object]) -> str:
    clauses = []
    for variant in sorted(_ndc_variants(token)):
        clauses.append(
            "(p.ndc9 LIKE ? OR EXISTS (SELECT 1 FROM package k "
            "WHERE k.ndc9 = p.ndc9 AND k.ndc11 LIKE ?))"
        )
        params.extend([f"{variant}%", f"{variant}%"])
    return "(" + " OR ".join(clauses) + ")"


def _strength_condition(
    number: str, unit: str | None, params: list[object]
) -> str | None:
    exact, prefixes = _strength_keys(number, unit)
    clauses = []
    if exact:
        placeholders = ", ".join("?" for _ in exact)
        clauses.append(f"p.strength_norm IN ({placeholders})")
        params.extend(sorted(exact))
    for prefix in sorted(prefixes):
        clauses.append("p.strength_norm LIKE ?")
        params.append(f"{prefix}%")
    if not clauses:
        return None
    return "(" + " OR ".join(clauses) + ")"


_NAME_FIELDS_SQL = (
    "(p.proprietary_name LIKE ? OR p.proprietary_suffix LIKE ? "
    "OR p.nonproprietary_name LIKE ? OR p.ingredient_set LIKE ? "
    "OR p.labeler_name LIKE ? OR s.rx_name LIKE ?)"
)


def search(
    conn: sqlite3.Connection, query: str, *, limit: int = 25
) -> tuple[SearchHit, ...]:
    tokens = _tokenize(query)
    if not tokens:
        return ()
    conditions: list[str] = []
    params: list[object] = []
    name_terms: list[str] = []
    for token in tokens:
        if token.kind == "name":
            conditions.append(_NAME_FIELDS_SQL)
            params.extend([f"%{token.text}%"] * 6)
            name_terms.append(token.text)
        elif token.kind == "form":
            conditions.append("(p.form_family = ? OR p.dosage_form_raw LIKE ?)")
            params.extend([_FORM_WORDS[token.text], f"%{token.text}%"])
        elif token.kind == "strength":
            assert token.number is not None
            condition = _strength_condition(token.number, token.unit, params)
            if condition is None:
                return ()  # unparseable strength can match nothing
            conditions.append(condition)
        elif token.kind == "ndc":
            conditions.append(_ndc_condition(token.text, params))
        else:  # ndc-or-strength
            assert token.number is not None
            sub_params: list[object] = []
            ndc_sql = _ndc_condition(token.text, sub_params)
            strength_sql = _strength_condition(token.number, token.unit, sub_params)
            joined = ndc_sql if strength_sql is None else f"({ndc_sql} OR {strength_sql})"
            conditions.append(joined)
            params.extend(sub_params)

    rows = conn.execute(
        f"""
        SELECT p.ndc9, p.product_ndc_filed, p.proprietary_name,
               p.proprietary_suffix, p.nonproprietary_name, p.labeler_name,
               p.dosage_form_raw, p.form_family, p.strength_numerator,
               p.strength_unit, p.ingredient_set,
               s.rx_name, s.te_code, s.marketed, s.has_nadac,
               s.rep_ndc11, s.package_count
        FROM product p JOIN search_doc s USING (ndc9)
        WHERE {" AND ".join(conditions)}
        ORDER BY s.marketed DESC, s.has_nadac DESC, p.proprietary_name, p.ndc9
        LIMIT {_FETCH_CAP}
        """,
        params,
    ).fetchall()
    # The ORDER BY makes the capped slice the PLAUSIBLE candidates for a
    # broad query (marketed, surveyed products first) — without it the cap
    # would take an arbitrary scan-order slice and the Python ranking
    # below could never surface what it was never given.

    scored = sorted(
        (( -_score(row, name_terms), _display_name(row), row["ndc9"], row) for row in rows),
    )
    hits = []
    for _negative_score, _name, _ndc9, row in scored[:limit]:
        strength = (
            f"{row['strength_numerator']} {row['strength_unit']}"
            if row["strength_numerator"]
            else None
        )
        hits.append(
            SearchHit(
                ndc9=row["ndc9"],
                rep_ndc11=row["rep_ndc11"],
                ndc_as_filed=row["product_ndc_filed"],
                name=row["proprietary_name"],
                name_suffix=row["proprietary_suffix"],
                generic_name=row["nonproprietary_name"],
                labeler=row["labeler_name"],
                dosage_form=row["dosage_form_raw"],
                form_family=row["form_family"],
                strength=strength,
                te_code=row["te_code"],
                marketed=bool(row["marketed"]),
                package_count=row["package_count"],
            )
        )
    return tuple(hits)


def _display_name(row: sqlite3.Row) -> str:
    return (row["proprietary_name"] or row["nonproprietary_name"] or "").upper()


def _score(row: sqlite3.Row, name_terms: list[str]) -> float:
    """Deterministic relevance: text quality, then marketed, then surveyed."""
    total = 0.0
    fields = [
        row["proprietary_name"],
        row["proprietary_suffix"],
        row["nonproprietary_name"],
        row["ingredient_set"],
        row["labeler_name"],
        row["rx_name"],
    ]
    for term in name_terms:
        needle = term.upper()
        best = 0.0
        for field in fields:
            if not field:
                continue
            haystack = str(field).upper()
            if needle not in haystack:
                continue
            words = re.split(r"[^A-Z0-9]+", haystack)
            if needle in words:
                best = max(best, 3.0)
            elif any(word.startswith(needle) for word in words):
                best = max(best, 2.0)
            else:
                best = max(best, 1.0)
        total += best
    if row["marketed"]:
        total += 2.0
    if row["has_nadac"]:
        total += 0.5
    return total


def build_search_docs(conn: sqlite3.Connection, run_id: int) -> int:
    """Rebuild the search_doc side table (called after every refresh)."""
    conn.execute(
        """
        INSERT INTO search_doc
          (ndc9, rx_name, te_code, marketed, has_nadac, rep_ndc11,
           package_count, run_id)
        SELECT p.ndc9,
               NULL,
               (SELECT MIN(o.te_code)
                  FROM product_ob_link l
                  JOIN ob_product o USING (appl_type, appl_no, product_no)
                 WHERE l.ndc9 = p.ndc9 AND o.te_code IS NOT NULL),
               CASE WHEN p.end_marketing IS NULL AND EXISTS (
                      SELECT 1 FROM package k
                       WHERE k.ndc9 = p.ndc9 AND k.sample_package = 0
                         AND k.end_marketing IS NULL)
                    THEN 1 ELSE 0 END,
               EXISTS (SELECT 1 FROM nadac n JOIN package k ON k.ndc11 = n.ndc11
                        WHERE k.ndc9 = p.ndc9),
               COALESCE(
                 (SELECT MIN(k.ndc11) FROM package k
                   WHERE k.ndc9 = p.ndc9 AND k.sample_package = 0
                     AND k.end_marketing IS NULL),
                 (SELECT MIN(k.ndc11) FROM package k WHERE k.ndc9 = p.ndc9)),
               (SELECT COUNT(*) FROM package k
                 WHERE k.ndc9 = p.ndc9 AND k.sample_package = 0),
               ?
        FROM product p
        """,
        (run_id,),
    )
    # Best RxNorm concept name per product; SCD preferred over SBD — the
    # same lexicographic-TTY rule the resolve prefetch uses.
    best_tty: dict[str, str] = {}
    best_name: dict[str, str] = {}
    for row in conn.execute(
        """
        SELECT p.ndc9, c.tty, c.name
        FROM rx_ndc n
        JOIN rx_concept c USING (rxcui)
        JOIN package p ON p.ndc11 = n.ndc11
        """
    ):
        current = best_tty.get(row["ndc9"])
        if current is None or row["tty"] > current:
            best_tty[row["ndc9"]] = row["tty"]
            best_name[row["ndc9"]] = row["name"]
    conn.executemany(
        "UPDATE search_doc SET rx_name = ? WHERE ndc9 = ?",
        [(name, ndc9) for ndc9, name in best_name.items()],
    )
    count = conn.execute("SELECT COUNT(*) FROM search_doc").fetchone()[0]
    return int(count)
