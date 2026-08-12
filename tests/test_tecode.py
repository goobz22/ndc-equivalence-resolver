"""TE code parsing tests — the AB1/AB2/AB3 partition machinery."""

from ndcres.tecode import TECode, parse_te_code


def test_subscripted_code() -> None:
    code = parse_te_code("AB1")
    assert code == TECode(letter_class="AB", subscript="1")
    assert code.full == "AB1"
    assert code.a_rated


def test_plain_ab() -> None:
    code = parse_te_code("AB")
    assert code is not None
    assert code.letter_class == "AB"
    assert code.subscript == ""


def test_subscripts_partition() -> None:
    # The load-bearing rule: AB1 and AB3 are NOT the same code.
    assert parse_te_code("AB1") != parse_te_code("AB3")
    assert parse_te_code("AB1") != parse_te_code("AB")


def test_b_codes() -> None:
    code = parse_te_code("BX")
    assert code is not None
    assert not code.a_rated


def test_blank_means_no_evaluation() -> None:
    assert parse_te_code("") is None
    assert parse_te_code("   ") is None
    assert parse_te_code(None) is None


def test_lowercase_tolerated() -> None:
    code = parse_te_code("ab2")
    assert code is not None
    assert code.full == "AB2"


def test_at_subscript() -> None:
    code = parse_te_code("AT1")
    assert code == TECode(letter_class="AT", subscript="1")
