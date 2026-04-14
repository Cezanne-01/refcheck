CONTENT_VERIFY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "category", "error_type", "severity", "confidence",
        "source_evidence_quote", "explanation", "suggestion",
    ],
    "properties": {
        "category": {
            "type": "string",
            "enum": ["content_mismatch", "weak_context", "none"],
        },
        "error_type": {"type": ["string", "null"]},
        "severity": {"type": "integer", "minimum": 1, "maximum": 5},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "source_evidence_quote": {"type": "string"},
        "explanation": {"type": "string"},
        "suggestion": {"type": ["string", "null"]},
    },
}
