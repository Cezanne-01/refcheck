from __future__ import annotations
import re


def _normalize_for_match(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def quote_exists_in_source(quote: str, source: str) -> bool:
    """공백·대소문자 차이를 허용하고 quote가 source에 포함되는지 확인."""
    if not quote.strip():
        return True
    if not source:
        return False
    q = _normalize_for_match(quote)
    s = _normalize_for_match(source)
    return q in s
