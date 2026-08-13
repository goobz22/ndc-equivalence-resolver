"""FDA-list history via the Wayback Machine (the ASPE-validated method).

The legacy `Drugshortages.cfm` endpoint served the whole shortage list
as CSV; the Internet Archive holds ~45 captures from 2019-10 onward.
Each capture becomes fda_list_history rows (snapshot_source
'wayback-cfm'), including FDA's own per-row "Initial Posting Date" —
the first-listing date the lead-time analysis measures against.

Header validation is fail-loud: the 22-column legacy header is pinned
verbatim (spacing normalized); drift raises rather than mis-parsing.
"""

from __future__ import annotations

import csv
import io
import sqlite3
import time
import urllib.request
from dataclasses import dataclass

from ..history import normalize_drug_name

CDX_URL = (
    "http://web.archive.org/cdx/search/cdx"
    "?url=accessdata.fda.gov/scripts/drugshortages/Drugshortages.cfm"
    "&output=json&filter=statuscode:200&collapse=timestamp:8"
)
SNAPSHOT_URL = (
    "http://web.archive.org/web/{timestamp}id_/"
    "https://www.accessdata.fda.gov/scripts/drugshortages/Drugshortages.cfm"
)

# The legacy CSV header, exactly as served (leading/trailing spaces in
# the raw file are normalized by strip before comparison).
EXPECTED_COLUMNS = (
    "Generic Name",
    "Company Name",
    "Contact Info",
    "Presentation",
    "Type of Update",
    "Date of Update",
    "Availability Information",
    "Related Information",
    "Resolved Note",
    "Reason for Shortage",
    "Therapeutic Category",
    "Status",
    "Change Date",
    "Date Discontinued",
    "Initial Posting Date",
)

_REQUEST_HEADERS = {"User-Agent": "ndc-equivalence-resolver backtest"}


@dataclass(frozen=True)
class LegacyRow:
    generic_name: str
    company: str
    status: str
    initial_posting: str | None
    update_date: str | None


def _iso_from_mdy(text: str) -> str | None:
    """'10/02/2020' -> '2020-10-02'; blank/malformed -> None."""
    parts = text.strip().split("/")
    if len(parts) != 3:
        return None
    month, day, year = parts
    if not (month.isdigit() and day.isdigit() and len(year) == 4):
        return None
    return f"{year}-{int(month):02d}-{int(day):02d}"


def parse_legacy_csv(text: str) -> list[LegacyRow]:
    reader = csv.reader(io.StringIO(text))
    try:
        header = [column.strip() for column in next(reader)]
    except StopIteration as error:
        raise RuntimeError("legacy CSV snapshot is empty") from error
    missing = [column for column in EXPECTED_COLUMNS if column not in header]
    if missing:
        raise RuntimeError(
            f"legacy CSV header drift — missing columns: {missing}; "
            f"got: {header[:12]}..."
        )
    index = {column: header.index(column) for column in EXPECTED_COLUMNS}
    rows: list[LegacyRow] = []
    for record in reader:
        if len(record) < len(EXPECTED_COLUMNS):
            continue
        name = record[index["Generic Name"]].strip()
        if not name:
            continue
        rows.append(
            LegacyRow(
                generic_name=name,
                company=record[index["Company Name"]].strip(),
                status=record[index["Status"]].strip(),
                initial_posting=_iso_from_mdy(
                    record[index["Initial Posting Date"]]
                ),
                update_date=_iso_from_mdy(record[index["Date of Update"]]),
            )
        )
    return rows


def _get(url: str, *, timeout: float = 120.0, attempts: int = 4) -> bytes:
    # The Archive 504s/429s routinely under load — retry with backoff;
    # only a persistent failure raises.
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=_REQUEST_HEADERS)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return bytes(response.read())
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504):
                raise
            last_error = error
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
        if attempt + 1 < attempts:
            time.sleep(5 * (2**attempt))
    raise RuntimeError(f"wayback fetch failed after {attempts} attempts: {url}") from last_error


def list_snapshot_timestamps() -> list[str]:
    import json

    payload = json.loads(_get(CDX_URL))
    return [row[1] for row in payload[1:]]  # row 0 is the CDX header


def store_snapshot(
    conn: sqlite3.Connection, timestamp: str, rows: list[LegacyRow]
) -> int:
    snapshot_date = f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
    before = conn.execute(
        "SELECT count(*) FROM fda_list_history WHERE snapshot_source='wayback-cfm'"
    ).fetchone()[0]
    with conn:
        conn.executemany(
            """
            INSERT OR IGNORE INTO fda_list_history
              (snapshot_date, snapshot_source, drug_name_raw, drug_name_norm,
               company, status, initial_posting, update_date)
            VALUES (?, 'wayback-cfm', ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot_date,
                    row.generic_name,
                    normalize_drug_name(row.generic_name),
                    row.company,
                    row.status,
                    row.initial_posting,
                    row.update_date,
                )
                for row in rows
            ],
        )
    after = conn.execute(
        "SELECT count(*) FROM fda_list_history WHERE snapshot_source='wayback-cfm'"
    ).fetchone()[0]
    return int(after - before)


def fetch_wayback_history(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
    pause_seconds: float = 2.0,
) -> dict[str, int]:
    """Fetch every archived capture into fda_list_history.

    Idempotent (the PK dedupes); polite to the Archive (pauses between
    captures); a capture that fails to parse raises — a broken snapshot
    must be seen, not skipped.
    """
    timestamps = list_snapshot_timestamps()
    if limit is not None:
        timestamps = timestamps[:limit]
    stored: dict[str, int] = {}
    for position, timestamp in enumerate(timestamps):
        text = _get(SNAPSHOT_URL.format(timestamp=timestamp)).decode(
            "utf-8", errors="replace"
        )
        rows = parse_legacy_csv(text)
        stored[timestamp] = store_snapshot(conn, timestamp, rows)
        if position + 1 < len(timestamps):
            time.sleep(pause_seconds)
    return stored
