from refcheck.report.aggregator import build_draft_report
from refcheck.schema.models import (
    VerifiedReference, Reference, Author, Citation, Finding, ReportMetadata,
)


def _ref(id_, title="T"):
    return Reference(id=id_, authors=[Author(family="X")], year=2020,
                     title=title, raw_text="...", style_detected="APA")


def _vref(status, id_="r1", access="abstract_only"):
    r = _ref(id_)
    return VerifiedReference(
        reference=r,
        status=status,
        canonical=r if status != "hallucination" else None,
        access_level=access,
    )


def test_counts_by_status():
    vrefs = [_vref("verified", "r1"), _vref("hallucination", "r2"),
             _vref("metadata_error", "r3"), _vref("unverifiable", "r4")]
    report = build_draft_report(
        verified_refs=vrefs,
        content_findings=[],
        citations=[],
        orphan_citations=[],
        orphan_references=[],
        metadata=ReportMetadata(
            draft_title="t", processing_seconds=1.0, total_usd_cost=0.1,
            verification_level="precise",
        ),
    )
    assert report.summary_counts["verified"] == 1
    assert report.summary_counts["hallucination"] == 1
    assert report.summary_counts["metadata_error"] == 1
    assert report.summary_counts["unverifiable"] == 1


def test_hallucination_generates_finding():
    vref = _vref("hallucination", "r1")
    citations = [Citation(id="c1", surface="(X, 2020)", ref_ids=["r1"],
                          char_offset=0, containing_sentence="...", surrounding_paragraph="...")]
    report = build_draft_report(
        verified_refs=[vref], content_findings=[], citations=citations,
        orphan_citations=[], orphan_references=[],
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
    )
    hall = [f for f in report.findings if f.category == "hallucination"]
    assert len(hall) == 1
    assert hall[0].severity == 5
    assert hall[0].reference_id == "r1"


def test_sorts_by_severity_desc():
    f1 = Finding(id="f1", citation_id="c1", reference_id="r1", category="content_mismatch",
                 error_type="minor", severity=2, confidence="high",
                 draft_claim_quote="a", explanation="a", suggestion=None)
    f2 = Finding(id="f2", citation_id="c2", reference_id="r2", category="content_mismatch",
                 error_type="major", severity=5, confidence="high",
                 draft_claim_quote="b", explanation="b", suggestion=None)
    report = build_draft_report(
        verified_refs=[], content_findings=[f1, f2], citations=[],
        orphan_citations=[], orphan_references=[],
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
    )
    assert report.findings[0].severity == 5
    assert report.findings[1].severity == 2


def test_unverifiable_added_to_manual_review():
    vrefs = [_vref("unverifiable", "r1"), _vref("verified", "r2")]
    report = build_draft_report(
        verified_refs=vrefs, content_findings=[], citations=[],
        orphan_citations=[], orphan_references=[],
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
    )
    assert "r1" in report.unverified_manual_review
    assert "r2" not in report.unverified_manual_review


def test_preprint_vs_published_emits_informational_finding():
    """저자·제목 일치하는데 연도 1년 차이 → preprint_vs_published, severity 1."""
    r = _ref("r1")
    vref = VerifiedReference(
        reference=r,
        status="metadata_error",
        canonical=r,
        field_diffs={"year": ("2012", "2013")},
        access_level="not_found",
        preprint_vs_published=True,
    )
    citations = [Citation(id="c1", surface="(X, 2012)", ref_ids=["r1"],
                          char_offset=0, containing_sentence="Claim (X, 2012).",
                          surrounding_paragraph="Claim (X, 2012).")]
    report = build_draft_report(
        verified_refs=[vref], content_findings=[], citations=citations,
        orphan_citations=[], orphan_references=[],
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
    )
    preprint_findings = [f for f in report.findings if f.error_type == "preprint_vs_published"]
    assert len(preprint_findings) == 1
    assert preprint_findings[0].severity == 1
    # field_mismatch가 동시에 emit되면 안 됨
    field_findings = [f for f in report.findings if f.error_type == "field_mismatch"]
    assert field_findings == []


def test_partial_verified_finding_for_abstract_only():
    """abstract_only 접근 수준은 informational partial_verified finding 생성."""
    vref = _vref("verified", "r1", access="abstract_only")
    citations = [Citation(id="c1", surface="(X, 2020)", ref_ids=["r1"],
                          char_offset=0, containing_sentence="...",
                          surrounding_paragraph="...")]
    report = build_draft_report(
        verified_refs=[vref], content_findings=[], citations=citations,
        orphan_citations=[], orphan_references=[],
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
    )
    partial = [f for f in report.findings if f.category == "partial_verified"]
    assert len(partial) == 1
    assert partial[0].severity == 1
    assert partial[0].confidence == "low"


def test_no_partial_verified_for_full_text():
    """full_text 접근 가능하면 partial_verified finding 없음."""
    vref = _vref("verified", "r1", access="full_text")
    citations = [Citation(id="c1", surface="(X, 2020)", ref_ids=["r1"],
                          char_offset=0, containing_sentence="...",
                          surrounding_paragraph="...")]
    report = build_draft_report(
        verified_refs=[vref], content_findings=[], citations=citations,
        orphan_citations=[], orphan_references=[],
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
    )
    partial = [f for f in report.findings if f.category == "partial_verified"]
    assert partial == []


def test_orphan_reference_emits_finding():
    """본문에서 인용되지 않은 참고문헌은 citation_unmatched finding 생성."""
    report = build_draft_report(
        verified_refs=[], content_findings=[], citations=[],
        orphan_citations=[], orphan_references=["ref_unused"],
        metadata=ReportMetadata(draft_title="t", processing_seconds=1.0,
                                total_usd_cost=0.1, verification_level="precise"),
    )
    orphan = [f for f in report.findings if f.error_type == "orphan_reference"]
    assert len(orphan) == 1
    assert orphan[0].reference_id == "ref_unused"
