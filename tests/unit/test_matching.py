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


def test_authors_match_overlap():
    a1 = [Author(family="Potenza"), Author(family="Balodis")]
    a2 = [Author(family="Potenza"), Author(family="Kober"), Author(family="Balodis")]
    assert authors_match(a1, a2) is True


def test_authors_mismatch_no_overlap():
    a1 = [Author(family="Smith")]
    a2 = [Author(family="Jones")]
    assert authors_match(a1, a2) is False


def test_authors_match_first_author_swap():
    """첫 저자만 다르고 나머지 겹쳐도 통과 (인용에서 저자 순서 바뀐 경우)."""
    a1 = [Author(family="Kim"), Author(family="Lee")]
    a2 = [Author(family="Lee"), Author(family="Kim")]
    assert authors_match(a1, a2) is True


def test_authors_match_partial_overlap():
    """첫 저자 다르지만 다른 저자 한 명이라도 겹치면 통과."""
    a1 = [Author(family="WrongFirst"), Author(family="Potenza")]
    a2 = [Author(family="Potenza"), Author(family="Balodis")]
    assert authors_match(a1, a2) is True


def test_title_similarity_ignores_smart_quotes():
    a = "Children's outcomes — a study"
    b = "Children's outcomes - a study"
    assert title_similarity(a, b) >= 0.95


def test_title_similarity_ignores_em_dash_vs_hyphen():
    a = "Effects of dopamine—a review"
    b = "Effects of dopamine-a review"
    assert title_similarity(a, b) >= 0.95


def test_title_similarity_handles_smart_double_quotes():
    a = "The “gold standard” trial"
    b = 'The "gold standard" trial'
    assert title_similarity(a, b) >= 0.95


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
    assert result.diff_severities.get("year") == "info"


# ---------------------------------------------------------------------------
# Severity classification — what gets flagged and at what level
# ---------------------------------------------------------------------------

def _ref(*, title="T", authors=("Smith",), year=2020, journal=None, doi=None,
         volume=None, issue=None, pages=None):
    return Reference(
        id="r", authors=[Author(family=a) for a in authors], year=year,
        title=title, journal=journal, doi=doi,
        volume=volume, issue=issue, pages=pages,
        raw_text="raw", style_detected="APA",
    )


def test_doi_mismatch_is_critical():
    a = _ref(doi="10.1/a")
    b = _ref(doi="10.1/b")
    r = compare_metadata(a, b)
    assert r.diff_severities.get("doi") == "critical"


def test_authors_no_overlap_is_critical():
    a = _ref(authors=("Smith",))
    b = _ref(authors=("Jones",))
    r = compare_metadata(a, b)
    assert r.diff_severities.get("authors") == "critical"


def test_year_off_by_two_is_major():
    a = _ref(year=2018, title="Same paper", authors=("Smith",))
    b = _ref(year=2020, title="Same paper", authors=("Smith",))
    r = compare_metadata(a, b)
    assert r.diff_severities.get("year") == "major"


def test_year_off_by_one_with_match_is_info():
    """1년 차이 + 저자·제목 일치 = preprint vs published, info-level."""
    a = _ref(year=2019, title="Same paper", authors=("Smith",))
    b = _ref(year=2020, title="Same paper", authors=("Smith",))
    r = compare_metadata(a, b)
    assert r.diff_severities.get("year") == "info"
    assert r.preprint_vs_published is True


def test_journal_abbreviation_not_flagged():
    """약어 vs 풀네임은 같은 저널 — 절대 flag되면 안 됨."""
    a = _ref(journal="Biol Psychiatry")
    b = _ref(journal="Biological Psychiatry")
    r = compare_metadata(a, b)
    assert "journal" not in r.field_diffs


def test_journal_completely_different_is_major():
    a = _ref(journal="Lancet Psychiatry")
    b = _ref(journal="Bird Quarterly")
    r = compare_metadata(a, b)
    assert r.diff_severities.get("journal") == "major"


def test_volume_issue_pages_flagged_as_minor():
    a = _ref(volume="10", issue="1", pages="100-110")
    b = _ref(volume="20", issue="3", pages="200-210")
    r = compare_metadata(a, b)
    assert r.diff_severities.get("volume") == "minor"
    assert r.diff_severities.get("issue") == "minor"
    assert r.diff_severities.get("pages") == "minor"


def test_pages_short_form_not_flagged():
    """'660-7' should match '660-667' — common citation style abbreviation."""
    a = _ref(pages="660-7")
    b = _ref(pages="660-667")
    r = compare_metadata(a, b)
    assert "pages" not in r.field_diffs


def test_minor_title_typos_not_flagged():
    """타이틀이 거의 같으면 (sim ≥ 0.75) 차이로 안 잡음."""
    a = _ref(title="Neurobiology of Gambling Behaviors")
    b = _ref(title="Neurobiology of gambling behaviors")
    r = compare_metadata(a, b)
    assert "title" not in r.field_diffs


def test_substantially_different_title_is_major():
    a = _ref(title="Adolescent gambling and depression")
    b = _ref(title="Quantum chromodynamics in particle physics")
    r = compare_metadata(a, b)
    assert r.diff_severities.get("title") == "major"
