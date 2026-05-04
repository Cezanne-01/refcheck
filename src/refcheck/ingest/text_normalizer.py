from __future__ import annotations
import re
import unicodedata


LIGATURES = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬆ": "st", "ﬅ": "ft",
}

# section_splitter의 HEADINGS와 동기화 — 여기서 줄 단위 헤딩 후보를 보호한다.
_HEADING_WORDS = [
    "References", "REFERENCES",
    "Reference", "REFERENCE",
    "Bibliography", "BIBLIOGRAPHY",
    "Works Cited", "WORKS CITED",
    "Literature Cited", "LITERATURE CITED",
    "참고문헌", "참고 문헌", "참고자료", "참고 자료", "인용문헌", "문헌",
]
_HEADING_ALT = "|".join(re.escape(h) for h in _HEADING_WORDS)
# 한 줄 헤딩: optional 섹션 번호 + 헤딩 본체 + optional 괄호 병기 + optional 콜론
_HEADING_LINE_RE = re.compile(
    r"^[ \t]*"
    r"(?:[IVXLCDM\d]+[ \t]*[.)][ \t]*)?"
    r"(?:" + _HEADING_ALT + r")"
    r"(?:[ \t]*\([ \t]*(?:" + _HEADING_ALT + r")[ \t]*\))?"
    r"[ \t]*:?[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)
# PDF가 헤딩을 두 줄로 분리한 경우: "(References)\n참고문헌" 또는 "참고문헌\n(References)"
_SPLIT_PAREN_HEADING_RE = re.compile(
    r"^[ \t]*\([ \t]*(" + _HEADING_ALT + r")[ \t]*\)[ \t]*\n"
    r"[ \t]*(" + _HEADING_ALT + r")[ \t]*$",
    re.MULTILINE | re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """NFC 정규화 + ligature 복원 + 하이픈 줄바꿈 제거 + 공백 압축.

    참고문헌 헤딩 라인은 단락 경계로 승격해 splitter가 항상 매치되도록 보장한다.
    """
    # 1. UTF-8 BOM 제거 (Windows에서 저장한 .txt에서 흔함)
    if text.startswith("﻿"):
        text = text[1:]
    # 2. 줄 끝 통일: CRLF / CR-only → LF (Streamlit decode 경로는 universal newlines 안 함)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 3. PDF 폰트 ToUnicode 매핑 누락 복원: '\x00X\x00' = '(X)'
    #    일부 PDF는 괄호 글리프가 ToUnicode에 없어 추출기가 \x00을 흘림.
    #    YYYY, 권/호, 페이지 등 숫자 주변 괄호가 이 형태로 사라지므로 복원해
    #    LLM이 인용·참고문헌 구조를 정상 파싱할 수 있게 한다.
    text = re.sub(r"\x00([^\x00]{1,30})\x00", r"(\1)", text)
    # 잔여 \x00 (홀수 개로 남거나 짝이 멀리 있는 경우) 제거
    text = text.replace("\x00", "")
    # 4. NFC
    text = unicodedata.normalize("NFC", text)
    # 5. Ligatures
    for lig, rep in LIGATURES.items():
        text = text.replace(lig, rep)
    # 6. PDF 줄바꿈으로 깨진 단어: "word-\nword" → "wordword"
    text = re.sub(r"-\n(\w)", r"\1", text)
    # 7. 분리된 괄호-병기 헤딩을 한 줄로 복원
    #    e.g. "(References)\n참고문헌" → "참고문헌 (References)"
    text = _SPLIT_PAREN_HEADING_RE.sub(
        lambda m: f"{m.group(2)} ({m.group(1)})", text
    )
    # 8. 헤딩 라인 주변을 단락 경계(\n\n)로 승격 — 다음 단계의 newline 압축으로부터 보호
    text = _HEADING_LINE_RE.sub(lambda m: f"\n\n{m.group(0).strip()}\n\n", text)
    # 9. 여러 줄바꿈은 단락 경계(\n\n)로만 보존
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 10. 단일 줄바꿈(단락 내부)은 공백으로
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    # 11. 연속 공백 압축
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()
