from __future__ import annotations

import re
from html import unescape


def _clean_text(value: str | None) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def extract_10k_description(html: str, filing: dict[str, str]) -> dict[str, object] | None:
    text = _clean_text(html)
    match = re.search(
        r"(?:Item\s+1\.?\s+Business|Business\s+Overview)(?P<body>.{300,4000}?)(?:Item\s+1A\.?|Risk Factors)",
        text,
        re.I,
    )
    if not match:
        return None
    body = _clean_text(match.group("body"))
    if "Item 1A" in body[:800] or len(re.findall(r"\bItem\s+\d", body[:1200], re.I)) > 2:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", body)
    selected = " ".join(sentences[:8]).strip()
    if len(selected) < 160:
        return None
    return {
        "value": selected[:1800],
        "provider": "SEC 10-K",
        "source_url": filing["source_url"],
        "filing_date": filing.get("filing_date"),
        "confidence": 0.9,
    }
