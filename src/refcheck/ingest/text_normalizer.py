from __future__ import annotations
import re
import unicodedata


LIGATURES = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬆ": "st", "ﬅ": "ft",
}


def normalize_text(text: str) -> str:
    """NFC 정규화 + ligature 복원 + 하이픈 줄바꿈 제거 + 공백 압축."""
    # 1. NFC
    text = unicodedata.normalize("NFC", text)
    # 2. Ligatures
    for lig, rep in LIGATURES.items():
        text = text.replace(lig, rep)
    # 3. PDF 줄바꿈으로 깨진 단어: "word-\nword" → "wordword"
    text = re.sub(r"-\n(\w)", r"\1", text)
    # 4. 여러 줄바꿈은 단락 경계(\n\n)로만 보존
    text = re.sub(r"\n{3,}", "\n\n", text)
    # 5. 단일 줄바꿈(단락 내부)은 공백으로
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
    # 6. 연속 공백 압축
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()
