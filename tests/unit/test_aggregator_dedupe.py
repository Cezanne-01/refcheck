"""Tests for the dedupe/grouping behavior added to aggregator.

The original report had ~5–6 near-identical findings per problematic
reference because every in-text citation generated its own finding. The
aggregator now emits one reference-level finding plus a "+N similar"
note on duplicate content findings.
"""
from refcheck.report.aggregator import build_draft_report
from refcheck.schema.models import (
    VerifiedReference, Reference, Author, Citation, Finding, ReportMetadata,
)


def _ref(id_, title="T"):
    return Reference(
        id=id_, authors=[Author(family="X")], year=2020,
        title=title, raw_text="raw", style_detected="APA",
    )


def _meta():
    return ReportMetadata(
        draft_title="t", processing_seconds=1.0, total_usd_cost=0.1,
        verification_level="precise",
    )


def _cit(id_, ref_id, sentence="A claim."):
    return Citation(
        id=id_, surface=f"({ref_id})", ref_ids=[ref_id], char_offset=0,
        containing_sentence=sentence, surrounding_paragraph=sentence,
    )


def test_hallucination_with_three_citations_emits_one_finding():
    """A hallucinated ref cited from three sentences should produce ONE
    hallucination finding (not three)."""
    vref = VerifiedReference(
        reference=_ref("r1"), status="hallucination", canonical=None,
        access_level="not_found", sources_checked=["search_crossref", "search_pubmed"],
    )
    citations = [_cit(f"c{i}", "r1", f"Sentence {i}.") for i in range(3)]

    report = build_draft_report(
        verified_refs=[vref], content_findings=[], citations=citations,
        orphan_citations=[], orphan_references=[], metadata=_meta(),
    )
    hall = [f for f in report.findings if f.category == "hallucination"]
    assert len(hall) == 1
    # The body note should mention how many citations are affected
    assert "3" in hall[0].explanation


def test_metadata_error_with_three_citations_emits_one_finding():
    r = _ref("r1")
    vref = VerifiedReference(
        reference=r, status="metadata_error", canonical=r,
        field_diffs={"journal": ("J Wrong", "J Right")},
        access_level="full_text",
    )
    citations = [_cit(f"c{i}", "r1", f"Sentence {i}.") for i in range(3)]

    report = build_draft_report(
        verified_refs=[vref], content_findings=[], citations=citations,
        orphan_citations=[], orphan_references=[], metadata=_meta(),
    )
    meta = [f for f in report.findings if f.error_type == "field_mismatch"]
    assert len(meta) == 1
    assert "본문 인용 3회" in meta[0].explanation


def test_content_findings_dedupe_collapses_same_source_evidence():
    """Three findings on the same ref citing the same source evidence (the
    common arxiv-bug pattern: one bad source text triggers N findings)
    collapse into one with '+N similar' annotation."""
    findings_in = [
        Finding(
            id=f"f{i}", citation_id=f"c{i}", reference_id="r1",
            category="content_mismatch", error_type="wrong_paper",
            severity=5, confidence="high",
            draft_claim_quote=f"draft sentence {i}",
            source_evidence_quote="Observation of rare B-meson decay (CMS-LHCb)",
            explanation=f"agent phrasing variant {i}",
            suggestion=None,
        )
        for i in range(3)
    ]
    report = build_draft_report(
        verified_refs=[], content_findings=findings_in, citations=[],
        orphan_citations=[], orphan_references=[], metadata=_meta(),
    )
    cm = [f for f in report.findings if f.category == "content_mismatch"]
    assert len(cm) == 1
    assert "2건 추가" in cm[0].explanation


def test_content_findings_dedupe_keeps_distinct_source_evidence():
    """Two findings with different source-evidence quotes are kept
    separate — they describe different observations from different parts
    of the source."""
    findings_in = [
        Finding(
            id="f1", citation_id="c1", reference_id="r1",
            category="content_mismatch", error_type="claim_reversal",
            severity=5, confidence="high",
            draft_claim_quote="claim a", source_evidence_quote="The opposite is true: X decreases.",
            explanation="The paper shows X decreases, not increases.",
            suggestion=None,
        ),
        Finding(
            id="f2", citation_id="c2", reference_id="r1",
            category="content_mismatch", error_type="number_distortion",
            severity=4, confidence="high",
            draft_claim_quote="claim b", source_evidence_quote="effect size was 0.2, not 0.7",
            explanation="Effect size citation is off by 0.5.",
            suggestion=None,
        ),
    ]
    report = build_draft_report(
        verified_refs=[], content_findings=findings_in, citations=[],
        orphan_citations=[], orphan_references=[], metadata=_meta(),
    )
    cm = [f for f in report.findings if f.category == "content_mismatch"]
    assert len(cm) == 2


def test_dedupe_does_not_merge_across_references():
    """Identical findings on different references must remain separate."""
    findings_in = [
        Finding(
            id="f1", citation_id="c1", reference_id="r1",
            category="content_mismatch", error_type="wrong_paper",
            severity=5, confidence="high",
            draft_claim_quote="x", source_evidence_quote=None,
            explanation="Wrong source attached",
            suggestion=None,
        ),
        Finding(
            id="f2", citation_id="c2", reference_id="r2",  # DIFFERENT ref
            category="content_mismatch", error_type="wrong_paper",
            severity=5, confidence="high",
            draft_claim_quote="x", source_evidence_quote=None,
            explanation="Wrong source attached",
            suggestion=None,
        ),
    ]
    report = build_draft_report(
        verified_refs=[], content_findings=findings_in, citations=[],
        orphan_citations=[], orphan_references=[], metadata=_meta(),
    )
    cm = [f for f in report.findings if f.category == "content_mismatch"]
    assert len(cm) == 2
