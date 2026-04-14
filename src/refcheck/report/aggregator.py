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
                if vref.preprint_vs_published:
                    # 저자·제목 일치하는데 연도 1년 차이 → preprint/published 구분 (informational)
                    findings.append(Finding(
                        id=f"find_preprint_{cit.id}",
                        citation_id=cit.id,
                        reference_id=rid,
                        category="metadata",
                        error_type="preprint_vs_published",
                        severity=1,
                        confidence="high",
                        draft_claim_quote=cit.containing_sentence,
                        source_evidence_quote=None,
                        explanation=(
                            f"원본 저자·제목과 일치하나 인용 연도가 1년 차이 ({diff_str}). "
                            "일반적으로 preprint vs 공식 출판 연도 혼동. 공식 출판 연도 사용 권장."
                        ),
                        suggestion="공식 출판 연도로 교체.",
                    ))
                else:
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

        # ⚪ partial_verified: 초록만으로 검증된 경우 informational finding
        if vref.status in ("verified", "metadata_error") and vref.access_level == "abstract_only":
            for cit in related_cits or [_dummy_cit(rid)]:
                findings.append(Finding(
                    id=f"find_partial_{cit.id}",
                    citation_id=cit.id,
                    reference_id=rid,
                    category="partial_verified",
                    error_type="abstract_only",
                    severity=1,
                    confidence="low",
                    draft_claim_quote=cit.containing_sentence,
                    source_evidence_quote=None,
                    explanation=(
                        "원문 전문 접근 불가. 초록만으로 내용 검증됨. "
                        "주장이 논문 주 결론이 아닌 경우 초록에서 확인 어려울 수 있음 — 수동 확인 권장."
                    ),
                    suggestion="중요한 인용이면 원문 전문 직접 확인.",
                ))

    # 본문에서 인용되지 않은 참고문헌 (고아 reference)
    for ref_id in orphan_references:
        findings.append(Finding(
            id=f"find_orphan_ref_{ref_id}",
            citation_id="",
            reference_id=ref_id,
            category="citation_unmatched",
            error_type="orphan_reference",
            severity=2,
            confidence="high",
            draft_claim_quote="",
            source_evidence_quote=None,
            explanation="참고문헌 목록에 존재하나 본문 어디서도 인용되지 않음.",
            suggestion="본문에서 인용 추가 또는 참고문헌 목록에서 삭제.",
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
