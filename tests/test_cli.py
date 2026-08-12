"""CLI smoke tests for the commands that exist so far."""

import pytest

from ndcres.cli import main


def test_normalize_unambiguous(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["normalize", "0378-4642-26"]) == 0
    out = capsys.readouterr().out
    assert "00378464226" in out
    assert "4-4-2" in out


def test_normalize_ambiguous_lists_candidates(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["normalize", "0378464226"]) == 1
    out = capsys.readouterr().out
    assert "ambiguous" in out
    assert "00378464226" in out
    assert "03784064226" in out
    assert "03784642206" in out


def test_normalize_invalid(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["normalize", "not-an-ndc"]) == 2
    assert "error" in capsys.readouterr().err
