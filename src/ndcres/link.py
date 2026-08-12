"""product_ob_link — the materialized NDC-Directory ↔ Orange-Book join.

This is the linchpin of the resolver: the Orange Book contains no NDCs,
so therapeutic-equivalence codes reach an NDC only through the
application-number join, disambiguated by canonical strength. The join is
built once per refresh (never fuzzy-matched at query time) and every
product records WHY it did or didn't link:

    linked / special-cased  — one OB row found (appl join, strength match
                              when the application spans strengths)
    no-application          — OTC monograph / unapproved / biologic; can
                              never carry a TE rating
    no-ob-row               — application number absent from the OB
                              (upstream lag or labeler error)
    strength-mismatch       — application found, no strength agreed
    ambiguous               — several OB rows matched; we never guess

Authorized generics and relabelers share the brand's application number;
the resulting many-to-one links are correct and preserved (the Orange
Book preface's repackager clause: such products inherit the applicant
product's TE rating).
"""

from __future__ import annotations

import sqlite3


def build_product_ob_link(conn: sqlite3.Connection, run_id: int) -> int:
    """(Re)build the link table; returns the number of link rows."""
    links = 0
    products = conn.execute(
        """
        SELECT ndc9, appl_type, appl_no, appl_no_raw, strength_norm
        FROM product
        """
    ).fetchall()

    for product in products:
        ndc9 = product["ndc9"]
        if product["appl_type"] is None or product["appl_no"] is None:
            _set_status(conn, ndc9, "no-application")
            continue

        ob_rows = conn.execute(
            """
            SELECT appl_type, appl_no, product_no, strength_norm
            FROM ob_product
            WHERE appl_type = ? AND appl_no = ?
            """,
            (product["appl_type"], product["appl_no"]),
        ).fetchall()

        special_cased = (
            product["appl_no_raw"] is not None
            and product["appl_no"] != product["appl_no_raw"]
        )

        if not ob_rows:
            _set_status(conn, ndc9, "no-ob-row")
            continue

        if len(ob_rows) == 1:
            matches = ob_rows
            method = "appl-single-product"
        else:
            matches = [
                row
                for row in ob_rows
                if row["strength_norm"] is not None
                and row["strength_norm"] == product["strength_norm"]
            ]
            method = "appl+strength"

        if not matches:
            _set_status(conn, ndc9, "strength-mismatch")
            continue
        if len(matches) > 1:
            # Several OB products share the strength (or the application
            # has one strength listed twice) — never guess.
            _set_status(conn, ndc9, "ambiguous")
            continue

        match = matches[0]
        conn.execute(
            """
            INSERT OR REPLACE INTO product_ob_link
              (ndc9, appl_type, appl_no, product_no, match_method, run_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ndc9,
                match["appl_type"],
                match["appl_no"],
                match["product_no"],
                "special-case" if special_cased else method,
                run_id,
            ),
        )
        _set_status(conn, ndc9, "special-cased" if special_cased else "linked")
        links += 1
    return links


def _set_status(conn: sqlite3.Connection, ndc9: str, status: str) -> None:
    conn.execute(
        "UPDATE product SET ob_link_status = ? WHERE ndc9 = ?", (status, ndc9)
    )
