from __future__ import annotations
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from refcheck.schema.models import DraftReport


_TEMPLATE_DIR = Path(__file__).parent.parent / "ui" / "templates"


_CATEGORY_LABELS = {
    "hallucination": "🔴 환각 의심",
    "metadata": "🟠 메타데이터 오류",
    "content_mismatch": "🟡 인용 내용 불일치",
    "weak_context": "🟢 맥락 약함",
    "partial_verified": "⚪ 부분 검증",
    "paywalled": "🔒 접근 불가",
    "unverifiable": "❓ 확인 불가",
    "citation_unmatched": "⚠️ 고아 인용",
}


def _category_label(category: str) -> str:
    return _CATEGORY_LABELS.get(category, category)


def export_html(report: DraftReport) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "htm", "j2"]),
    )
    env.globals["category_label"] = _category_label
    template = env.get_template("report.html.j2")
    return template.render(report=report)
