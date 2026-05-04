from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal
from refcheck._match import (
    normalize_text_for_match as _normalize_title,
    title_similarity,
    surname_overlap,
)
from refcheck.schema.models import Reference, Author


__all__ = [
    "title_similarity",
    "authors_match",
    "compare_metadata",
    "MatchResult",
    "DiffSeverity",
]


# Thresholds — chosen so that nuisance differences (abbreviations, minor
# punctuation, typos) do NOT get flagged. Only flag when the difference
# would actually mislead a reader.
_TITLE_SIM_THRESHOLD = 0.75   # below = title is substantially different
_JOURNAL_SIM_THRESHOLD = 0.50  # below = different journal (not abbreviation)
_YEAR_PREPRINT_GAP = 1         # off-by-one => preprint vs published, info-only
_YEAR_ERROR_GAP = 2            # off by ≥2 => real year error


def authors_match(a: list[Author], b: list[Author]) -> bool:
    """Author surnames overlap by at least one element."""
    return surname_overlap(
        [x.family for x in a if x.family],
        [x.family for x in b if x.family],
    )


DiffSeverity = Literal["critical", "major", "minor", "info"]


@dataclass
class MatchResult:
    status: Literal["verified", "metadata_error", "hallucination", "unverifiable"]
    # field name -> (user_value, canonical_value, severity)
    field_diffs: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    # field name -> severity classification
    diff_severities: dict[str, DiffSeverity] = field(default_factory=dict)
    title_sim: float = 0.0
    preprint_vs_published: bool = False


def compare_metadata(ref: Reference, canonical: Reference) -> MatchResult:
    """Deterministic comparison of user citation vs canonical record.

    Flags ALL real differences but categorizes them by severity so the
    renderer can show critical issues prominently and demote minor ones
    to the bottom of the diff table. Nuisance-level cases that aren't
    really errors are excluded entirely.

    Severity rubric:
      critical = wrong DOI, wrong authors (no surname overlap)
      major    = title substantially different, journal entirely different,
                 year off by ≥2
      minor    = volume / issue / pages mismatch
      info     = preprint vs published (year off by 1, rest matches)

    Excluded (NOT flagged):
      - Title differences above the substantial threshold (i.e. typos,
        punctuation, capitalization)
      - Journal abbreviation vs full-name (they're equivalent)
      - Author order / extra-author differences when at least one surname
        overlaps (citation styles vary)
    """
    diffs: dict[str, tuple[str | None, str | None]] = {}
    sev: dict[str, DiffSeverity] = {}
    preprint_flag = False

    # ---------- title ----------
    sim = title_similarity(ref.title or "", canonical.title or "")
    if sim < _TITLE_SIM_THRESHOLD:
        diffs["title"] = (ref.title, canonical.title)
        sev["title"] = "major"

    # ---------- authors ----------
    if not authors_match(ref.authors, canonical.authors):
        diffs["authors"] = (
            ", ".join(a.family for a in ref.authors if a.family),
            ", ".join(a.family for a in canonical.authors if a.family),
        )
        sev["authors"] = "critical"

    # ---------- year ----------
    if (
        ref.year is not None
        and canonical.year is not None
        and ref.year != canonical.year
    ):
        gap = abs(ref.year - canonical.year)
        diffs["year"] = (str(ref.year), str(canonical.year))
        if gap == _YEAR_PREPRINT_GAP and sim >= _TITLE_SIM_THRESHOLD and authors_match(ref.authors, canonical.authors):
            # off-by-one with otherwise-matching paper: preprint vs published
            preprint_flag = True
            sev["year"] = "info"
        elif gap >= _YEAR_ERROR_GAP:
            sev["year"] = "major"
        else:
            # gap == 1 with title or author also mismatched — still a real
            # year diff, just less load-bearing. Keep it visible as minor.
            sev["year"] = "minor"

    # ---------- journal ----------
    if ref.journal and canonical.journal:
        if _normalize_title(ref.journal) != _normalize_title(canonical.journal):
            sim_j = title_similarity(ref.journal, canonical.journal)
            if sim_j < _JOURNAL_SIM_THRESHOLD:
                diffs["journal"] = (ref.journal, canonical.journal)
                sev["journal"] = "major"
            # Otherwise treat as abbreviation difference — don't flag.

    # ---------- DOI ----------
    if ref.doi and canonical.doi and ref.doi.lower() != canonical.doi.lower():
        diffs["doi"] = (ref.doi, canonical.doi)
        sev["doi"] = "critical"

    # ---------- volume / issue / pages ----------
    # Minor severity — relevant for retrieval but doesn't usually mean the
    # citation is wrong. Shown at the bottom of the diff table.
    if ref.volume and canonical.volume and ref.volume.strip() != canonical.volume.strip():
        diffs["volume"] = (ref.volume, canonical.volume)
        sev["volume"] = "minor"
    if ref.issue and canonical.issue and ref.issue.strip() != canonical.issue.strip():
        diffs["issue"] = (ref.issue, canonical.issue)
        sev["issue"] = "minor"
    if ref.pages and canonical.pages and _pages_differ(ref.pages, canonical.pages):
        diffs["pages"] = (ref.pages, canonical.pages)
        sev["pages"] = "minor"

    status: Literal["verified", "metadata_error"]
    status = "verified" if not diffs else "metadata_error"
    return MatchResult(
        status=status,
        field_diffs=diffs,
        diff_severities=sev,
        title_sim=sim,
        preprint_vs_published=preprint_flag,
    )


def _pages_differ(a: str, b: str) -> bool:
    """Compare page strings ignoring whitespace, dash style, and short→long
    page expansion (e.g. '660-7' vs '660-667')."""
    def _norm(p: str) -> str:
        return p.replace(" ", "").replace("–", "-").replace("—", "-").lower()
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return False
    # Try short-form expansion: "660-7" vs "660-667" — same start, end is
    # the suffix of the longer end.
    parts_a = na.split("-")
    parts_b = nb.split("-")
    if len(parts_a) == 2 and len(parts_b) == 2 and parts_a[0] == parts_b[0]:
        if parts_b[1].endswith(parts_a[1]) or parts_a[1].endswith(parts_b[1]):
            return False
    return True
