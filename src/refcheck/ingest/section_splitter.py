from __future__ import annotations
import re


HEADINGS = [
    "References", "REFERENCES",
    "Bibliography", "BIBLIOGRAPHY",
    "참고문헌", "참고 문헌", "인용문헌",
    "문헌", "Literature Cited",
]


class SectionSplitError(Exception):
    pass


def split_body_and_references(text: str) -> tuple[str, str]:
    """본문과 참고문헌 섹션을 분리. 헤딩은 양쪽 모두에서 제거."""
    # 헤딩을 단독 줄로 등장 (앞뒤 개행 또는 문서 시작/끝)
    pattern = r"(?m)^\s*(?:{})\s*:?\s*$".format("|".join(re.escape(h) for h in HEADINGS))
    matches = list(re.finditer(pattern, text, re.IGNORECASE))

    if not matches:
        raise SectionSplitError(
            "참고문헌 섹션 헤딩을 찾을 수 없습니다. "
            "'References', '참고문헌', 'Bibliography' 등이 단독 줄로 있는지 확인하세요."
        )

    # 보통 마지막 등장이 실제 참고문헌 섹션 (Introduction에서 언급된 'references' 같은 본문 단어와 구분)
    last = matches[-1]
    body = text[: last.start()].strip()
    refs = text[last.end():].strip()

    if not refs:
        raise SectionSplitError("참고문헌 섹션이 비어있습니다.")

    return body, refs
