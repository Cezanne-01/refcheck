"""Streamlit renderer for the verification report.

Layout: one card per reference. Card contents in priority order:
  1. Status banner (verified / metadata error / hallucination / unverifiable)
  2. One-line summary of what is wrong (if anything)
  3. Side-by-side diff table when canonical metadata exists
  4. Up to 2 deduped content findings with the actual evidence
The goal is "what should the writer do?" not "every difference my code can detect".
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any
from refcheck.schema.models import DraftReport, Finding, VerifiedReference


# Status → human label and color (used in the card banner)
_STATUS_DISPLAY: dict[str, tuple[str, str]] = {
    "verified":         ("✅ 검증됨",         "#2e7d32"),
    "metadata_error":   ("🟠 메타데이터 오류", "#ef6c00"),
    "hallucination":    ("🔴 환각 의심",      "#c62828"),
    "unverifiable":     ("❓ 확인 불가",      "#6a1b9a"),
}

_SEVERITY_COLOR: dict[str, str] = {
    "critical": "#c62828",
    "major":    "#ef6c00",
    "minor":    "#9e9e9e",
    "info":     "#1976d2",
}

_FIELD_LABEL: dict[str, str] = {
    "title":    "제목",
    "authors":  "저자",
    "year":     "연도",
    "journal":  "저널",
    "doi":      "DOI",
    "volume":   "권(volume)",
    "issue":    "호(issue)",
    "pages":    "페이지",
}


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

def render_report(report: DraftReport, *, st: Any) -> None:
    st.title("📚 검증 리포트")
    st.caption(f"**문서:** {report.metadata.draft_title}")
    st.warning(
        "⚠️ **이 리포트는 보조 도구입니다.** 모든 판정은 LLM·API 출력이며 오판 가능성이 있습니다. "
        "🟡/🟢/⚪/❓/🔒 항목은 최종 사용자 확인이 필수입니다."
    )
    _render_summary(report, st=st)
    _render_reference_cards(report, st=st)


def _render_summary(report: DraftReport, *, st: Any) -> None:
    """Top dashboard. 4 headline metrics, then a single-line breakdown by status."""
    st.subheader("요약")

    # Roll up status counts from the verified_refs (more useful than the
    # raw `summary_counts` dict which mixes statuses and access levels).
    status_counts: dict[str, int] = defaultdict(int)
    for v in report.references:
        status_counts[v.status] += 1

    n_refs = len(report.references)
    n_problems = sum(
        1 for v in report.references if v.status in {"metadata_error", "hallucination", "unverifiable"}
    )

    cols = st.columns(4)
    cols[0].metric("총 참고문헌", n_refs)
    cols[1].metric("문제 있음", n_problems)
    cols[2].metric("처리 시간", f"{report.metadata.processing_seconds:.1f}초")
    cols[3].metric("총 비용", f"${report.metadata.total_usd_cost:.3f}")

    parts: list[str] = []
    for status, (label, color) in _STATUS_DISPLAY.items():
        count = status_counts.get(status, 0)
        if count:
            parts.append(f"<span style='color:{color}'>{label} {count}</span>")
    if parts:
        st.markdown(" · ".join(parts), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Per-reference card
# ---------------------------------------------------------------------------

def _render_reference_cards(report: DraftReport, *, st: Any) -> None:
    """Sort refs by problem severity and render one card per ref."""
    findings_by_ref: dict[str, list[Finding]] = defaultdict(list)
    orphan_findings: list[Finding] = []
    for f in report.findings:
        if f.reference_id and any(v.reference.id == f.reference_id for v in report.references):
            findings_by_ref[f.reference_id].append(f)
        else:
            orphan_findings.append(f)

    # Order: hallucination > metadata_error > unverifiable > verified-with-content-finding > verified
    order_key = {
        "hallucination": 0,
        "metadata_error": 1,
        "unverifiable": 2,
        "verified": 3,
    }

    refs_sorted = sorted(
        report.references,
        key=lambda v: (
            order_key.get(v.status, 99),
            -max([f.severity for f in findings_by_ref.get(v.reference.id, [])] or [0]),
            v.reference.id,
        ),
    )

    # A ref is a "real problem" if its status is non-verified OR it has at
    # least one substantive finding (severity ≥ 3). Info-only findings like
    # partial_verified (verified-via-abstract-only) and orphan_reference
    # don't count — they're advisory, not errors.
    def _has_real_problem(v: VerifiedReference, findings: list[Finding]) -> bool:
        if v.status in ("hallucination", "metadata_error", "unverifiable"):
            return True
        return any(f.severity >= 3 for f in findings)

    n_problem_refs = sum(
        1 for v in refs_sorted
        if _has_real_problem(v, findings_by_ref.get(v.reference.id, []))
    )
    st.subheader(f"참고문헌별 검증 결과 ({n_problem_refs}/{len(refs_sorted)} 문제 있음)")
    st.caption(
        "문제가 있는 항목부터 위에 표시됩니다. "
        "(전문 미확보 같은 정보성 항목은 카운트에서 제외)"
    )

    for idx, vref in enumerate(refs_sorted, start=1):
        _render_card(idx, vref, findings_by_ref.get(vref.reference.id, []), st=st)

    if orphan_findings:
        st.markdown("---")
        st.markdown("### ⚠️ 본문에서 인용되었으나 참고문헌 매칭 실패")
        for f in orphan_findings:
            with st.expander(f.error_type or "고아 인용", expanded=False):
                st.markdown(f.explanation)
                if f.suggestion:
                    st.info(f"💡 {f.suggestion}")


def _render_card(
    idx: int,
    vref: VerifiedReference,
    findings: list[Finding],
    *,
    st: Any,
) -> None:
    user_ref = vref.reference
    canonical = vref.canonical

    # Status banner
    label, color = _STATUS_DISPLAY.get(vref.status, (vref.status, "#666"))
    st.markdown("---")
    st.markdown(
        f"### #{idx}. <span style='color:{color}'>{label}</span> — {_short_ref_line(user_ref)}",
        unsafe_allow_html=True,
    )

    # One-line summary
    summary = _verdict_summary(vref, findings)
    if summary:
        st.markdown(f"**{summary}**")

    # The user's original raw citation (so they can locate it in their draft)
    if user_ref.raw_text:
        st.caption(f"원문 그대로: _{user_ref.raw_text.strip()[:300]}_")

    # Diff table — but for `unverifiable` status, the canonical may be a
    # *different* paper that just happens to share the first author. Frame
    # it as a candidate the user should review, not as authoritative.
    if vref.field_diffs and canonical is not None:
        if vref.status == "unverifiable":
            st.caption(
                "⚠️ 아래는 검색에서 가장 가까운 후보지만 실제 인용한 논문이 아닐 수 있습니다. "
                "같은 저자의 다른 논문일 가능성이 있어 직접 확인이 필요합니다."
            )
        _render_diff_table(vref, st=st)

    # Content findings (deduped already by aggregator). Cap at 2 visible.
    # Skip for unverifiable refs — the content agent ran against a candidate
    # that may not be the user's actual cited paper, so the verdict is unreliable.
    all_content = (
        [] if vref.status == "unverifiable"
        else [f for f in findings if f.category == "content_mismatch"]
    )
    visible_content = all_content[:2]
    extra_count = len(all_content) - len(visible_content)
    if visible_content:
        header = f"📝 인용 내용 검증 결과 ({len(all_content)}건)"
        with st.expander(header, expanded=True):
            for f in visible_content:
                _render_content_finding(f, st=st)
            if extra_count > 0:
                st.caption(
                    f"… 비슷한 발견 {extra_count}건 추가 — 상위 2건만 표시. "
                    "전체는 JSON 다운로드에서 확인 가능."
                )

    # Hallucination explainer (if status is hallucination)
    if vref.status == "hallucination":
        st.error(
            "이 참고문헌은 4개 학술 DB와 웹 검색에서 모두 찾을 수 없어 LLM이 생성한 가짜 인용일 가능성이 높습니다. "
            "직접 확인 후 삭제하거나 올바른 출처로 교체하세요."
        )


def _render_diff_table(vref: VerifiedReference, *, st: Any) -> None:
    """Side-by-side: 사용자 인용 vs 실제 논문, only flagged fields."""
    # Order rows by severity (critical first)
    order = {"critical": 0, "major": 1, "minor": 2, "info": 3}
    rows = sorted(
        vref.field_diffs.items(),
        key=lambda kv: order.get(vref.diff_severities.get(kv[0], "minor"), 9),
    )

    rendered: list[str] = []
    rendered.append(
        "<table style='width:100%; border-collapse:collapse;'>"
        "<tr style='background:#f5f5f5'>"
        "<th style='text-align:left; padding:6px; width:90px'>필드</th>"
        "<th style='text-align:left; padding:6px'>사용자 인용</th>"
        "<th style='text-align:left; padding:6px'>실제 논문</th>"
        "</tr>"
    )
    for field_name, (user_val, canonical_val) in rows:
        sev = vref.diff_severities.get(field_name, "minor")
        sev_color = _SEVERITY_COLOR.get(sev, "#666")
        label = _FIELD_LABEL.get(field_name, field_name)
        rendered.append(
            "<tr style='border-top:1px solid #eee'>"
            f"<td style='padding:6px; color:{sev_color}; font-weight:600'>● {label}</td>"
            f"<td style='padding:6px; color:#c62828'>{_html_escape(user_val) or '<em>(없음)</em>'}</td>"
            f"<td style='padding:6px; color:#2e7d32'>{_html_escape(canonical_val) or '<em>(없음)</em>'}</td>"
            "</tr>"
        )
    rendered.append("</table>")
    st.markdown("".join(rendered), unsafe_allow_html=True)


def _render_content_finding(f: Finding, *, st: Any) -> None:
    sev_dots = "●" * f.severity + "○" * (5 - f.severity)
    st.markdown(
        f"**{f.error_type or '내용 불일치'}** · "
        f"<span style='color:#c62828'>{sev_dots}</span> · 신뢰도 {f.confidence}",
        unsafe_allow_html=True,
    )
    # Side-by-side: 초안 인용 (left, red tone) vs 원문 근거 (right, green tone)
    left, right = st.columns(2)
    with left:
        st.markdown("**초안 인용**")
        if f.draft_claim_quote:
            st.markdown(
                f"<div style='background:#fff3f3; padding:0.5em 0.7em; "
                f"border-radius:4px; border-left:3px solid #c62828; "
                f"color:#333; font-size:0.92em'>{f.draft_claim_quote}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("_(인용 문장 없음)_")
    with right:
        st.markdown("**원문 근거**")
        if f.source_evidence_quote:
            st.markdown(
                f"<div style='background:#f1f8e9; padding:0.5em 0.7em; "
                f"border-radius:4px; border-left:3px solid #2e7d32; "
                f"color:#333; font-size:0.92em'>{f.source_evidence_quote}</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("_(원문에서 근거 인용 못 찾음)_")

    if f.explanation:
        st.markdown(f"**설명:** {f.explanation}")
    if f.suggestion:
        st.info(f"💡 **제안:** {f.suggestion}")
    st.markdown("")  # spacer between findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short_ref_line(ref: Any) -> str:
    """One-line: '저자 et al. (연도) — 제목'"""
    if ref.authors:
        names = [a.family for a in ref.authors[:2]]
        author_str = " & ".join(names)
        if len(ref.authors) > 2:
            author_str += " et al."
    else:
        author_str = "(저자 없음)"
    year_str = f" ({ref.year})" if ref.year else ""
    title = ref.title or "(제목 없음)"
    return f"**{author_str}{year_str}** — _{title[:120]}_"


def _verdict_summary(vref: VerifiedReference, findings: list[Finding]) -> str:
    """One-line plain-Korean summary: what's wrong with this ref?"""
    if vref.status == "hallucination":
        return "❌ 4개 DB와 웹 검색에서 찾을 수 없음 — 가짜 인용 의심"
    if vref.status == "unverifiable":
        return "❓ 확인 불가 — 수동 검증 권장"
    if vref.status == "metadata_error":
        critical = [k for k, sev in vref.diff_severities.items() if sev == "critical"]
        major = [k for k, sev in vref.diff_severities.items() if sev == "major"]
        info = [k for k, sev in vref.diff_severities.items() if sev == "info"]
        if vref.preprint_vs_published:
            return "ℹ️ 1년 차이 (preprint vs 공식 출판) — 공식 출판 연도 권장"
        if critical:
            return f"❌ 중요한 메타데이터 오류: {', '.join(_FIELD_LABEL.get(k, k) for k in critical)}"
        if major:
            return f"⚠️ 메타데이터 차이: {', '.join(_FIELD_LABEL.get(k, k) for k in major)}"
        if info:
            return f"ℹ️ 사소한 차이: {', '.join(_FIELD_LABEL.get(k, k) for k in info)}"
    if vref.status == "verified":
        n_content = sum(1 for f in findings if f.category == "content_mismatch")
        if n_content:
            return f"⚠️ 메타데이터는 정확하나 인용 내용에 문제가 있을 수 있습니다 ({n_content}건)"
        return "✅ 메타데이터·인용 내용 모두 검증됨"
    return ""


def _html_escape(s: Any) -> str:
    """Safe escape for the HTML diff table."""
    if s is None:
        return ""
    s = str(s)
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
