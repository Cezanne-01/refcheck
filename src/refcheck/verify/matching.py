from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Literal
from rapidfuzz import fuzz
from refcheck.schema.models import Reference, Author


_SMART_TO_ASCII = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",  # en/em dash, minus
    " ": " ", " ": " ", "​": "",   # nbsp, thin sp, zero-width
})


def _normalize_title(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_SMART_TO_ASCII)
    s = s.lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def title_similarity(a: str, b: str) -> float:
    """0.0~1.0. token_set_ratio(부분 포함 허용)과 ratio(전체 일치)의 가중 평균."""
    a_n = _normalize_title(a)
    b_n = _normalize_title(b)
    set_score = fuzz.token_set_ratio(a_n, b_n) / 100
    full_score = fuzz.ratio(a_n, b_n) / 100
    return 0.5 * set_score + 0.5 * full_score


def _norm_surname(s: str) -> str:
    return re.sub(r"\s+", "", s.lower().strip())


def authors_match(a: list[Author], b: list[Author]) -> bool:
    """저자 집합 교집합이 비어있지 않으면 일치로 본다.

    예전엔 첫 저자 성 일치를 강제했지만, 인용 과정에서 저자 순서가 바뀌거나
    첫 저자만 잘못 적힌 경우 실제로 존재하는 논문이 false negative로 떨어졌다.
    한 명이라도 겹치면 후보로 인정하고, 최종 verdict는 LLM 에이전트가 종합해서 내린다.
    """
    if not a or not b:
        return False
    set_a = {_norm_surname(x.family) for x in a if x.family}
    set_b = {_norm_surname(x.family) for x in b if x.family}
    return bool(set_a & set_b)


@dataclass
class MatchResult:
    status: Literal["verified", "metadata_error", "hallucination", "unverifiable"]
    field_diffs: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    title_sim: float = 0.0
    preprint_vs_published: bool = False


def compare_metadata(ref: Reference, canonical: Reference) -> MatchResult:
    diffs: dict[str, tuple[str | None, str | None]] = {}
    preprint_flag = False

    sim = title_similarity(ref.title, canonical.title)
    if sim < 0.90:
        diffs["title"] = (ref.title, canonical.title)

    if not authors_match(ref.authors, canonical.authors):
        diffs["authors"] = (
            ", ".join(a.family for a in ref.authors),
            ", ".join(a.family for a in canonical.authors),
        )

    if ref.year != canonical.year:
        diffs["year"] = (str(ref.year), str(canonical.year))
        if (
            ref.year is not None
            and canonical.year is not None
            and abs(ref.year - canonical.year) == 1
            and sim >= 0.90
            and authors_match(ref.authors, canonical.authors)
        ):
            preprint_flag = True

    if ref.journal and canonical.journal:
        if _normalize_title(ref.journal) != _normalize_title(canonical.journal):
            # 약어 vs 풀네임 동등 처리 (간단 heuristic: 유사도 기반)
            sim_j = title_similarity(ref.journal, canonical.journal)
            if sim_j < 0.70:
                diffs["journal"] = (ref.journal, canonical.journal)

    if ref.doi and canonical.doi and ref.doi.lower() != canonical.doi.lower():
        diffs["doi"] = (ref.doi, canonical.doi)

    if ref.volume and canonical.volume and ref.volume != canonical.volume:
        diffs["volume"] = (ref.volume, canonical.volume)

    if ref.pages and canonical.pages and ref.pages != canonical.pages:
        diffs["pages"] = (ref.pages, canonical.pages)

    status: Literal["verified", "metadata_error"]
    status = "verified" if not diffs else "metadata_error"
    return MatchResult(status=status, field_diffs=diffs, title_sim=sim, preprint_vs_published=preprint_flag)
