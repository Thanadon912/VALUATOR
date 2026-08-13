from __future__ import annotations

from enum import Enum


class ValuationMethodology(str, Enum):
    STANDARD = "Standard Driver-Based DCF"
    TECH = "Capitalized R&D DCF"
    FINANCIAL = "Regulatory FCFE"
    CYCLICAL = "Normalized Median DCF"
    # No "Fixed Leverage FCFE" / infrastructure route: AGENTS.md's adaptive DCF
    # spec lists exactly these four routes. A prior INFRASTRUCTURE enum member
    # had no calculation function, no routing rule, and no call site anywhere
    # in the codebase — removed rather than left as dead, unreachable code.


def _normalize_sic_code(sic_code: str | int | None) -> str:
    if sic_code is None:
        return ""
    normalized = str(sic_code).strip()
    return normalized if normalized.isdigit() else ""


def get_valuation_methodology(
    sic_code: str | int | None,
    finnhub_industry: str | None = None,
) -> ValuationMethodology:
    """Return the adaptive valuation methodology for a SEC SIC code and optional Finnhub industry."""
    normalized = _normalize_sic_code(sic_code)
    
    if finnhub_industry:
        ind = finnhub_industry.lower()
        if any(x in ind for x in ["technology", "software", "semiconductor", "hardware", "electronics"]):
            return ValuationMethodology.TECH
        elif any(x in ind for x in ["financial", "bank", "insurance"]):
            return ValuationMethodology.FINANCIAL
        elif any(x in ind for x in ["energy", "oil", "gas", "mining", "metals"]):
            return ValuationMethodology.CYCLICAL

    if not normalized:
        return ValuationMethodology.STANDARD

    if normalized.startswith(("60", "61")):
        return ValuationMethodology.FINANCIAL

    if (
        normalized.startswith("357")
        or normalized.startswith("737")
        # Electronic components & accessories (367x) covers SIC 3674
        # Semiconductors — the single largest tech grouping here (TSM, NVDA,
        # INTC, TXN, AVGO, AMD, MU). Without it these route to TECH only when
        # the Finnhub industry string happens to say "semiconductor", so a
        # provider outage, rate-limit, or expired key would silently move the
        # whole sector onto the standard driver engine and return a materially
        # different fair value. Engine selection must not hinge on one
        # third-party label when the SEC SIC code already states the sector.
        or normalized.startswith("367")
        or normalized.startswith("369")
        or normalized == "3711"
        # Retail-catalog & mail-order houses (e.g. AMZN, SIC 5961) run
        # platform/logistics/cloud businesses with R&D-heavy reinvestment
        # profiles much closer to frontier tech than a traditional
        # standard-driver DCF assumes. Mirrors the "retail-catalog" /
        # "e-commerce" terms already recognized for the frontier-tech SOTP
        # profile in sotp_configs.resolve_sotp_profile.
        or normalized == "5961"
    ):
        return ValuationMethodology.TECH

    try:
        sic_int = int(normalized)
    except ValueError:
        return ValuationMethodology.STANDARD

    if (
        normalized.startswith("13")
        or (
            normalized.startswith("28")
            # SIC 2840-2844 (soap, detergents, cleaning preparations,
            # perfumes, cosmetics — e.g. PG) is branded consumer staples, not
            # a commodity chemicals producer. The rest of division 28
            # (industrial/inorganic/organic chemicals, plastics, agricultural
            # chemicals) does track commodity input costs and stays cyclical.
            and not (2840 <= sic_int <= 2844)
        )
        or normalized.startswith("29")
        or 1000 <= sic_int <= 1499
    ):
        return ValuationMethodology.CYCLICAL

    return ValuationMethodology.STANDARD
