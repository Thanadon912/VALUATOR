"""Classification-driven SOTP profiles for frontier/high-growth businesses."""

from __future__ import annotations

from typing import Any


SOTP_PROFILE_CONFIGS: dict[str, dict[str, Any]] = {
    "software": {"sector": "Technology"},
    "semiconductors": {"sector": "Semiconductors"},
    "automotive": {"sector": "Automotive Technology"},
    "frontier-tech": {"sector": "Technology"},
}


def _classification_text(classification: Any) -> str:
    if classification is None:
        return ""
    if hasattr(classification, "model_dump"):
        data = classification.model_dump(by_alias=True)
    elif isinstance(classification, dict):
        data = classification
    else:
        return ""
    values = [
        data.get("sector", ""),
        data.get("industry", ""),
        data.get("sicDescription", data.get("sic_description", "")),
        *(data.get("businessTags", data.get("business_tags", [])) or []),
        *(data.get("revenueSegments", data.get("revenue_segments", [])) or []),
    ]
    return " ".join(str(value) for value in values).lower()


def resolve_sotp_profile(
    *,
    classification: Any = None,
    methodology: str | None = None,
    sic_description: str | None = None,
    industry: str | None = None,
) -> str | None:
    text = " ".join(
        value for value in (
            _classification_text(classification),
            (sic_description or "").lower(),
            (industry or "").lower(),
        ) if value
    )
    if any(term in text for term in ("semiconductor", "chip", "accelerated compute", "gpu")):
        return "semiconductors"
    if any(term in text for term in ("motor vehicle", "automotive", "electric vehicle", "autonomous driving", "robotaxi")):
        return "automotive"
    if any(term in text for term in ("software", "cloud", "internet services", "data processing", "artificial intelligence")):
        return "software"
    if methodology == "Capitalized R&D DCF" or any(
        term in text for term in ("technology", "frontier tech", "high-growth tech", "retail-catalog", "e-commerce")
    ):
        return "frontier-tech"
    return None


def get_sotp_config(**routing_context: Any) -> dict[str, Any] | None:
    profile = resolve_sotp_profile(**routing_context)
    if profile is None:
        return None
    classification = routing_context.get("classification")
    sector = SOTP_PROFILE_CONFIGS[profile]["sector"]
    # Classification currently provides labels, not audited segment revenue,
    # margins, or invested capital. Do not reuse vendor-specific templates for
    # another company. Until quantified filing-backed segments exist, expose a
    # transparent 100% Core Business fallback.
    return {
        "sector": sector,
        "profile": profile,
        "segment_source": "single_segment_fallback_unquantified_classification",
        "classification_available": classification is not None,
        "segments": [
            {
                "name": "Core Business",
                "base_revenue_fraction": 1.0,
                "is_high_growth": False,
            }
        ],
    }
