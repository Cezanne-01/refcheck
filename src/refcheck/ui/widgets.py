from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class UploadResult:
    filename: str
    draft_text: str


@dataclass
class RunConfig:
    verification_level: str
    cache_dir: Path


def render_upload(st: Any) -> UploadResult | None:
    """파일 업로드 위젯. 반환값은 업로드 완료 시 UploadResult, 아니면 None."""
    uploaded = st.file_uploader(
        "초안 업로드 (PDF 또는 .txt)",
        type=["pdf", "txt"],
        help="LLM이 작성한 초안을 업로드하세요. 참고문헌 섹션이 포함되어야 합니다.",
    )
    if uploaded is None:
        return None

    try:
        if uploaded.name.lower().endswith(".pdf"):
            from refcheck.ingest.pdf_reader import read_pdf, PDFReadError
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(uploaded.getvalue())
                tmp_path = Path(f.name)
            try:
                text = read_pdf(tmp_path)
            except PDFReadError as e:
                st.error(f"PDF 읽기 실패: {e}")
                return None
            finally:
                tmp_path.unlink(missing_ok=True)
        else:
            try:
                text = uploaded.getvalue().decode("utf-8")
            except UnicodeDecodeError:
                st.error("텍스트 파일은 UTF-8 인코딩이어야 합니다.")
                return None
    except Exception as e:
        st.error(f"파일 처리 중 오류: {e}")
        return None

    return UploadResult(filename=uploaded.name, draft_text=text)


def render_config(st: Any) -> RunConfig:
    """검증 레벨·캐시 디렉토리 선택."""
    st.subheader("⚙️ 검증 설정")
    col1, col2 = st.columns([2, 3])
    level = col1.selectbox(
        "검증 레벨",
        options=["fast", "precise", "ultra"],
        index=1,
        help=(
            "- **fast**: 빠른 검증 (비용 ~$1~2, 2~3분)\n"
            "- **precise**: 정밀 검증 (비용 ~$3~5, 5~8분) — 기본\n"
            "- **ultra**: 초정밀 (비용 ~$8~12, 10~15분)"
        ),
    )
    cache_dir_str = col2.text_input(
        "캐시 디렉토리",
        value="./.cache",
        help="API 응답·전문 PDF 캐시 위치. 재실행 시 속도 향상.",
    )
    return RunConfig(verification_level=level, cache_dir=Path(cache_dir_str))


def check_env_readiness(st: Any) -> bool:
    """OPENAI_API_KEY 등 필수 환경변수 체크. 부재 시 에러 표시 + False 반환."""
    missing: list[str] = []
    if not os.getenv("OPENAI_API_KEY"):
        missing.append("OPENAI_API_KEY")

    if missing:
        st.error(
            f"환경변수 {', '.join(missing)}이(가) 설정되지 않았습니다. "
            "프로젝트 루트의 `.env` 파일을 확인하세요 (예시: `.env.example`)."
        )
        return False

    if not os.getenv("UNPAYWALL_EMAIL"):
        st.warning(
            "`UNPAYWALL_EMAIL`이 설정되지 않아 오픈 액세스 PDF 자동 다운로드는 스킵됩니다. "
            "메타데이터·초록 기반 검증은 정상 동작합니다."
        )
    return True
