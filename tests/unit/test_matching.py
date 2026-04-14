from refcheck.verify.matching import (
    title_similarity, authors_match, compare_metadata,
    MatchResult,
)
from refcheck.schema.models import Reference, Author


def test_title_similarity_exact():
    assert title_similarity("The Neurobiology of Gambling",
                            "The Neurobiology of Gambling") >= 0.99


def test_title_similarity_near():
    s = title_similarity(
        "Anticipatory reward processing in addicted populations",
        "Anticipatory Reward Processing in Addicted Populations: A Focus on the Monetary Incentive Delay Task",
    )
    assert 0.60 <= s <= 0.90  # 부분 매칭


def test_title_similarity_different():
    assert title_similarity("Gambling neurobiology",
                            "Schizophrenia treatment") < 0.40


def test_authors_match_first_author_required():
    a1 = [Author(family="Potenza"), Author(family="Balodis")]
    a2 = [Author(family="Potenza"), Author(family="Kober"), Author(family="Balodis")]
    assert authors_match(a1, a2) is True  # 첫 저자 일치 + 부분집합


def test_authors_mismatch_different_first():
    a1 = [Author(family="Smith")]
    a2 = [Author(family="Jones")]
    assert authors_match(a1, a2) is False


def test_compare_metadata_all_match():
    ref = Reference(id="r1", authors=[Author(family="Potenza")], year=2013,
                    title="Neurobiology of gambling", journal="J Neuro",
                    raw_text="...", style_detected="APA")
    canonical = Reference(id="r1", authors=[Author(family="Potenza")], year=2013,
                          title="Neurobiology of gambling", journal="J Neuro",
                          raw_text="...", style_detected="APA")
    result = compare_metadata(ref, canonical)
    assert result.status == "verified"
    assert result.field_diffs == {}


def test_compare_metadata_year_mismatch():
    ref = Reference(id="r1", authors=[Author(family="Potenza")], year=2013,
                    title="Neurobiology of gambling", raw_text="...", style_detected="APA")
    canonical = Reference(id="r1", authors=[Author(family="Potenza")], year=2014,
                          title="Neurobiology of gambling", raw_text="...", style_detected="APA")
    result = compare_metadata(ref, canonical)
    assert result.status == "metadata_error"
    assert "year" in result.field_diffs


def test_compare_metadata_preprint_vs_published():
    # 저자·제목 일치, 연도 1년 차이 — 정보성 finding
    ref = Reference(id="r1", authors=[Author(family="Potenza")], year=2012,
                    title="Neurobiology of gambling", raw_text="...", style_detected="APA")
    canonical = Reference(id="r1", authors=[Author(family="Potenza")], year=2013,
                          title="Neurobiology of gambling", raw_text="...", style_detected="APA")
    result = compare_metadata(ref, canonical)
    assert result.status == "metadata_error"
    assert result.preprint_vs_published is True
