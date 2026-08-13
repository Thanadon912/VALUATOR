"""Representative tickers for each valuation category, with the invariants
that category's output must satisfy.

One ticker per category so the suite actually exercises every reachable
adaptive DCF engine plus the cross-cutting data shapes that have produced
real defects (ADR/non-USD reporting, IFRS filers with provider gaps,
dividend applicability, implausible provider consensus).

SIC codes are the SEC-assigned values; industries are the Finnhub strings.
Both are recorded because `get_valuation_methodology` consults the industry
label first and the SIC code second — routing must land on the same engine
either way, so a provider outage cannot silently change the engine.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValuationEngineCase:
    """A ticker chosen to represent exactly one valuation category."""

    engine: str
    ticker: str
    sic_code: str
    finnhub_industry: str
    rationale: str
    # Fields the engine's own output must expose.
    required_assumption_keys: tuple[str, ...] = ()
    # Fields that belong to a different engine and must not leak in.
    forbidden_assumption_keys: tuple[str, ...] = ()


# Multi-stage FCFF fields; any engine that is not the growth model must not
# expose these, otherwise the response misrepresents which model produced it.
_MULTISTAGE_ONLY_KEYS = (
    "consensus_coverage",
    "terminal_margin",
    "terminal_margin_basis",
    "margin_consensus_rejected",
)


ENGINE_COVERAGE_CASES: tuple[ValuationEngineCase, ...] = (
    ValuationEngineCase(
        engine="Capitalized R&D DCF",
        ticker="NVDA",
        sic_code="3674",
        finnhub_industry="Semiconductors",
        rationale=(
            "Pure-play semiconductor with a valid multi-year R&D history and USD "
            "reporting; also the regression target for SIC 367x routing."
        ),
        required_assumption_keys=(
            "consensus_coverage",
            "terminal_margin",
            "terminal_margin_basis",
            "terminal_roic",
            "terminal_reinvestment_rate",
            "rnd_capitalization_applied",
        ),
        forbidden_assumption_keys=("tier1_capital_ratio",),
    ),
    ValuationEngineCase(
        engine="Regulatory FCFE",
        ticker="JPM",
        sic_code="6021",
        finnhub_industry="Banking",
        rationale="Bank: equity-side model discounted at cost of equity, no enterprise value.",
        required_assumption_keys=(
            "tier1_capital_ratio",
            "present_value_fcfe",
            "present_value_terminal_value",
            "discount_rate_basis",
        ),
        forbidden_assumption_keys=("enterprise_value",) + _MULTISTAGE_ONLY_KEYS,
    ),
    ValuationEngineCase(
        engine="Normalized Median DCF",
        ticker="XOM",
        sic_code="2911",
        finnhub_industry="Energy",
        rationale=(
            "Integrated oil and gas: the cyclical case whose whole purpose is to "
            "value off a normalized median margin rather than the latest year."
        ),
        required_assumption_keys=("normalized_margin", "enterprise_value"),
        forbidden_assumption_keys=_MULTISTAGE_ONLY_KEYS + ("tier1_capital_ratio",),
    ),
    ValuationEngineCase(
        engine="Standard Driver-Based DCF",
        ticker="KO",
        sic_code="2080",
        finnhub_industry="Beverages",
        rationale=(
            "Non-tech consumer staples that genuinely routes to the standard driver "
            "engine (not the growth model's R&D-fallback label) and pays a dividend."
        ),
        required_assumption_keys=("sales_to_capital_ratio", "enterprise_value"),
        forbidden_assumption_keys=_MULTISTAGE_ONLY_KEYS + ("tier1_capital_ratio",),
    ),
)


@dataclass(frozen=True)
class DataShapeCase:
    """A cross-cutting data shape that is independent of engine selection."""

    shape: str
    ticker: str
    rationale: str
    expectations: tuple[str, ...] = field(default=())


DATA_SHAPE_CASES: tuple[DataShapeCase, ...] = (
    DataShapeCase(
        shape="adr_non_usd_reporting",
        ticker="TSM",
        rationale=(
            "ADR whose SEC-filed statements are USD but whose separate FMP "
            "analyst-estimates consensus feed is TWD; original FX normalization "
            "defect was this statement/consensus currency mismatch."
        ),
        expectations=(
            "reported_currency and fx_translation.rate are present (statement-level basis)",
            "analyst_estimates_normalization.status == 'normalized' with source_units ['TWD']",
            "adr_ratio == 5.0 and fair value is per ADS",
        ),
    ),
    DataShapeCase(
        shape="ifrs_filer_with_provider_gaps",
        ticker="ASML",
        rationale="EUR 20-F filer where Yahoo/Finnhub/FMP each have holes; peer-multiple defect.",
        expectations=(
            "peer P/B below the implausibility bound",
            "peer EV/EBITDA below the implausibility bound",
            "rejected provider values are disclosed rather than published",
        ),
    ),
    DataShapeCase(
        shape="dividend_payer_ddm_applicable",
        ticker="KO",
        rationale="Reliable dividend payer; DDM must produce a value.",
        expectations=("DDM returns a computed fair value",),
    ),
    DataShapeCase(
        shape="non_dividend_payer_ddm_inapplicable",
        ticker="NVDA",
        rationale="Negligible dividend; DDM must decline rather than fabricate.",
        expectations=("DDM status is INAPPLICABLE with stated reasons",),
    ),
    DataShapeCase(
        shape="implausible_flat_consensus_margin",
        ticker="AMZN",
        rationale="Provider backfills a flat out-year EBIT margin diverging from the filed margin.",
        expectations=(
            "margin_consensus_rejected is True with a disclosed reason",
            "revenue consensus is still used for growth",
        ),
    ),
)
