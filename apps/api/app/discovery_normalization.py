"""Deterministic text normalization for field discovery."""

from __future__ import annotations

import re
import unicodedata

_DIGIT_RUN = re.compile(r"\d+")
_WHITESPACE = re.compile(r"\s+")


def normalize_search_text(value: str) -> str:
    """Return an accent/case-insensitive substring-search key."""
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return _WHITESPACE.sub(" ", without_marks.casefold()).strip()


def natural_sort_key(value: str) -> str:
    """Return a lexically sortable key with natural ordering for digit runs."""
    normalized = normalize_search_text(value)

    def encode_digits(match: re.Match[str]) -> str:
        digits = match.group(0).lstrip("0") or "0"
        # PostgreSQL text rejects NUL bytes; SOH is a stable internal separator.
        return f"\x01{len(digits):08d}:{digits}\x01"

    return _DIGIT_RUN.sub(encode_digits, normalized)
