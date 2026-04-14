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
