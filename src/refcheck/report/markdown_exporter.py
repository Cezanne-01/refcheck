from __future__ import annotations
from refcheck.schema.models import DraftReport, Finding


CATEGORY_ICONS = {
    "hallucination": "🔴 환각 의심",
    "metadata": "🟠 메타데이터 오류",
    "content_mismatch": "🟡 인용 내용 불일치",
    "weak_context": "🟢 맥락 약함",
    "partial_verified": "⚪ 부분 검증",
    "paywalled": "🔒 접근 불가",
    "unverifiable": "❓ 확인 불가",
    "citation_unmatched": "⚠️ 고아 인용",
}


def export_markdown(report: DraftReport) -> str:
    m = report.metadata
    lines: list[str] = []
    lines.append("# 참고문헌 검증 리포트\n")
    lines.append(f"- **문서**: {m.draft_title}")
    lines.append(f"- **처리 시간**: {m.processing_seconds:.1f}초")
    lines.append(f"- **비용**: ${m.total_usd_cost:.3f}")
    lines.append(f"- **검증 레벨**: {m.verification_level}\n")

    lines.append("## ⚠️ 이 리포트는 **보조 도구**입니다\n")
    lines.append(
        "모든 판정은 LLM·API 출력이며 오판 가능성이 있습니다. "
        "🟡/🟢/⚪/❓/🔒 항목은 사용자 최종 확인이 필수입니다.\n"
    )

    lines.append("## 요약\n")
    for k, v in report.summary_counts.items():
        lines.append(f"- `{k}`: {v}")
    lines.append("")

    if report.unverified_manual_review:
        lines.append("## 수동 확인 권장 참고문헌\n")
        for ref_id in report.unverified_manual_review:
            lines.append(f"- {ref_id}")
        lines.append("")

    lines.append("## 발견된 문제\n")
    if not report.findings:
        lines.append("문제 없음. ✅\n")
    else:
        for idx, f in enumerate(report.findings, start=1):
            lines.extend(_render_finding(idx, f))

    return "\n".join(lines)


def _render_finding(idx: int, f: Finding) -> list[str]:
    icon = CATEGORY_ICONS.get(f.category, f.category)
    out = [f"### Finding #{idx} — {icon}"]
    out.append(f"- **유형**: {f.error_type or '-'}")
    out.append(f"- **심각도**: {'●' * f.severity}{'○' * (5 - f.severity)}")
    out.append(f"- **신뢰도**: {f.confidence}")
    out.append(f"- **Citation ID**: {f.citation_id}")
    out.append(f"- **Reference ID**: {f.reference_id}")
    out.append("")
    out.append("**초안 인용 부분:**")
    out.append(f"> {f.draft_claim_quote}")
    out.append("")
    if f.source_evidence_quote:
        out.append("**원문 근거:**")
        out.append(f"> {f.source_evidence_quote}")
        out.append("")
    out.append(f"**설명:** {f.explanation}")
    if f.suggestion:
        out.append(f"**제안:** {f.suggestion}")
    out.append("")
    return out
