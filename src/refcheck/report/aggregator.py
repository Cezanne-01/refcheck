from __future__ import annotations
from collections import Counter, defaultdict
from refcheck._match import title_similarity
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
        related_cits = citations_by_ref.get(rid, []) or [_dummy_cit(rid)]
        # Metadata-derived findings (hallucination / metadata_error /
        # preprint_vs_published) describe a property of the *reference*,
        # not of a specific in-text citation. Generate ONE finding per
        # reference; pick the first citation as the navigation anchor and
        # note how many citations of this ref exist in the body.
        anchor_cit = related_cits[0]
        cit_count_note = (
            f" (본문 인용 {len(related_cits)}회)"
            if len(related_cits) > 1 else ""
        )

        if vref.status == "hallucination":
            findings.append(Finding(
                id=f"find_hall_{rid}",
                citation_id=anchor_cit.id,
                reference_id=rid,
                category="hallucination",
                error_type="fabricated_reference",
                severity=5,
                confidence="high",
                draft_claim_quote=anchor_cit.containing_sentence,
                source_evidence_quote=None,
                explanation=(
                    f"참고문헌 '{vref.reference.raw_text[:80]}...'을 "
                    f"{len(vref.sources_checked)}개 DB에서 찾을 수 없습니다. "
                    f"환각 의심.{cit_count_note}"
                ),
                suggestion="해당 논문 존재 여부 직접 확인 후 삭제 또는 올바른 출처로 교체.",
            ))
        elif vref.status == "metadata_error":
            diff_str = ", ".join(
                f"{k}: '{v[0]}' → '{v[1]}'" for k, v in vref.field_diffs.items()
            ) or "(차이 정보 없음)"
            if vref.preprint_vs_published:
                findings.append(Finding(
                    id=f"find_preprint_{rid}",
                    citation_id=anchor_cit.id,
                    reference_id=rid,
                    category="metadata",
                    error_type="preprint_vs_published",
                    severity=1,
                    confidence="high",
                    draft_claim_quote=anchor_cit.containing_sentence,
                    source_evidence_quote=None,
                    explanation=(
                        f"원본 저자·제목과 일치하나 인용 연도가 1년 차이 ({diff_str}). "
                        f"일반적으로 preprint vs 공식 출판 연도 혼동. 공식 출판 연도 사용 권장.{cit_count_note}"
                    ),
                    suggestion="공식 출판 연도로 교체.",
                ))
            else:
                findings.append(Finding(
                    id=f"find_meta_{rid}",
                    citation_id=anchor_cit.id,
                    reference_id=rid,
                    category="metadata",
                    error_type="field_mismatch",
                    severity=3,
                    confidence="high",
                    draft_claim_quote=anchor_cit.containing_sentence,
                    source_evidence_quote=None,
                    explanation=f"메타데이터 불일치: {diff_str}.{cit_count_note}",
                    suggestion="정확한 메타데이터로 교체.",
                ))

        # ⚪ partial_verified — also reference-level, one finding only
        if vref.status in ("verified", "metadata_error") and vref.access_level == "abstract_only":
            findings.append(Finding(
                id=f"find_partial_{rid}",
                citation_id=anchor_cit.id,
                reference_id=rid,
                category="partial_verified",
                error_type="abstract_only",
                severity=1,
                confidence="low",
                draft_claim_quote=anchor_cit.containing_sentence,
                source_evidence_quote=None,
                explanation=(
                    "원문 전문 접근 불가. 초록만으로 내용 검증됨. "
                    f"주장이 논문 주 결론이 아닌 경우 초록에서 확인 어려울 수 있음 — 수동 확인 권장.{cit_count_note}"
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

    # Content findings: dedupe near-identical findings on the same reference.
    # When a single ref is cited from N nearly-identical sentences, the agent
    # tends to emit N very similar findings. Keep the first; collapse the rest
    # into a "+N similar" note on the kept one.
    findings.extend(_dedupe_content_findings(content_findings))

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


# ---------------------------------------------------------------------------
# Content-finding dedupe
# ---------------------------------------------------------------------------


def _dedupe_content_findings(content_findings: list[Finding]) -> list[Finding]:
    """Collapse content findings that share a root cause on the same ref.

    Two findings are merged when they describe the same underlying issue:
    same reference, same error_type, and the same source evidence (or both
    have none). This catches the common pattern where a single bad source
    text triggers a "wrong paper" verdict on every citation of that ref —
    those are 1 root cause, not N.

    Two findings with different source quotes or different error types are
    kept separate; they represent genuinely different observations.
    """
    by_ref: dict[str, list[Finding]] = defaultdict(list)
    others: list[Finding] = []
    for f in content_findings:
        if f.reference_id:
            by_ref[f.reference_id].append(f)
        else:
            others.append(f)

    deduped: list[Finding] = list(others)
    for ref_id, group in by_ref.items():
        clusters: dict[tuple[str, str, str], list[Finding]] = {}
        for f in group:
            # Source-evidence key: first 120 chars normalised. Same source
            # text → same root cause.
            src_key = (f.source_evidence_quote or "").strip()[:120]
            cluster_key = (
                f.category,
                (f.error_type or ""),
                src_key,
            )
            clusters.setdefault(cluster_key, []).append(f)

        for cluster in clusters.values():
            head = cluster[0]
            extra = len(cluster) - 1
            if extra > 0:
                head = head.model_copy(update={
                    "explanation": (
                        f"{head.explanation} "
                        f"(같은 참고문헌에 대해 유사한 발견 {extra}건 추가 — 합쳐서 표시)"
                    ),
                })
            deduped.append(head)

    return deduped


def _dummy_cit(ref_id: str) -> Citation:
    return Citation(
        id=f"cit_unused_{ref_id}",
        surface="",
        ref_ids=[ref_id],
        char_offset=-1,
        containing_sentence="(참고문헌에만 존재, 본문 인용 없음)",
        surrounding_paragraph="",
    )
