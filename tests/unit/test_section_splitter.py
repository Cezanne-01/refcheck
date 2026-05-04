import pytest
from refcheck.ingest.section_splitter import split_body_and_references, SectionSplitError


def test_splits_on_references_heading_english():
    text = """Introduction
Gambling is bad (Potenza, 2013).

References

Potenza, M. N. (2013). ...
Balodis, I. M. (2015). ..."""
    body, refs = split_body_and_references(text)
    assert "Gambling is bad" in body
    assert "Potenza, M. N. (2013)" in refs
    assert "References" not in body


def test_splits_on_korean_heading():
    text = """서론
도박장애는 심각하다 (Potenza, 2013).

참고문헌

Potenza, M. N. (2013). ..."""
    body, refs = split_body_and_references(text)
    assert "도박장애는 심각하다" in body
    assert "Potenza, M. N. (2013)" in refs


def test_splits_on_bibliography():
    text = "Body text.\n\nBibliography\n\nFoo (2020)."
    body, refs = split_body_and_references(text)
    assert refs.startswith("Foo")


def test_raises_when_no_heading_found():
    with pytest.raises(SectionSplitError, match="참고문헌 섹션"):
        split_body_and_references("Just some text with no references heading.")


def test_case_insensitive():
    text = "Body.\n\nREFERENCES\n\nFoo (2020)."
    body, refs = split_body_and_references(text)
    assert "Foo (2020)" in refs


def test_parenthesized_english_after_korean():
    """'참고문헌 (References)' — 한글 + 괄호 영어 병기."""
    text = "본문 내용.\n\n참고문헌 (References)\n\nSmith (2020). Paper."
    body, refs = split_body_and_references(text)
    assert "본문 내용" in body
    assert "Smith (2020)" in refs


def test_parenthesized_korean_after_english():
    """'References (참고문헌)' — 영어 + 괄호 한글 병기."""
    text = "Body.\n\nReferences (참고문헌)\n\nSmith (2020). Paper."
    body, refs = split_body_and_references(text)
    assert "Body" in body
    assert "Smith (2020)" in refs


def test_numbered_section_reference():
    """'8. References' 같은 섹션 번호 prefix."""
    text = "Body.\n\n8. References\n\nSmith (2020)."
    body, refs = split_body_and_references(text)
    assert "Smith (2020)" in refs


def test_numbered_section_korean():
    """'8. 참고문헌' 도 허용."""
    text = "본문.\n\n8. 참고문헌\n\nSmith (2020)."
    body, refs = split_body_and_references(text)
    assert "Smith (2020)" in refs
