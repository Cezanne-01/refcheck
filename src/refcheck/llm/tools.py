from __future__ import annotations
import re
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


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _ref_to_dict(ref: Any) -> dict[str, Any]:
    """Convert a Reference model to a plain dict suitable for tool output."""
    if ref is None:
        return {"found": False}
    return {
        "found": True,
        "title": ref.title,
        "authors": [{"given": a.given, "family": a.family} for a in ref.authors],
        "year": ref.year,
        "journal": ref.journal,
        "volume": ref.volume,
        "issue": ref.issue,
        "pages": ref.pages,
        "doi": ref.doi,
    }


# ---------------------------------------------------------------------------
# Dispatchers
# ---------------------------------------------------------------------------

class MetadataToolDispatcher:
    """Routes agent tool calls to backing DB clients."""

    def __init__(
        self,
        *,
        crossref: Any,
        openalex: Any,
        semantic_scholar: Any,
        pubmed: Any,
    ) -> None:
        self._crossref = crossref
        self._openalex = openalex
        self._semantic = semantic_scholar
        self._pubmed = pubmed

    async def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "search_crossref":
                from refcheck.schema.models import Author
                authors = [Author(family=a) for a in args.get("authors", [])]
                ref = await self._crossref.search(
                    title=args["title"], authors=authors, year=args.get("year"),
                )
                return _ref_to_dict(ref)

            if name == "lookup_doi_crossref":
                ref = await self._crossref.lookup_doi(args["doi"])
                return _ref_to_dict(ref)

            if name == "search_openalex":
                from refcheck.schema.models import Author
                authors = [Author(family=a) for a in args.get("authors", [])]
                res = await self._openalex.search(
                    title=args["title"], authors=authors, year=args.get("year"),
                )
                if res is None:
                    return {"found": False}
                out = _ref_to_dict(res.reference)
                out["abstract"] = res.abstract
                out["is_oa"] = res.is_oa
                out["oa_pdf_url"] = res.oa_url
                return out

            if name == "search_semantic_scholar":
                from refcheck.schema.models import Author
                authors = [Author(family=a) for a in args.get("authors", [])]
                res = await self._semantic.search(
                    title=args["title"], authors=authors, year=args.get("year"),
                )
                if res is None:
                    return {"found": False}
                out = _ref_to_dict(res.reference)
                out["abstract"] = res.abstract
                return out

            if name == "search_pubmed":
                from refcheck.schema.models import Author
                authors = [Author(family=a) for a in args.get("authors", [])]
                res = await self._pubmed.search(
                    title=args["title"], authors=authors, year=args.get("year"),
                )
                if res is None:
                    return {"found": False}
                out = _ref_to_dict(res.reference)
                out["abstract"] = res.abstract
                return out

            return {"error": f"unknown tool: {name}"}
        except Exception as e:
            return {"error": str(e)}


class ContentToolDispatcher:
    """Routes content-agent tool calls.

    Holds the current source text (abstract or full text of the cited paper).
    ``find_passage`` searches this text by keyword overlap.
    ``fetch_full_text`` / ``fetch_abstract`` are optional — attempt to upgrade
    the source text and return new text. Caller updates source_text if successful.
    """

    def __init__(
        self,
        *,
        source_text: str = "",
        openalex: Any | None = None,
        unpaywall: Any | None = None,
    ) -> None:
        self._source_text = source_text
        self._openalex = openalex
        self._unpaywall = unpaywall

    @property
    def source_text(self) -> str:
        return self._source_text

    def set_source_text(self, text: str) -> None:
        self._source_text = text

    async def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "find_passage":
            return self._find_passage(args["query"])
        if name == "fetch_abstract":
            return await self._fetch_abstract(args["doi"])
        if name == "fetch_full_text":
            return await self._fetch_full_text(args["doi"])
        return {"error": f"unknown tool: {name}"}

    def _find_passage(self, query: str) -> dict[str, Any]:
        if not self._source_text:
            return {"passages": [], "note": "no source text available"}
        keywords = [w.lower() for w in re.findall(r"[A-Za-z가-힣0-9]{3,}", query)]
        if not keywords:
            return {"passages": [], "note": "no searchable keywords"}
        paragraphs = re.split(r"\n{2,}", self._source_text)
        matches: list[tuple[int, str]] = []
        for p in paragraphs:
            p_lower = p.lower()
            hits = sum(1 for kw in keywords if kw in p_lower)
            if hits > 0:
                matches.append((hits, p))
        matches.sort(key=lambda x: -x[0])
        return {"passages": [m[1][:1500] for m in matches[:3]]}

    async def _fetch_abstract(self, doi: str) -> dict[str, Any]:
        # Note: OpenAlexClient currently has no DOI-lookup method. The abstract
        # for this paper is already embedded in the agent's user prompt, so
        # returning a clear "not implemented" signal avoids misleading the
        # agent with unrelated search results.
        return {
            "abstract": None,
            "note": "fetch_abstract not implemented in this version; "
                    "use the abstract provided in the user prompt",
        }

    async def _fetch_full_text(self, doi: str) -> dict[str, Any]:
        if self._unpaywall is None:
            return {"full_text": None, "note": "no unpaywall client"}
        try:
            url = await self._unpaywall.oa_pdf_url(doi)
            if not url:
                return {"full_text": None, "note": "not open access"}
            return {
                "full_text": None,
                "oa_pdf_url": url,
                "note": "OA URL found but full text download not executed in-agent",
            }
        except Exception as e:
            return {"full_text": None, "error": str(e)}
