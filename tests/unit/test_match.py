"""Tests for the shared text-matching utilities (refcheck._match)."""
from __future__ import annotations
from refcheck._match import (
    title_similarity,
    surname_overlap,
    normalize_text_for_match,
)


# ---------------------------------------------------------------------------
# normalize_text_for_match
# ---------------------------------------------------------------------------

def test_normalize_collapses_whitespace():
    assert normalize_text_for_match("a\n\n   b\t c") == "a b c"


def test_normalize_lowercases_and_strips_punct():
    """Punctuation becomes whitespace then collapses; trailing space may remain."""
    assert normalize_text_for_match("Hello, World!").strip() == "hello world"


def test_normalize_smart_quotes_normalized_to_alnum_run():
    """Smart quotes get translated to ASCII quotes which are then stripped
    by the alphanumeric-only regex — so the visible result is just the
    surrounding words."""
    assert normalize_text_for_match("Don’t “go”").strip().split() == ["don", "t", "go"]


def test_normalize_empty_string():
    assert normalize_text_for_match("") == ""


# ---------------------------------------------------------------------------
# title_similarity
# ---------------------------------------------------------------------------

def test_title_similarity_identical():
    assert title_similarity("Hello world", "Hello world") == 1.0


def test_title_similarity_empty_returns_zero():
    assert title_similarity("", "anything") == 0.0
    assert title_similarity("anything", "") == 0.0


def test_title_similarity_word_order_insensitive():
    """Same tokens in different order — token_set_ratio is 1.0 but the
    char-level ratio is lower, so the blended score sits in the 0.7–0.9
    range (still well above the rejection threshold)."""
    sim = title_similarity("brain volume gambling", "gambling brain volume")
    assert sim > 0.7


def test_title_similarity_minor_typo():
    sim = title_similarity(
        "Neurobiology of gambling behaviors",
        "Neurobiology of gambling behavior",  # singular vs plural
    )
    assert sim > 0.85


def test_title_similarity_subtitle_difference():
    """Same main title, different subtitle — should still be >0.5."""
    sim = title_similarity(
        "Adolescent gambling: a systematic review",
        "Adolescent gambling: clinical implications",
    )
    assert sim > 0.5


def test_title_similarity_completely_unrelated():
    """Two genuinely unrelated titles with no common words fall well below
    the rejection threshold (0.40)."""
    sim = title_similarity(
        "Adolescent gambling depression comorbid",
        "Quantum chromodynamics LHC physics calorimetry",
    )
    assert sim < 0.40


def test_title_similarity_short_word_overlap_only():
    """Short common words like 'of' alone shouldn't make unrelated titles
    pass the rejection threshold once the author penalty is applied. Pure
    title similarity may still be ~0.4 from accidental letter overlap, but
    the DB clients halve it when no author surname matches."""
    raw = title_similarity(
        "Neurobiology of gambling behaviors in adolescents",
        "Observation of B-meson decay at CMS LHCb",
    )
    # With no author overlap the DB clients multiply by 0.5
    after_author_penalty = raw * 0.5
    assert after_author_penalty < 0.30


# ---------------------------------------------------------------------------
# surname_overlap
# ---------------------------------------------------------------------------

def test_surname_overlap_exact():
    assert surname_overlap(["Potenza"], ["Potenza"]) is True


def test_surname_overlap_case_insensitive():
    assert surname_overlap(["potenza"], ["POTENZA"]) is True


def test_surname_overlap_partial_match():
    assert surname_overlap(["Potenza", "Smith"], ["Smith"]) is True


def test_surname_overlap_no_overlap():
    assert surname_overlap(["Potenza"], ["Smith"]) is False


def test_surname_overlap_empty_inputs():
    assert surname_overlap([], ["Smith"]) is False
    assert surname_overlap(["Smith"], []) is False
    assert surname_overlap([], []) is False


def test_surname_overlap_strips_whitespace():
    """Compound surname "Guillou Landreat" should still overlap with "Landreat" if normalized."""
    # surname_overlap normalizes by stripping internal whitespace, so
    # "Guillou Landreat" becomes "guilloulandreat" — won't overlap with
    # "Landreat" alone. This test documents that behavior; a higher-level
    # routine in the agent must split compound surnames if needed.
    assert surname_overlap(["Guillou Landreat"], ["Landreat"]) is False
