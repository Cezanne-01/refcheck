"""Shared text-matching utilities used by both fetch and verify layers.

Kept at the top level (not under fetch/ or verify/) so both packages can
import without creating a circular dependency. These are pure functions
operating on strings — no model dependencies.
"""
from __future__ import annotations
import re
import unicodedata
from rapidfuzz import fuzz


_SMART_TO_ASCII = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",
    " ": " ", " ": " ", "​": "",
})


def normalize_text_for_match(s: str) -> str:
    """Normalize a string for fuzzy comparison."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_SMART_TO_ASCII)
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def title_similarity(a: str, b: str) -> float:
    """0.0~1.0. Weighted average of token_set_ratio and ratio."""
    a_n = normalize_text_for_match(a)
    b_n = normalize_text_for_match(b)
    if not a_n or not b_n:
        return 0.0
    set_score = fuzz.token_set_ratio(a_n, b_n) / 100
    full_score = fuzz.ratio(a_n, b_n) / 100
    return 0.5 * set_score + 0.5 * full_score


def normalize_surname(s: str) -> str:
    return re.sub(r"\s+", "", s.lower().strip())


def surname_overlap(a: list[str], b: list[str]) -> bool:
    """True if at least one surname overlaps (case-insensitive, whitespace-stripped)."""
    if not a or not b:
        return False
    set_a = {normalize_surname(x) for x in a if x}
    set_b = {normalize_surname(x) for x in b if x}
    return bool(set_a & set_b)
