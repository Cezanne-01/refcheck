from __future__ import annotations
from pathlib import Path
from refcheck.schema.models import Citation, Reference
from refcheck.llm.client import LLMClient


_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "citation_extractor.md"


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
                "required": ["id", "surface", "ref_ids", "char_offset",
                             "containing_sentence", "surrounding_paragraph"],
                "properties": {
                    "id": {"type": "string"},
                    "surface": {"type": "string"},
                    "ref_ids": {"type": "array", "items": {"type": "string"}},
                    "char_offset": {"type": "integer"},
                    "containing_sentence": {"type": "string"},
                    "surrounding_paragraph": {"type": "string"},
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


async def extract_citations(
    body_text: str,
    references: list[Reference],
    *,
    llm: LLMClient,
    model: str = "gpt-5.4-mini",
) -> list[Citation]:
    system = _PROMPT_PATH.read_text(encoding="utf-8")
    user = (
        "REFERENCES:\n"
        f"{_refs_summary(references)}\n\n"
        "BODY TEXT:\n"
        f"{body_text}"
    )
    result, _ = await llm.complete_json(
        model=model,
        system=system,
        user=user,
        response_schema=CITATION_SCHEMA,
    )

    cits: list[Citation] = []
    for idx, item in enumerate(result["citations"], start=1):
        cits.append(Citation(
            id=item["id"] or f"cit_{idx:04d}",
            surface=item["surface"],
            ref_ids=item["ref_ids"],
            char_offset=item["char_offset"],
            containing_sentence=item["containing_sentence"],
            surrounding_paragraph=item["surrounding_paragraph"],
        ))
    return cits
