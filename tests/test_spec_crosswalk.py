"""docs/SPEC.md cannot rot silently.

Section 19 of the spec maps every invariant (INV-x.y) to the tests that
prove it. This test parses those rows and asserts every referenced test
actually exists in the collected suite — a renamed or deleted test breaks
the build until the spec row is updated in the same change.

Scope honesty: this proves the references RESOLVE, not that the mapping
is COMPLETE — completeness is the per-phase review discipline (a phase
lands its spec section + rows + tests in one commit).

Reference grammar (SPEC.md §19): `tests/<file>::<test_name>`, class names
omitted, parameterized tests referenced by base name, multiple pins
separated by ` ; `. Rows whose pin cell starts with the ⚠️ marker are
declared-open gaps and are exempt (each names its owner in the row).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "docs" / "SPEC.md"

# A format drift that made the parser match nothing would turn this whole
# test vacuous-green (the planted-defect lesson: an instrument must fail
# on a broken input, not skip it). The spec currently carries far more
# rows than this floor; it only guards against parsing zero.
MINIMUM_EXPECTED_ROWS = 40


def _spec_rows() -> list[tuple[str, str]]:
    """(invariant_id, pins_cell) for every table row in section 19."""
    rows: list[tuple[str, str]] = []
    for line in SPEC_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("| INV-"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            pytest.fail(f"malformed traceability row (needs 3 cells): {line!r}")
        rows.append((cells[0], cells[-1]))
    return rows


def _collected_test_ids() -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    ids = []
    for line in result.stdout.splitlines():
        if "::" not in line:
            continue
        # Strip parameterization: tests/x.py::test_y[case] -> tests/x.py::test_y
        ids.append(line.split("[", 1)[0].strip().replace("\\", "/"))
    if not ids:
        pytest.fail(
            "pytest --collect-only returned no test ids — collection broke:\n"
            + result.stdout[-2000:]
            + result.stderr[-2000:]
        )
    return ids


def _reference_resolves(ref: str, collected: list[str]) -> bool:
    if "::" not in ref:
        return False
    ref_file, ref_name = ref.split("::", 1)
    suffix = f"::{ref_name}"
    return any(
        test_id.split("::", 1)[0] == ref_file and test_id.endswith(suffix)
        for test_id in collected
    )


class TestSpecCrosswalk:
    def test_traceability_rows_parse_and_are_unique(self) -> None:
        rows = _spec_rows()
        assert len(rows) >= MINIMUM_EXPECTED_ROWS, (
            f"only {len(rows)} INV rows parsed from SPEC.md — either the "
            "table shrank dramatically or the row format drifted"
        )
        ids = [invariant_id for invariant_id, _ in rows]
        duplicates = {i for i in ids if ids.count(i) > 1}
        assert not duplicates, f"duplicate invariant ids: {sorted(duplicates)}"

    def test_every_referenced_test_exists(self) -> None:
        rows = _spec_rows()
        collected = _collected_test_ids()
        dangling: list[str] = []
        open_rows = 0
        for invariant_id, pins in rows:
            if pins.startswith("⚠️"):
                open_rows += 1
                continue
            for ref in (r.strip() for r in pins.split(";")):
                if not _reference_resolves(ref, collected):
                    dangling.append(f"{invariant_id} -> {ref!r}")
        assert not dangling, (
            "SPEC.md references tests that do not exist (update the spec row "
            "in the same change that renamed/removed the test):\n  "
            + "\n  ".join(dangling)
        )
        # Every declared-open row must name an owner — a bare warning marker
        # is an exclusion nobody can audit.
        for invariant_id, pins in rows:
            if pins.startswith("⚠️"):
                assert "owner" in pins.lower() or "by design" in pins.lower(), (
                    f"{invariant_id} is OPEN without naming an owner"
                )
        assert open_rows <= 5, (
            f"{open_rows} OPEN rows — the audit debt is growing; "
            "close some before adding more"
        )
