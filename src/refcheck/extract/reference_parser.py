from __future__ import annotations
from pathlib import Path
from refcheck.schema.models import Reference, Author
from refcheck.llm.client import LLMClient


_PROMPT_PATH = Path(__file__).parent.parent / "llm" / "prompts" / "reference_parser.md"


REFERENCE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["references"],
    "properties": {
        "references": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id", "authors", "year", "title", "journal",
                    "volume", "issue", "pages", "doi", "raw_text", "style_detected"
                ],
                "properties": {
                    "id": {"type": "string"},
                    "authors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["given", "family"],
                            "properties": {
                                "given": {"type": ["string", "null"]},
                                "family": {"type": "string"},
                            },
                        },
                    },
                    "year": {"type": ["integer", "null"]},
                    "title": {"type": "string"},
                    "journal": {"type": ["string", "null"]},
                    "volume": {"type": ["string", "null"]},
                    "issue": {"type": ["string", "null"]},
                    "pages": {"type": ["string", "null"]},
                    "doi": {"type": ["string", "null"]},
                    "raw_text": {"type": "string"},
                    "style_detected": {
                        "type": "string",
                        "enum": ["APA", "Vancouver", "Nature", "Chicago", "IEEE", "unknown"],
                    },
                },
            },
        },
    },
}


async def parse_references(
    raw_refs_text: str,
    *,
    llm: LLMClient,
    model: str = "gpt-5.4-mini",
) -> list[Reference]:
    system = _PROMPT_PATH.read_text(encoding="utf-8")
    result, _ = await llm.complete_json(
        model=model,
        system=system,
        user=raw_refs_text,
        response_schema=REFERENCE_SCHEMA,
        temperature=0.0,
    )

    refs: list[Reference] = []
    for idx, item in enumerate(result["references"], start=1):
        item_id = item["id"] or f"ref_{idx:03d}"
        refs.append(Reference(
            id=item_id,
            authors=[Author(**a) for a in item["authors"]],
            year=item["year"],
            title=item["title"],
            journal=item["journal"],
            volume=item["volume"],
            issue=item["issue"],
            pages=item["pages"],
            doi=item["doi"],
            raw_text=item["raw_text"],
            style_detected=item["style_detected"],
        ))
    return refs
