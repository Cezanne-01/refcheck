from __future__ import annotations
from collections import Counter
from refcheck.schema.models import (
    VerifiedReference, Citation, Finding, DraftReport, ReportMetadata,
)


def build_draft_report(
    *,
    verified_refs: list[VerifiedReference],
    content_findings: list[Finding],
    citations: list[Citation],
    orphan_citations: list[str],
    orphan_references: list[str],
    metadata: ReportMetadata,
) -> DraftReport:
    findings: list[Finding] = []

    citations_by_ref: dict[str, list[Citation]] = {}
    for c in citations:
        for rid in c.ref_ids:
            citations_by_ref.setdefault(rid, []).append(c)

    for vref in verified_refs:
        rid = vref.reference.id
        related_cits = citations_by_ref.get(rid, [])
        if vref.status == "hallucination":
            for cit in related_cits or [_dummy_cit(rid)]:
                findings.append(Finding(
                    id=f"find_hall_{cit.id}",
                    citation_id=cit.id,
                    reference_id=rid,
                    category="hallucination",
                    error_type="fabricated_reference",
                    severity=5,
                    confidence="high",
                    draft_claim_quote=cit.containing_sentence,
                    source_evidence_quote=None,
                    explanation=(
                        f"참고문헌 '{vref.reference.raw_text[:80]}...'을 "
                        f"{len(vref.sources_checked)}개 DB에서 찾을 수 없습니다. 환각 의심."
                    ),
                    suggestion="해당 논문 존재 여부 직접 확인 후 삭제 또는 올바른 출처로 교체.",
                ))
        elif vref.status == "metadata_error":
            for cit in related_cits or [_dummy_cit(rid)]:
                diff_str = ", ".join(f"{k}: '{v[0]}' → '{v[1]}'" for k, v in vref.field_diffs.items())
                findings.append(Finding(
                    id=f"find_meta_{cit.id}",
                    citation_id=cit.id,
                    reference_id=rid,
                    category="metadata",
                    error_type="field_mismatch",
                    severity=3,
                    confidence="high",
                    draft_claim_quote=cit.containing_sentence,
                    source_evidence_quote=None,
                    explanation=f"메타데이터 불일치: {diff_str}",
                    suggestion="정확한 메타데이터로 교체.",
                ))

    for cit_id in orphan_citations:
        findings.append(Finding(
            id=f"find_orphan_cit_{cit_id}",
            citation_id=cit_id,
            reference_id="",
            category="citation_unmatched",
            error_type="orphan_citation",
            severity=3,
            confidence="high",
            draft_claim_quote="",
            source_evidence_quote=None,
            explanation="본문에서 인용되었으나 참고문헌 목록에 해당 항목 없음.",
            suggestion="참고문헌 추가 또는 인용 삭제.",
        ))

    findings.extend(content_findings)

    conf_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: (-f.severity, conf_order.get(f.confidence, 3)))

    counts: Counter = Counter()
    for v in verified_refs:
        counts[v.status] += 1
    for v in verified_refs:
        counts[f"access_{v.access_level}"] += 1
    counts["orphan_citations"] = len(orphan_citations)
    counts["orphan_references"] = len(orphan_references)
    counts["findings_total"] = len(findings)

    manual = [
        v.reference.id for v in verified_refs
        if v.status == "unverifiable" or v.access_level == "paywalled"
    ]

    return DraftReport(
        metadata=metadata,
        summary_counts=dict(counts),
        findings=findings,
        references=verified_refs,
        unverified_manual_review=manual,
    )


def _dummy_cit(ref_id: str) -> Citation:
    return Citation(
        id=f"cit_unused_{ref_id}",
        surface="",
        ref_ids=[ref_id],
        char_offset=-1,
        containing_sentence="(참고문헌에만 존재, 본문 인용 없음)",
        surrounding_paragraph="",
    )
