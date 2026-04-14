from refcheck.verify.evidence_validator import quote_exists_in_source


def test_exact_quote_found():
    source = "Gambling disorder is characterized by persistent patterns."
    assert quote_exists_in_source("characterized by persistent patterns", source) is True


def test_quote_with_whitespace_differences_found():
    source = "Gambling disorder\n\nis   characterized by persistent."
    assert quote_exists_in_source("is characterized by persistent", source) is True


def test_quote_not_in_source():
    source = "Gambling disorder."
    assert quote_exists_in_source("schizophrenia treatment", source) is False


def test_empty_quote_returns_true():
    # 빈 문자열은 "증거 없음"이므로 True (검증 통과, low confidence로 처리)
    assert quote_exists_in_source("", "any source") is True


def test_empty_source_with_nonempty_quote_returns_false():
    assert quote_exists_in_source("something", "") is False
