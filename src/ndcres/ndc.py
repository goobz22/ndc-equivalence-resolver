"""NDC parsing and normalization.

US National Drug Codes appear in the wild in several spellings:

- 10-digit hyphenated, in the labeler's as-filed segmentation
  (21 CFR 207.33): ``4-4-2`` ("0378-4642-26"), ``5-3-2`` ("65162-149-08"),
  ``5-4-1`` ("68968-6650-8").
- 11-digit hyphenated HIPAA form: "00378-4642-26" (``5-4-2``).
- 11-digit bare: "00378464226" — the claims format used natively by NADAC
  and RxNorm, and the canonical join key throughout ndcres.
- 10-digit bare: inherently ambiguous — the same ten digits are a valid
  4-4-2, 5-3-2, AND 5-4-1 parse, each yielding a different 11-digit code.
  Callers must disambiguate against known packages (21 CFR 207.33(b)(3):
  one labeler code uses exactly one configuration).

21 CFR 207.33 also permits natively-11-digit ``6-4-1`` / ``6-3-2`` codes
(no such labeler exists in current FDA data); those hyphenated forms are
accepted and treated as already-normalized. FDA moves to a uniform
12-digit NDC on 2033-03-07 — out of scope here.

Zero-padding positions (10 → 11 digits):

    4-4-2  pad the labeler   0378-4642-26  -> 00378464226
    5-3-2  pad the product   65162-149-08  -> 65162014908
    5-4-1  pad the package   68968-6650-8  -> 68968665008
"""

from __future__ import annotations

from dataclasses import dataclass

# Hyphenated segment-length shapes that are exactly one zero short of the
# 11-digit 5-4-2 form, mapped to the segment index that takes the pad.
_TEN_DIGIT_SHAPES: dict[tuple[int, int, int], int] = {
    (4, 4, 2): 0,
    (5, 3, 2): 1,
    (5, 4, 1): 2,
}
# Hyphenated shapes that are already 11 digits.
_ELEVEN_DIGIT_SHAPES = {(5, 4, 2), (6, 4, 1), (6, 3, 2)}

_SEGMENT_WIDTHS_11 = (5, 4, 2)


class NdcError(ValueError):
    """Raised when a string cannot be interpreted as an NDC."""


@dataclass(frozen=True)
class NdcQuery:
    """The result of parsing user-supplied NDC text.

    ``candidates`` holds one 11-digit code when the spelling was
    unambiguous, or up to three when a bare 10-digit string was given
    (one per permissible segmentation, deduplicated, in 4-4-2 / 5-3-2 /
    5-4-1 order). ``shape`` records the as-filed segmentation when the
    input carried hyphens; bare input has no knowable shape.
    """

    raw: str
    candidates: tuple[str, ...]
    shape: str | None
    ambiguous: bool

    @property
    def ndc11(self) -> str:
        """The single candidate; only valid when not ambiguous."""
        if self.ambiguous:
            raise NdcError(
                f"NDC {self.raw!r} is ambiguous without hyphens; "
                f"candidates: {', '.join(self.candidates)}"
            )
        return self.candidates[0]


def parse_ndc(text: str) -> NdcQuery:
    """Parse any accepted NDC spelling into candidate 11-digit codes.

    Raises :class:`NdcError` for strings that cannot be an NDC in any
    permissible configuration.
    """
    raw = text.strip()
    if not raw:
        raise NdcError("empty NDC")

    if "-" in raw:
        return _parse_hyphenated(raw)
    if not raw.isdigit():
        raise NdcError(f"NDC {raw!r} contains non-digit characters")
    if len(raw) == 11:
        return NdcQuery(raw=raw, candidates=(raw,), shape=None, ambiguous=False)
    if len(raw) == 10:
        candidates = _bare10_candidates(raw)
        return NdcQuery(
            raw=raw,
            candidates=candidates,
            shape=None,
            ambiguous=len(candidates) > 1,
        )
    raise NdcError(
        f"NDC {raw!r} has {len(raw)} digits; expected 10 or 11 (or a hyphenated form)"
    )


def _parse_hyphenated(raw: str) -> NdcQuery:
    parts = raw.split("-")
    if len(parts) != 3 or not all(p.isdigit() and p for p in parts):
        raise NdcError(f"NDC {raw!r} is not a valid labeler-product-package form")
    widths = (len(parts[0]), len(parts[1]), len(parts[2]))

    pad_index = _TEN_DIGIT_SHAPES.get(widths)
    if pad_index is not None:
        padded = list(parts)
        padded[pad_index] = "0" + padded[pad_index]
        ndc11 = "".join(padded)
        shape = "-".join(str(w) for w in widths)
        return NdcQuery(raw=raw, candidates=(ndc11,), shape=shape, ambiguous=False)

    if widths in _ELEVEN_DIGIT_SHAPES:
        shape = "-".join(str(w) for w in widths)
        return NdcQuery(
            raw=raw, candidates=("".join(parts),), shape=shape, ambiguous=False
        )

    raise NdcError(
        f"NDC {raw!r} has segment widths {widths}; "
        "not a configuration permitted by 21 CFR 207.33"
    )


def _bare10_candidates(digits: str) -> tuple[str, ...]:
    """All 11-digit codes a bare 10-digit string could normalize to."""
    seen: list[str] = []
    for shape, pad_index in _TEN_DIGIT_SHAPES.items():
        widths = list(shape)
        segments: list[str] = []
        pos = 0
        for width in widths:
            segments.append(digits[pos : pos + width])
            pos += width
        segments[pad_index] = "0" + segments[pad_index]
        candidate = "".join(segments)
        if candidate not in seen:
            seen.append(candidate)
    return tuple(seen)


def ndc11_to_hipaa(ndc11: str) -> str:
    """Render an 11-digit code in the hyphenated 5-4-2 display form."""
    if len(ndc11) != 11 or not ndc11.isdigit():
        raise NdcError(f"{ndc11!r} is not an 11-digit NDC")
    out: list[str] = []
    pos = 0
    for width in _SEGMENT_WIDTHS_11:
        out.append(ndc11[pos : pos + width])
        pos += width
    return "-".join(out)


def ndc9_of(ndc11: str) -> str:
    """The 9-digit labeler+product prefix (product grain key)."""
    if len(ndc11) != 11 or not ndc11.isdigit():
        raise NdcError(f"{ndc11!r} is not an 11-digit NDC")
    return ndc11[:9]


def product_ndc_to_ndc9(product_ndc: str) -> str:
    """Normalize an as-filed product NDC ('0378-4642', '65162-149') to 9 digits."""
    parts = product_ndc.strip().split("-")
    if len(parts) != 2 or not all(p.isdigit() and p for p in parts):
        raise NdcError(f"{product_ndc!r} is not a labeler-product NDC")
    labeler, product = parts
    if len(labeler) == 4:
        labeler = "0" + labeler
    if len(labeler) != 5:
        # 6-digit labelers would be natively 11-digit codes; none exist in
        # current data, and their 9-digit prefix is not representable here.
        raise NdcError(f"{product_ndc!r} has an unsupported labeler width")
    if len(product) == 3:
        product = "0" + product
    if len(product) != 4:
        raise NdcError(f"{product_ndc!r} has an unsupported product width")
    return labeler + product
