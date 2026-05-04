from refcheck.schema.models import (
    Author, Reference, Citation, VerifiedReference,
    Finding, DraftReport, ReportMetadata
)


def test_reference_accepts_none_fields():
    ref = Reference(
        id="ref_001",
        authors=[Author(given="Marc", family="Potenza")],
        year=2013,
        title="Neurobiology of gambling",
        journal=None,
        volume=None,
        pages=None,
        doi=None,
        raw_text="Potenza, M. (2013). ...",
        style_detected="APA",
    )
    assert ref.id == "ref_001"
    assert ref.authors[0].family == "Potenza"


def test_finding_severity_range():
    import pytest
    with pytest.raises(ValueError):
        Finding(
            id="f_001",
            citation_id="cit_001",
            reference_id="ref_001",
            category="content_mismatch",
            error_type="주장 반전",
            severity=6,  # out of range
            confidence="high",
            draft_claim_quote="...",
            source_evidence_quote="...",
            explanation="...",
            suggestion=None,
        )


def test_verified_reference_diff_severities_default_empty():
    """diff_severities should default to {} when not provided."""
    ref = Reference(
        id="r1", authors=[Author(family="X")], year=2020,
        title="T", raw_text="raw", style_detected="APA",
    )
    vref = VerifiedReference(reference=ref, status="verified")
    assert vref.diff_severities == {}


def test_verified_reference_diff_severities_validates_enum():
    """diff_severities values must be one of the four allowed levels."""
    import pytest
    ref = Reference(
        id="r1", authors=[Author(family="X")], year=2020,
        title="T", raw_text="raw", style_detected="APA",
    )
    # Valid
    vref = VerifiedReference(
        reference=ref, status="metadata_error",
        field_diffs={"year": ("2019", "2020")},
        diff_severities={"year": "info"},
    )
    assert vref.diff_severities["year"] == "info"
    # Invalid value
    with pytest.raises(ValueError):
        VerifiedReference(
            reference=ref, status="metadata_error",
            diff_severities={"year": "nonsense"},  # type: ignore[dict-item]
        )


def test_draft_report_summary_counts():
    report = DraftReport(
        metadata=ReportMetadata(
            draft_title="Test",
            processing_seconds=10.0,
            total_usd_cost=0.5,
            verification_level="precise",
        ),
        summary_counts={"verified": 5, "hallucination": 1},
        findings=[],
        references=[],
        unverified_manual_review=[],
    )
    assert report.summary_counts["hallucination"] == 1
