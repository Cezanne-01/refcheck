from __future__ import annotations
from collections import defaultdict
from typing import Any
from refcheck.schema.models import DraftReport, Finding, VerifiedReference


CATEGORY_LABELS = {
    "hallucination": "🔴 환각 의심",
    "metadata": "🟠 메타데이터 오류",
    "content_mismatch": "🟡 인용 내용 불일치",
    "weak_context": "🟢 맥락 약함",
    "partial_verified": "⚪ 부분 검증",
    "paywalled": "🔒 접근 불가",
    "unverifiable": "❓ 확인 불가",
    "citation_unmatched": "⚠️ 고아 인용",
}

SEVERITY_LABEL = {5: "Critical", 4: "Major", 3: "Moderate", 2: "Minor", 1: "Info"}

STATUS_ICON = {
    "verified": "✅",
    "hallucination": "🔴",
    "metadata_error": "🟠",
    "unverifiable": "❓",
}

ACCESS_ICON = {
    "full_text": "📄 전문 확인",
    "abstract_only": "⚪ 초록만",
    "paywalled": "🔒 접근 불가",
    "not_found": "❌ 전문 없음",
}


def render_summary(report: DraftReport, *, st: Any) -> None:
    """상단 요약 대시보드 — 주요 지표 4개 + 카테고리별 카운트."""
    st.subheader("요약")

    cols = st.columns(4)
    cols[0].metric("처리 시간", f"{report.metadata.processing_seconds:.1f}초")
    cols[1].metric("총 비용", f"${report.metadata.total_usd_cost:.3f}")
    cols[2].metric("발견사항", report.summary_counts.get("findings_total", 0))
    cols[3].metric("검증 레벨", report.metadata.verification_level)

    st.markdown("**카테고리별 분포**")
    count_cols = st.columns(min(4, max(1, len(report.summary_counts))))
    for i, (k, v) in enumerate(report.summary_counts.items()):
        count_cols[i % len(count_cols)].metric(k, v)


def _format_reference_title(vref: VerifiedReference) -> tuple[str, str, str]:
    """Return (authors_line, title, journal_line)."""
    r = vref.canonical or vref.reference
    if r.authors:
        names = [a.family for a in r.authors[:3]]
        authors_str = ", ".join(names)
        if len(r.authors) > 3:
            authors_str += " et al."
    else:
        authors_str = "(저자 없음)"
    year_str = f" ({r.year})" if r.year else ""
    authors_line = f"**{authors_str}{year_str}**"

    title = r.title or "(제목 없음)"

    journal_parts = []
    if r.journal:
        journal_parts.append(f"_{r.journal}_")
    if r.volume:
        journal_parts.append(f"{r.volume}" + (f"({r.issue})" if r.issue else ""))
    if r.pages:
        journal_parts.append(f"pp. {r.pages}")
    if r.doi:
        journal_parts.append(f"DOI: `{r.doi}`")
    journal_line = ", ".join(journal_parts)

    return authors_line, title, journal_line


def render_findings(report: DraftReport, *, st: Any) -> None:
    """문제 발견사항을 **참고문헌별로 그룹화**하여 표시.

    각 그룹은 논문 메타데이터(저자·연도·제목·저널)를 헤더로 하고,
    그 아래에 해당 논문에 대한 모든 findings을 심각도 내림차순으로 나열.
    """
    if not report.findings:
        st.subheader("발견된 문제")
        st.success("문제 없음. ✅")
        return

    ref_by_id: dict[str, VerifiedReference] = {
        v.reference.id: v for v in report.references
    }

    # Group by reference_id (empty string = orphan citation)
    grouped: dict[str, list[Finding]] = defaultdict(list)
    orphan_citation_findings: list[Finding] = []
    for f in report.findings:
        if f.reference_id and f.reference_id in ref_by_id:
            grouped[f.reference_id].append(f)
        else:
            orphan_citation_findings.append(f)

    st.subheader(
        f"발견된 문제 ({len(report.findings)}건, {len(grouped)}개 참고문헌에서)"
    )
    st.caption(
        "심각한 문제가 많은 논문부터 순서대로 표시됩니다. "
        "각 논문의 문제들은 심각도 내림차순으로 정렬됩니다."
    )

    # Sort groups by (max severity DESC, count DESC)
    ordered = sorted(
        grouped.items(),
        key=lambda kv: (-max(f.severity for f in kv[1]), -len(kv[1])),
    )

    for idx, (ref_id, findings) in enumerate(ordered, start=1):
        vref = ref_by_id[ref_id]
        _render_reference_group(
            idx=idx,
            vref=vref,
            findings=findings,
            st=st,
        )

    if orphan_citation_findings:
        st.markdown("---")
        st.markdown("### ⚠️ 본문에서 인용되었으나 참고문헌 매칭 실패")
        st.caption(
            "아래 인용들은 참고문헌 목록에서 해당하는 논문을 찾지 못했습니다. "
            "참고문헌을 추가하거나 인용을 수정하세요."
        )
        for f in orphan_citation_findings:
            label = (
                f"{CATEGORY_LABELS.get(f.category, f.category)} — "
                f"{f.error_type or '-'}"
            )
            with st.expander(label, expanded=False):
                _render_finding_body(f, show_ids=True, st=st)


def _render_reference_group(
    *,
    idx: int,
    vref: VerifiedReference,
    findings: list[Finding],
    st: Any,
) -> None:
    """단일 참고문헌에 대한 헤더 + 그 아래의 findings 목록."""
    authors_line, title, journal_line = _format_reference_title(vref)

    status_icon = STATUS_ICON.get(vref.status, "")
    access_icon = ACCESS_ICON.get(vref.access_level, "")
    max_sev = max(f.severity for f in findings)
    sev_dots = "●" * max_sev + "○" * (5 - max_sev)

    # Group header
    st.markdown("---")
    st.markdown(f"### #{idx}. {status_icon} {authors_line}")
    st.markdown(f"**『{title}』**")
    if journal_line:
        st.caption(journal_line)

    badges = []
    badges.append(f"{status_icon} {vref.status}")
    if access_icon:
        badges.append(access_icon)
    badges.append(f"최대 심각도 {sev_dots}")
    badges.append(f"{len(findings)}건 발견")
    st.caption(" · ".join(badges))

    # Findings sorted by severity DESC
    findings_sorted = sorted(findings, key=lambda f: -f.severity)
    for fi_idx, f in enumerate(findings_sorted, start=1):
        label = (
            f"{CATEGORY_LABELS.get(f.category, f.category)} — "
            f"{f.error_type or '-'} · "
            f"{'●' * f.severity}{'○' * (5 - f.severity)} · "
            f"신뢰도 {f.confidence}"
        )
        # Expand the first (most severe) finding of high-severity papers
        expanded = max_sev >= 4 and fi_idx == 1
        with st.expander(label, expanded=expanded):
            _render_finding_body(f, show_ids=False, st=st)


def _render_finding_body(f: Finding, *, show_ids: bool = False, st: Any) -> None:
    cols = st.columns(2)
    cols[0].markdown("**초안 인용**")
    cols[0].markdown(f"> {f.draft_claim_quote}")
    if f.source_evidence_quote:
        cols[1].markdown("**원문 근거**")
        cols[1].markdown(f"> {f.source_evidence_quote}")
    else:
        cols[1].markdown("**원문 근거**")
        cols[1].caption("_(제시된 근거 없음)_")

    st.markdown(f"**설명:** {f.explanation}")
    if f.suggestion:
        st.info(f"💡 **제안**: {f.suggestion}")

    if show_ids:
        st.caption(f"Citation: `{f.citation_id}` · Reference: `{f.reference_id}`")


def render_report(report: DraftReport, *, st: Any) -> None:
    """전체 리포트 렌더. UI 최상단에서 호출."""
    st.title("📚 검증 리포트")
    st.caption(f"**문서:** {report.metadata.draft_title}")

    st.warning(
        "⚠️ **이 리포트는 보조 도구입니다.** 모든 판정은 LLM·API 출력이며 오판 가능성이 있습니다. "
        "🟡/🟢/⚪/❓/🔒 항목은 최종 사용자 확인이 필수입니다."
    )

    render_summary(report, st=st)

    if report.unverified_manual_review:
        with st.expander(f"수동 확인 권장 참고문헌 ({len(report.unverified_manual_review)}개)"):
            for rid in report.unverified_manual_review:
                st.markdown(f"- `{rid}`")

    render_findings(report, st=st)
