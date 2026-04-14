from __future__ import annotations
from typing import Any


_search_args_schema = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "authors", "year"],
    "properties": {
        "title": {"type": "string", "description": "Paper title (may be truncated)"},
        "authors": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Author surnames (family names only)",
        },
        "year": {"type": ["integer", "null"], "description": "Publication year, or null"},
    },
}


_doi_args_schema = {
    "type": "object",
    "additionalProperties": False,
    "required": ["doi"],
    "properties": {"doi": {"type": "string"}},
}


SUBMIT_METADATA_FINAL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_final",
        "description": (
            "Call this ONCE when you have made your verification verdict. "
            "This terminates the reasoning loop."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "confidence", "reasoning", "canonical",
                         "field_diffs", "abstract", "oa_pdf_url", "preprint_vs_published"],
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["verified", "metadata_error", "hallucination", "unverifiable"],
                },
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "reasoning": {
                    "type": "string",
                    "description": "Why you reached this verdict (2-3 sentences)",
                },
                "canonical": {
                    "type": ["object", "null"],
                    "description": "Canonical paper metadata from best-matching DB, or null if hallucination",
                    "additionalProperties": True,
                },
                "field_diffs": {
                    "type": "object",
                    "description": "Fields where user ref differs from canonical",
                    "additionalProperties": {"type": "array", "items": {"type": ["string", "null"]}},
                },
                "abstract": {
                    "type": ["string", "null"],
                    "description": "Abstract text if found, else null",
                },
                "oa_pdf_url": {
                    "type": ["string", "null"],
                    "description": "Open access PDF URL if available, else null",
                },
                "preprint_vs_published": {
                    "type": "boolean",
                    "description": "True if year mismatch is likely preprint vs published",
                },
            },
        },
    },
}


METADATA_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_crossref",
            "description": "Search Crossref by title+authors+year. Returns top candidate metadata.",
            "parameters": _search_args_schema,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_openalex",
            "description": "Search OpenAlex (like Crossref but includes abstracts and OA URLs).",
            "parameters": _search_args_schema,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_semantic_scholar",
            "description": "Search Semantic Scholar (includes abstracts).",
            "parameters": _search_args_schema,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_pubmed",
            "description": "Search PubMed (biomedical literature, includes abstracts).",
            "parameters": _search_args_schema,
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_doi_crossref",
            "description": "Direct DOI lookup via Crossref. Use if DOI is provided.",
            "parameters": _doi_args_schema,
        },
    },
    SUBMIT_METADATA_FINAL,
]


SUBMIT_CONTENT_FINAL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_final",
        "description": (
            "Call this ONCE when you have made your content verification verdict."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "required": ["category", "error_type", "severity", "confidence",
                         "source_evidence_quote", "explanation", "suggestion"],
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["content_mismatch", "weak_context", "none",
                             "abstract_insufficient"],
                },
                "error_type": {"type": ["string", "null"]},
                "severity": {"type": "integer", "minimum": 1, "maximum": 5},
                "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                "source_evidence_quote": {
                    "type": "string",
                    "description": "Verbatim from source text, or empty string",
                },
                "explanation": {"type": "string"},
                "suggestion": {"type": ["string", "null"]},
            },
        },
    },
}


CONTENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "find_passage",
            "description": (
                "Search the source text (abstract or full text) for a specific passage. "
                "Returns paragraphs containing any keyword from the query."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords to search (space separated)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_full_text",
            "description": (
                "Attempt to retrieve full text of the paper. "
                "Only works if the paper has an open access version. Returns text or null."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["doi"],
                "properties": {"doi": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_abstract",
            "description": "Refetch the abstract from OpenAlex/SS/PubMed for a given DOI.",
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "required": ["doi"],
                "properties": {"doi": {"type": "string"}},
            },
        },
    },
    SUBMIT_CONTENT_FINAL,
]
