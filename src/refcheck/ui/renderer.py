from __future__ import annotations
from collections import defaultdict
from typing import Any
from refcheck.schema.models import DraftReport, Finding


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


def render_findings(report: DraftReport, *, st: Any) -> None:
    """Findings를 심각도별로 그룹화, expander로 표시."""
    st.subheader(f"발견된 문제 ({len(report.findings)}건)")

    if not report.findings:
        st.success("문제 없음. ✅")
        return

    grouped: dict[int, list[Finding]] = defaultdict(list)
    for f in report.findings:
        grouped[f.severity].append(f)

    for sev in sorted(grouped.keys(), reverse=True):
        st.markdown(f"### {SEVERITY_LABEL.get(sev, sev)} — {len(grouped[sev])}건")
        for idx, f in enumerate(grouped[sev], start=1):
            label = (
                f"{CATEGORY_LABELS.get(f.category, f.category)} — "
                f"{f.error_type or '-'} · 신뢰도: {f.confidence}"
            )
            with st.expander(label, expanded=(sev >= 4 and idx == 1)):
                _render_finding_body(f, st=st)


def _render_finding_body(f: Finding, *, st: Any) -> None:
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
