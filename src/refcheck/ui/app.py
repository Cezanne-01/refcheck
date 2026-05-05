"""Streamlit entry point for refcheck."""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from refcheck.pipeline import PipelineConfig, run_pipeline
from refcheck.llm.client import LLMClient
from refcheck.fetch.crossref import CrossrefClient
from refcheck.fetch.openalex import OpenAlexClient
from refcheck.fetch.semantic_scholar import SemanticScholarClient
from refcheck.fetch.pubmed import PubMedClient
from refcheck.fetch.unpaywall import UnpaywallClient
from refcheck.fetch.web_search import WebSearchClient
from refcheck.fetch.full_text import FullTextFetcher
from refcheck.schema.models import DraftReport
from refcheck.ui.progress import ProgressReporter, ProgressEvent, Stage
from refcheck.ui.widgets import render_upload, render_config, check_env_readiness
from refcheck.ui.renderer import render_report


load_dotenv()


def _hydrate_env_from_streamlit_secrets() -> None:
    """Copy Streamlit secrets into ``os.environ`` so existing ``os.getenv``
    code paths work on Streamlit Cloud without code changes.

    Local dev typically uses a ``.env`` file (loaded above by ``load_dotenv``).
    Streamlit Cloud has no ``.env`` — secrets are configured via the dashboard
    and exposed through ``st.secrets``. We iterate ``st.secrets`` and copy
    any string values into the environment when not already set.

    Errors (no secrets.toml locally, etc.) are silently ignored — local dev
    falls back to ``.env`` and Streamlit Cloud sets secrets via dashboard.
    """
    try:
        for key, value in st.secrets.items():  # type: ignore[attr-defined]
            if isinstance(value, str) and not os.getenv(key):
                os.environ[key] = value
    except Exception:
        pass


_hydrate_env_from_streamlit_secrets()


def main() -> None:
    st.set_page_config(page_title="refcheck", layout="wide", page_icon="📚")
    st.title("📚 refcheck — 참고문헌 검증")
    st.caption("LLM이 작성한 학술 문서 초안의 참고문헌·인용을 검증합니다.")

    # Session state
    if "report" not in st.session_state:
        st.session_state.report = None

    # 1. Env check
    if not check_env_readiness(st):
        return

    # 2. Upload + config
    col_up, col_cfg = st.columns([3, 2])
    with col_up:
        upload = render_upload(st)
    with col_cfg:
        config = render_config(st)

    # 3. Run button
    if upload is not None:
        st.success(f"✅ 업로드됨: **{upload.filename}** ({len(upload.draft_text):,}자)")
        if st.button("🚀 검증 시작", type="primary", use_container_width=True):
            _run_pipeline_with_progress(upload, config)

    # 4. Report display
    if st.session_state.report is not None:
        st.divider()
        render_report(st.session_state.report, st=st)

        # 5. Download buttons
        _render_download_buttons(st.session_state.report)


def _run_pipeline_with_progress(upload: Any, config: Any) -> None:
    """Pipeline을 동기적으로 실행하며 st.status로 진행 상황 표시."""
    with st.status("검증 중...", expanded=True) as status:
        stage_placeholders: dict[Stage, Any] = {}
        progress_bars: dict[Stage, Any] = {}

        def _on_event(event: ProgressEvent) -> None:
            if event.stage not in stage_placeholders:
                stage_placeholders[event.stage] = st.empty()
                progress_bars[event.stage] = st.progress(0, text=event.stage.label)
            ratio = (event.current / event.total) if event.total else 0.0
            label = f"**{event.stage.label}** — {event.current}/{event.total}"
            if event.message:
                label += f" · {event.message}"
            stage_placeholders[event.stage].markdown(label)
            progress_bars[event.stage].progress(ratio, text=event.stage.label)

        reporter = ProgressReporter(callback=_on_event)
        try:
            report = asyncio.run(_execute_pipeline(upload, config, reporter))
            st.session_state.report = report
            status.update(label="✅ 검증 완료", state="complete", expanded=False)
        except ValueError as e:
            status.update(label="❌ 검증 실패", state="error")
            st.error(str(e))
        except Exception as e:
            from refcheck.ingest.section_splitter import SectionSplitError
            status.update(label="❌ 검증 실패", state="error")
            if isinstance(e, SectionSplitError):
                st.error(f"{e}")
                st.info(
                    "팁: 참고문헌 섹션 헤딩을 단독 줄로 두세요. "
                    "예: `참고문헌`, `References`, `참고문헌 (References)`, `8. References` 등이 지원됩니다."
                )
            else:
                st.exception(e)


async def _execute_pipeline(upload: Any, config: Any, reporter: ProgressReporter) -> DraftReport:
    unpaywall_email = os.getenv("UNPAYWALL_EMAIL")

    llm = LLMClient(api_key=os.getenv("OPENAI_API_KEY"))
    ua_suffix = f" (mailto:{unpaywall_email})" if unpaywall_email else ""
    crossref = CrossrefClient(user_agent=f"refcheck/0.1{ua_suffix}")
    openalex = OpenAlexClient(mailto=unpaywall_email)
    semantic = SemanticScholarClient(api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY") or None)
    pubmed = PubMedClient()
    unpaywall = UnpaywallClient(email=unpaywall_email)
    web_search = WebSearchClient()
    full_text_fetcher = FullTextFetcher(unpaywall=unpaywall)

    try:
        report = await run_pipeline(
            draft_text=upload.draft_text,
            draft_title=upload.filename,
            config=PipelineConfig(
                cache_dir=config.cache_dir,
                verification_level=config.verification_level,
            ),
            llm=llm,
            crossref=crossref,
            openalex=openalex,
            semantic_scholar=semantic,
            pubmed=pubmed,
            web_search=web_search,
            full_text_fetcher=full_text_fetcher,
            progress=reporter,
        )
    finally:
        await crossref.close()
        await openalex.close()
        await semantic.close()
        await pubmed.close()
        await unpaywall.close()
        await web_search.close()
        await full_text_fetcher.close()
    return report


def _render_download_buttons(report: DraftReport) -> None:
    from refcheck.report.json_exporter import export_json

    st.subheader("📥 리포트 다운로드")
    cols = st.columns(2)

    base = Path(report.metadata.draft_title).stem or "report"

    cols[0].download_button(
        "JSON (구조화 데이터)",
        data=export_json(report),
        file_name=f"{base}.refcheck.json",
        mime="application/json",
        use_container_width=True,
    )

    pdf_bytes = _try_export_pdf(report)
    if pdf_bytes is not None:
        cols[1].download_button(
            "PDF (가독성 좋은 리포트)",
            data=pdf_bytes,
            file_name=f"{base}.refcheck.pdf",
            mime="application/pdf",
            use_container_width=True,
            type="primary",
        )
    else:
        with cols[1]:
            st.button("PDF (사용 불가)", disabled=True, use_container_width=True,
                      help="weasyprint 시스템 deps 설치 필요: brew install cairo pango gdk-pixbuf libffi")


def _try_export_pdf(report: DraftReport) -> bytes | None:
    from refcheck.report.pdf_exporter import export_pdf, PDFExportError
    try:
        return export_pdf(report)
    except PDFExportError:
        return None


if __name__ == "__main__":
    main()
