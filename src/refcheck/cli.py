from __future__ import annotations
import argparse
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from refcheck.pipeline import run_pipeline, PipelineConfig
from refcheck.ingest.pdf_reader import read_pdf, PDFReadError
from refcheck.ingest.section_splitter import SectionSplitError
from refcheck.llm.client import LLMClient
from refcheck.fetch.crossref import CrossrefClient
from refcheck.fetch.openalex import OpenAlexClient
from refcheck.fetch.semantic_scholar import SemanticScholarClient
from refcheck.fetch.pubmed import PubMedClient
from refcheck.fetch.unpaywall import UnpaywallClient
from refcheck.report.json_exporter import export_json
from refcheck.report.markdown_exporter import export_markdown


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="refcheck", description="참고문헌 검증 도구")
    parser.add_argument("--input", "-i", required=True, type=Path, help="초안 PDF 또는 .txt 파일")
    parser.add_argument("--output", "-o", type=Path, default=Path("./refcheck_report"),
                        help="출력 기본 경로 (.json, .md 자동 생성)")
    parser.add_argument("--level", "-l", choices=["fast", "precise", "ultra"],
                        default="precise", help="검증 레벨")
    parser.add_argument("--cache-dir", type=Path, default=Path("./.cache"),
                        help="API 응답 캐시 디렉토리")
    args = parser.parse_args()

    if not args.input.exists():
        print(f"ERROR: 입력 파일을 찾을 수 없습니다: {args.input}", file=sys.stderr)
        sys.exit(2)

    try:
        if args.input.suffix.lower() == ".pdf":
            draft_text = read_pdf(args.input)
        else:
            draft_text = args.input.read_text(encoding="utf-8")
    except PDFReadError as e:
        print(f"ERROR: PDF 읽기 실패 — {e}", file=sys.stderr)
        sys.exit(3)
    except UnicodeDecodeError as e:
        print(f"ERROR: 텍스트 파일 인코딩 문제 (UTF-8이어야 합니다) — {e}", file=sys.stderr)
        sys.exit(3)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY 환경변수가 필요합니다.", file=sys.stderr)
        sys.exit(2)

    unpaywall_email = os.getenv("UNPAYWALL_EMAIL")
    if not unpaywall_email:
        print("WARN: UNPAYWALL_EMAIL 미설정. OA PDF 자동 다운로드 스킵됨.", file=sys.stderr)

    llm = LLMClient(api_key=api_key)
    ua_suffix = f" (mailto:{unpaywall_email})" if unpaywall_email else ""
    crossref = CrossrefClient(user_agent=f"refcheck/0.1{ua_suffix}")
    openalex = OpenAlexClient(mailto=unpaywall_email)
    semantic = SemanticScholarClient(api_key=os.getenv("SEMANTIC_SCHOLAR_API_KEY") or None)
    pubmed = PubMedClient()
    unpaywall = UnpaywallClient(email=unpaywall_email)

    config = PipelineConfig(cache_dir=args.cache_dir, verification_level=args.level)

    async def _run():
        try:
            report = await run_pipeline(
                draft_text=draft_text,
                draft_title=args.input.name,
                config=config,
                llm=llm,
                crossref=crossref,
                openalex=openalex,
                semantic_scholar=semantic,
                pubmed=pubmed,
                unpaywall=unpaywall,
            )
        finally:
            await crossref.close()
            await openalex.close()
            await semantic.close()
            await pubmed.close()
            await unpaywall.close()
        return report

    try:
        report = asyncio.run(_run())
    except SectionSplitError as e:
        print(f"ERROR: 참고문헌 섹션 분리 실패 — {e}", file=sys.stderr)
        sys.exit(4)
    except ValueError as e:
        # e.g. reference-count guard from pipeline
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(5)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    json_path = args.output.with_suffix(".json")
    md_path = args.output.with_suffix(".md")
    json_path.write_text(export_json(report), encoding="utf-8")
    md_path.write_text(export_markdown(report), encoding="utf-8")

    print(f"✅ 리포트 생성 완료")
    print(f"  - JSON: {json_path}")
    print(f"  - Markdown: {md_path}")
    print(f"  - 처리 시간: {report.metadata.processing_seconds:.1f}초")
    print(f"  - 총 비용: ${report.metadata.total_usd_cost:.3f}")
    print(f"  - 발견된 문제: {report.summary_counts.get('findings_total', 0)}건")
