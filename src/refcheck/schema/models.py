from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Author(BaseModel):
    model_config = ConfigDict(extra="forbid")
    given: str | None = None
    family: str


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    authors: list[Author]
    year: int | None
    title: str
    journal: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    doi: str | None = None
    raw_text: str
    style_detected: Literal["APA", "Vancouver", "Nature", "Chicago", "IEEE", "unknown"]


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    surface: str
    ref_ids: list[str]
    char_offset: int
    containing_sentence: str
    surrounding_paragraph: str


class VerifiedReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: Reference
    status: Literal["verified", "hallucination", "metadata_error", "unverifiable"]
    canonical: Reference | None = None
    field_diffs: dict[str, tuple[str | None, str | None]] = Field(default_factory=dict)
    access_level: Literal["full_text", "abstract_only", "paywalled", "not_found"] = "not_found"
    abstract: str | None = None
    full_text: str | None = None
    sources_checked: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    citation_id: str
    reference_id: str
    category: Literal[
        "hallucination", "metadata", "content_mismatch", "weak_context",
        "partial_verified", "paywalled", "unverifiable", "citation_unmatched",
    ]
    error_type: str | None = None
    severity: int = Field(ge=1, le=5)
    confidence: Literal["high", "medium", "low"]
    draft_claim_quote: str
    source_evidence_quote: str | None = None
    explanation: str
    suggestion: str | None = None


class ReportMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_title: str
    processing_seconds: float
    total_usd_cost: float
    verification_level: Literal["fast", "precise", "ultra"]


class DraftReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    metadata: ReportMetadata
    summary_counts: dict[str, int]
    findings: list[Finding]
    references: list[VerifiedReference]
    unverified_manual_review: list[str]
