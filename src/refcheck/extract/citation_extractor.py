from __future__ import annotations
import re
from pathlib import Path
from refcheck.schema.models import Citation, Reference
from refcheck.llm.client import LLMClient


_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "citation_extractor.md"


# LLM은 가벼운 필드만 뽑게 한다 (id/surface/ref_ids/char_offset).
# 문장·단락은 본문에서 char_offset 기반으로 직접 계산 — 출력 30K+chars 폭증
# (containing_sentence/surrounding_paragraph)이 timeout 원인이라 분리.
CITATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["citations"],
    "properties": {
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "surface", "ref_ids", "char_offset"],
                "properties": {
                    "id": {"type": "string"},
                    "surface": {"type": "string"},
                    "ref_ids": {"type": "array", "items": {"type": "string"}},
                    "char_offset": {"type": "integer"},
                },
            },
        },
    },
}


def _refs_summary(refs: list[Reference]) -> str:
    """LLM에게 참고문헌 ID 매핑을 보여주기 위한 요약."""
    lines = []
    for r in refs:
        authors = ", ".join(a.family for a in r.authors)
        lines.append(f"{r.id}: {authors} ({r.year}) — {r.title[:80]}")
    return "\n".join(lines)


_SENTENCE_END = re.compile(r"[.!?。！？]\s")


def _containing_sentence(body: str, offset: int) -> str:
    """offset 위치를 포함하는 문장. sentence-end punctuation 기준."""
    if not 0 <= offset <= len(body):
        return ""
    # 왼쪽으로 sentence-end 또는 문단 시작까지
    start = 0
    for m in _SENTENCE_END.finditer(body, 0, offset):
        start = m.end()
    # 오른쪽으로 sentence-end 또는 문단 끝까지
    end_match = _SENTENCE_END.search(body, offset)
    end = end_match.end() if end_match else len(body)
    return body[start:end].strip()


def _surrounding_paragraph(body: str, offset: int) -> str:
    """offset 위치를 포함하는 단락. 단락 경계는 \\n\\n."""
    if not 0 <= offset <= len(body):
        return ""
    start = body.rfind("\n\n", 0, offset)
    start = 0 if start == -1 else start + 2
    end = body.find("\n\n", offset)
    end = len(body) if end == -1 else end
    return body[start:end].strip()


async def extract_citations(
    body_text: str,
    references: list[Reference],
    *,
    llm: LLMClient,
    model: str = "gpt-5.4",
) -> list[Citation]:
    system = _PROMPT_PATH.read_text(encoding="utf-8")
    user = (
        "REFERENCES:\n"
        f"{_refs_summary(references)}\n\n"
        "BODY TEXT:\n"
        f"{body_text}"
    )
    # temperature=0 — exhaustive 추출은 결정성이 중요.
    result, _ = await llm.complete_json(
        model=model,
        system=system,
        user=user,
        response_schema=CITATION_SCHEMA,
        temperature=0.0,
    )

    cits: list[Citation] = []
    for idx, item in enumerate(result["citations"], start=1):
        offset = _verify_offset(body_text, item["surface"], item["char_offset"])
        cits.append(Citation(
            id=item["id"] or f"cit_{idx:04d}",
            surface=item["surface"],
            ref_ids=item["ref_ids"],
            char_offset=offset,
            containing_sentence=_containing_sentence(body_text, offset),
            surrounding_paragraph=_surrounding_paragraph(body_text, offset),
        ))
    return cits


def _verify_offset(body: str, surface: str, claimed: int) -> int:
    """LLM이 준 char_offset이 실제 surface 위치와 어긋날 수 있어 검증·보정.

    1) 주어진 offset에 surface가 있으면 그대로 사용.
    2) 없으면 body 내 surface 첫 등장 위치로 fallback.
    3) surface 자체를 못 찾으면(파싱 실수) claimed 그대로 둔다 — sentence 추출은
       어차피 가까운 위치 텍스트라 큰 손해 없음.
    """
    if 0 <= claimed <= len(body) and body[claimed : claimed + len(surface)] == surface:
        return claimed
    found = body.find(surface)
    return found if found != -1 else max(0, min(claimed, len(body)))
