"""citation_extractor의 sentence/paragraph 도출 + offset 검증 헬퍼 테스트.

LLM은 offset 정수만 반환하고 문장·단락은 본문에서 직접 계산한다 (출력 폭증 방지).
헬퍼들이 잘못된 offset에도 견고하게 동작해야 한다.
"""
from refcheck.extract.citation_extractor import (
    _containing_sentence,
    _surrounding_paragraph,
    _verify_offset,
)


def test_containing_sentence_basic():
    body = "First sentence. Second sentence with citation. Third sentence."
    offset = body.find("citation")
    sent = _containing_sentence(body, offset)
    assert sent == "Second sentence with citation."


def test_containing_sentence_korean():
    body = "첫 문장입니다. 인용은 여기 (Smith, 2020) 있습니다. 다음 문장."
    offset = body.find("(Smith")
    sent = _containing_sentence(body, offset)
    assert "(Smith, 2020)" in sent
    assert "다음 문장" not in sent


def test_containing_sentence_at_start():
    body = "Citation at start (Smith, 2020). Then more."
    offset = body.find("(Smith")
    sent = _containing_sentence(body, offset)
    assert sent.startswith("Citation at start")


def test_surrounding_paragraph_picks_correct_block():
    body = "Para A line.\n\nPara B with (Smith, 2020) cite.\n\nPara C."
    offset = body.find("(Smith")
    para = _surrounding_paragraph(body, offset)
    assert para == "Para B with (Smith, 2020) cite."


def test_verify_offset_correct():
    body = "Hello (Smith, 2020) world"
    surface = "(Smith, 2020)"
    correct = body.find(surface)
    assert _verify_offset(body, surface, correct) == correct


def test_verify_offset_off_by_a_few_falls_back_to_search():
    body = "Hello (Smith, 2020) world"
    surface = "(Smith, 2020)"
    # LLM이 잘못된 offset을 줘도 surface로 검색해 정확한 위치 회복
    assert _verify_offset(body, surface, claimed=0) == body.find(surface)
    assert _verify_offset(body, surface, claimed=999) == body.find(surface)


def test_verify_offset_surface_not_in_body_keeps_claimed():
    body = "Hello world"
    # surface 자체가 본문에 없으면 (LLM 환각) claimed를 boundary clamp만 해서 사용
    assert _verify_offset(body, "(NotHere, 2020)", claimed=5) == 5
    assert _verify_offset(body, "(NotHere, 2020)", claimed=999) == len(body)
