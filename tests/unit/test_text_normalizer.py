from refcheck.ingest.text_normalizer import normalize_text


def test_removes_ligatures():
    assert normalize_text("eﬃcacy") == "efficacy"
    assert normalize_text("ﬁnal") == "final"


def test_collapses_whitespace():
    assert normalize_text("hello  \t  world") == "hello world"


def test_removes_soft_hyphen_breaks():
    # PDF 줄바꿈: "neurobio-\nlogical" → "neurobiological"
    assert normalize_text("neurobio-\nlogical") == "neurobiological"


def test_preserves_paragraph_breaks():
    text = "Para 1.\n\nPara 2."
    result = normalize_text(text)
    assert "\n\n" in result


def test_nfc_normalization():
    # NFD (결합 문자) → NFC
    nfd = "한" + chr(0x1100) + chr(0x1161) + chr(0x11AB)  # 간
    result = normalize_text(nfd)
    assert "한" in result


def test_recovers_parens_from_null_byte_pairs():
    """일부 PDF는 괄호 글리프 ToUnicode 매핑이 없어 '\\x00X\\x00' 형태로 흘림.
    숫자 주변 괄호가 이 형태이므로 (X)로 복원해야 LLM이 인용을 정상 파싱."""
    assert normalize_text("Potenza \x002013\x00") == "Potenza (2013)"
    assert normalize_text("vol \x0077\x00, p. \x005\x00") == "vol (77), p. (5)"


def test_strips_unpaired_null_bytes():
    """짝이 안 맞는 \\x00은 그냥 제거."""
    assert normalize_text("foo\x00bar") == "foobar"


def test_protects_reference_heading_line():
    """헤딩이 단일 줄바꿈으로만 둘러싸인 경우, 단락 경계로 승격되어야 함.

    그렇지 않으면 normalizer 5단계에서 헤딩이 본문/참고문헌과 한 줄로 합쳐져
    section_splitter가 매치 실패함."""
    text = "본문 끝.\nReferences\nSmith, J. (2020). Foo."
    result = normalize_text(text)
    # heading은 paragraph break으로 분리돼야 함
    assert "\n\nReferences\n\n" in result or "\nReferences\n" in result


def test_strips_utf8_bom():
    """Windows에서 저장된 .txt는 UTF-8 BOM (\\ufeff)으로 시작하기도 함."""
    assert normalize_text("﻿본문") == "본문"


def test_normalizes_crlf_line_endings():
    """Streamlit decode 경로(getvalue().decode)는 universal newlines를 적용 안 하므로
    \\r\\n이 그대로 남는다 — splitter regex가 깨지지 않게 LF로 통일."""
    from refcheck.ingest.section_splitter import split_body_and_references

    text = "본문 끝.\r\n\r\n참고문헌 (References)\r\nSmith, J. (2020). Foo.\r\n"
    body, refs = split_body_and_references(normalize_text(text))
    assert "본문 끝" in body
    assert "Smith, J. (2020)" in refs
    # \r 잔재 없음
    assert "\r" not in body and "\r" not in refs


def test_normalize_then_split_recovers_split_parenthesized_heading():
    """PDF 추출에서 '(References)\\n참고문헌'처럼 두 줄로 쪼개진 헤딩이
    normalize_text → split_body_and_references 파이프라인을 통과해야 함."""
    from refcheck.ingest.section_splitter import split_body_and_references

    text = "본문 끝.\n(References)\n참고문헌\nSmith, J. (2020). Foo."
    body, refs = split_body_and_references(normalize_text(text))
    assert "본문 끝" in body
    assert "Smith, J. (2020)" in refs
