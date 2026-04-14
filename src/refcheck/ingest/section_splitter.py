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
    """본문과 참고문헌 섹션을 분리. 헤딩은 양쪽 모두에서 제거.

    지원하는 헤딩 형식 (단독 줄, 양끝 whitespace 허용):
    - `References`
    - `참고문헌`
    - `참고문헌 (References)` — 괄호 안 영어 번역 병기
    - `References (참고문헌)` — 반대 순서도 허용
    - 숫자 섹션 번호 (`8. References`, `VI. 참고문헌`) 허용
    - 끝에 콜론 허용 (`References:`)
    """
    heading_alt = "|".join(re.escape(h) for h in HEADINGS)
    # 1) optional 섹션 번호 (e.g. "8.", "VI.", "IX. ")
    # 2) 헤딩 본체
    # 3) optional 괄호 안 번역 병기 (e.g. " (References)")
    # 4) optional trailing colon
    pattern = (
        r"(?m)^\s*"
        r"(?:[IVXLCDM\d]+\s*[.)]\s*)?"  # section number prefix
        r"(?:" + heading_alt + r")"
        r"(?:\s*\(\s*(?:" + heading_alt + r")\s*\))?"  # parenthesized alt
        r"\s*:?\s*$"
    )
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
