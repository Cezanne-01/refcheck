from __future__ import annotations
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from refcheck.schema.models import DraftReport, ReportMetadata
from refcheck.ingest.text_normalizer import normalize_text
from refcheck.ingest.section_splitter import split_body_and_references
from refcheck.extract.reference_parser import parse_references
from refcheck.extract.citation_extractor import extract_citations
from refcheck.extract.linker import check_orphans
from refcheck.verify.metadata import verify_all_references
from refcheck.fetch.source_fetcher import fetch_sources
from refcheck.verify.content import verify_all_content
from refcheck.verify.agent_metadata import verify_all_references_agent
from refcheck.verify.agent_content import verify_all_content_agent
from refcheck.report.aggregator import build_draft_report
from refcheck.llm.client import LLMClient
from refcheck.fetch.crossref import CrossrefClient
from refcheck.fetch.openalex import OpenAlexClient
from refcheck.fetch.semantic_scholar import SemanticScholarClient
from refcheck.fetch.pubmed import PubMedClient
from refcheck.fetch.unpaywall import UnpaywallClient
from refcheck.ui.progress import ProgressReporter, Stage


MODEL_MAP = {
    # 사용자 계정에서 확인된 모델만 기본값으로 사용.
    # gpt-5.4-thinking / gpt-5.4-pro는 일부 계정에서 접근 불가 — 404 방지를 위해 gpt-5.4로 폴백.
    "fast":    {"extract": "gpt-5.4-mini", "content": "gpt-5.4-mini"},
    "precise": {"extract": "gpt-5.4-mini", "content": "gpt-5.4"},
    "ultra":   {"extract": "gpt-5.4",      "content": "gpt-5.4"},
}


@dataclass
class PipelineConfig:
    cache_dir: Path
    verification_level: Literal["fast", "precise", "ultra"] = "precise"
    concurrency: int = 5
    max_references: int = 200
    warn_references: int = 100
    use_agents: bool = False
    agent_max_turns: int = 6


async def run_pipeline(
    *,
    draft_text: str,
    draft_title: str,
    config: PipelineConfig,
    llm: LLMClient,
    crossref: CrossrefClient,
    openalex: OpenAlexClient,
    semantic_scholar: SemanticScholarClient,
    pubmed: PubMedClient,
    unpaywall: UnpaywallClient,
    progress: ProgressReporter | None = None,
) -> DraftReport:
    start = time.time()
    models = MODEL_MAP[config.verification_level]
    reporter = progress or ProgressReporter()  # no-op if absent

    reporter.start(Stage.INGEST, total=1, message="본문 정규화")
    text = normalize_text(draft_text)
    body, refs_raw = split_body_and_references(text)
    reporter.finish(Stage.INGEST)

    reporter.start(Stage.EXTRACT, total=2, message="참고문헌·인용 추출")
    references = await parse_references(refs_raw, llm=llm, model=models["extract"])

    if len(references) == 0:
        raise ValueError(
            "참고문헌이 감지되지 않았습니다. 초안이 참고문헌 섹션을 포함하는지 확인하세요."
        )
    if len(references) > config.max_references:
        raise ValueError(
            f"참고문헌 수가 제한을 초과했습니다 ({len(references)} > {config.max_references}). "
            "초안을 분할하거나 --max-references 옵션으로 상한을 조정하세요."
        )
    if len(references) > config.warn_references:
        import warnings
        warnings.warn(
            f"참고문헌 수가 많습니다 ({len(references)} > {config.warn_references}). "
            "검증 시간·비용이 증가할 수 있습니다.",
            UserWarning,
            stacklevel=2,
        )

    reporter.update(Stage.EXTRACT, current=1, message=f"{len(references)}개 참고문헌 파싱됨")
    citations = await extract_citations(body, references, llm=llm, model=models["extract"])
    reporter.finish(Stage.EXTRACT, message=f"{len(citations)}개 인용 추출됨")

    orphan_cits, orphan_refs = check_orphans(citations, references)

    reporter.start(Stage.VERIFY_METADATA, total=len(references), message="4개 DB에서 메타데이터 검증")
    if config.use_agents:
        openai_raw = llm._client  # type: ignore[attr-defined]
        verified = await verify_all_references_agent(
            references,
            openai_client=openai_raw,
            crossref=crossref, openalex=openalex,
            semantic_scholar=semantic_scholar, pubmed=pubmed,
            model=models["content"],
            max_turns=config.agent_max_turns,
            concurrency=min(3, config.concurrency),
        )
    else:
        verified = await verify_all_references(
            references,
            crossref=crossref, openalex=openalex,
            semantic_scholar=semantic_scholar, pubmed=pubmed,
            concurrency=config.concurrency,
        )
    reporter.finish(Stage.VERIFY_METADATA)

    reporter.start(Stage.FETCH_SOURCES, total=len(verified), message="전문·초록 확보")
    verified = await fetch_sources(
        verified, unpaywall=unpaywall,
        cache_dir=config.cache_dir,
        concurrency=config.concurrency,
    )
    reporter.finish(Stage.FETCH_SOURCES)

    reporter.start(Stage.VERIFY_CONTENT, total=len(citations), message="LLM으로 인용 내용 검증")
    if config.use_agents:
        openai_raw = llm._client  # type: ignore[attr-defined]
        findings = await verify_all_content_agent(
            citations, verified,
            openai_client=openai_raw,
            unpaywall=unpaywall, openalex=openalex,
            model=models["content"],
            max_turns=config.agent_max_turns,
            concurrency=min(3, config.concurrency),
        )
    else:
        findings = await verify_all_content(
            citations, verified, llm=llm,
            model=models["content"],
            concurrency=config.concurrency,
        )
    reporter.finish(Stage.VERIFY_CONTENT, message=f"{len(findings)}개 발견사항")

    reporter.start(Stage.AGGREGATE, total=1)
    elapsed = time.time() - start
    metadata = ReportMetadata(
        draft_title=draft_title,
        processing_seconds=elapsed,
        total_usd_cost=llm.total_cost_usd,
        verification_level=config.verification_level,
    )
    report = build_draft_report(
        verified_refs=verified,
        content_findings=findings,
        citations=citations,
        orphan_citations=orphan_cits,
        orphan_references=orphan_refs,
        metadata=metadata,
    )
    reporter.finish(Stage.AGGREGATE)
    return report
