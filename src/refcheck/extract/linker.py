from __future__ import annotations
from refcheck.schema.models import Reference, Citation


def check_orphans(
    citations: list[Citation],
    references: list[Reference],
) -> tuple[list[str], list[str]]:
    """고아 citation과 고아 reference의 ID 리스트 반환."""
    orphan_citations = [c.id for c in citations if not c.ref_ids]

    used_ref_ids: set[str] = set()
    for c in citations:
        used_ref_ids.update(c.ref_ids)

    orphan_references = [r.id for r in references if r.id not in used_ref_ids]

    return orphan_citations, orphan_references
