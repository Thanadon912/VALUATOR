import math
from statistics import median, mean
from typing import Callable, List, Dict, Any, Optional

import numpy as np


MIN_SALES_TO_CAPITAL_RATIO = 1.0
MAX_SALES_TO_CAPITAL_RATIO = 4.0
MAX_REINVESTMENT_TO_NOPAT = 0.80
MIN_EBIT_MARGIN = 0.05
MATURE_EBIT_MARGIN = 0.08
EBIT_MARGIN_FADE_YEAR = 5
MAX_TERMINAL_WACC = 0.10
DEFAULT_TIER1_CAPITAL_RATIO = 0.10
MONTE_CARLO_ITERATIONS = 10_000
# A relative gap this large between a flat consensus EBIT margin and the
# company's own current sourced margin indicates the provider's out-year EBIT
# figures are a formulaic extrapolation rather than an independent forecast.
MARGIN_CONSENSUS_MAX_RELATIVE_DEVIATION = 0.20


EngineRunner = Callable[[float, Optional[float]], Dict[str, Any]]


def normalize_equity_value_per_traded_share(total_equity_value_usd: float, total_ordinary_shares: float, adr_ratio: float = 1.0) -> float:
    """Return USD per listed share (ADR or ordinary). total_ordinary_shares is passed from shares_outstanding which is already listed shares."""
    if total_ordinary_shares <= 0 or adr_ratio <= 0:
        raise ValueError("Shares outstanding and ADR ratio must be positive.")
    return total_equity_value_usd / total_ordinary_shares


def _validated_rnd_history(trailing_rnd: Optional[List[Any]]) -> tuple[List[float], str | None]:
    observations = trailing_rnd or []
    if observations and all(not isinstance(item, dict) for item in observations):
        values = [_as_finite_float(item) for item in observations]
        valid = [value for value in values if value is not None and value >= 0]
        return (valid, None) if len(valid) == len(observations) else ([], "invalid numeric R&D value")

    normalized: list[tuple[str, float]] = []
    for item in observations:
        if not isinstance(item, dict):
            return [], "mixed R&D history representation"
        value = _as_finite_float(item.get("value"))
        end = str(item.get("end") or "")
        unit = item.get("unit") or item.get("currency")
        if value is None or value < 0 or len(end) < 4:
            return [], "R&D history contains an invalid annual observation"
        if unit != "USD":
            return [], "R&D history is not normalized to USD"
        if item.get("form") not in {"10-K", "20-F", "40-F"}:
            return [], "R&D history contains a non-annual filing"
        normalized.append((end, value))

    normalized.sort(key=lambda item: item[0])
    years = [int(end[:4]) for end, _ in normalized]
    if len(years) != len(set(years)):
        return [], "R&D history contains duplicate fiscal years"
    if len(years) >= 3 and any(current - previous != 1 for previous, current in zip(years[-3:], years[-2:])):
        return [], "R&D history does not contain three consecutive fiscal years"
    return [value for _, value in normalized], None


def _as_finite_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def _engine_fair_value(
    engine_runner: EngineRunner,
    revenue_growth: float,
    operating_margin: Optional[float],
) -> Optional[float]:
    try:
        result = engine_runner(float(revenue_growth), operating_margin)
    except (ArithmeticError, ValueError, OverflowError):
        return None
    return _as_finite_float(result.get("computed_fair_value"))


def run_monte_carlo_simulation(
    *,
    engine_runner: EngineRunner,
    base_revenue_growth: float,
    base_operating_margin: Optional[float],
    revenue_growth_volatility: float,
    operating_margin_volatility: float,
    iterations: int = MONTE_CARLO_ITERATIONS,
    random_seed: int = 42,
    revenue_growth_bounds: tuple[float, float] = (-0.20, 0.30),
    operating_margin_bounds: tuple[float, float] = (-0.20, 0.60),
    live_market_price: Optional[float] = None,
    histogram_bin_count: int = 40,
) -> Dict[str, Any]:
    """Run the routed valuation engine across a fixed 10,000-iteration sample."""
    if iterations != MONTE_CARLO_ITERATIONS:
        raise ValueError("Monte Carlo simulation must run exactly 10,000 iterations.")
    if histogram_bin_count <= 0:
        raise ValueError("Monte Carlo histogram bin count must be positive.")

    rng = np.random.default_rng(random_seed)
    growth_sigma = max(float(revenue_growth_volatility or 0.0), 0.0)
    margin_sigma = max(float(operating_margin_volatility or 0.0), 0.0)
    revenue_growth_samples = np.clip(
        rng.normal(float(base_revenue_growth), growth_sigma, iterations),
        revenue_growth_bounds[0],
        revenue_growth_bounds[1],
    )

    if base_operating_margin is None:
        operating_margin_samples: list[Optional[float]] = [None] * iterations
    else:
        operating_margin_samples = np.clip(
            rng.normal(float(base_operating_margin), margin_sigma, iterations),
            operating_margin_bounds[0],
            operating_margin_bounds[1],
        ).tolist()

    fair_values = np.array(
        [
            value
            for value in (
                _engine_fair_value(engine_runner, growth, margin)
                for growth, margin in zip(
                    revenue_growth_samples,
                    operating_margin_samples,
                )
            )
            if value is not None
        ],
        dtype=float,
    )
    if fair_values.size == 0:
        raise ValueError("Monte Carlo simulation produced no valid valuation results.")

    sorted_values = np.sort(fair_values)
    bear_p10, base_p50, bull_p90 = np.percentile(sorted_values, [10, 50, 90])
    counts, edges = np.histogram(sorted_values, bins=histogram_bin_count)
    histogram_bins = [
        {
            "lower_bound": float(edges[index]),
            "upper_bound": float(edges[index + 1]),
            "count": int(count),
            "probability": float(count / fair_values.size),
        }
        for index, count in enumerate(counts)
    ]
    parsed_live_price = _as_finite_float(live_market_price)
    live_price_percentile = (
        float(np.searchsorted(sorted_values, parsed_live_price, side="right") / fair_values.size * 100)
        if parsed_live_price is not None
        else None
    )
    return {
        "bear_p10": float(bear_p10),
        "base_p50": float(base_p50),
        "bull_p90": float(bull_p90),
        "iteration_count": MONTE_CARLO_ITERATIONS,
        "valid_sample_count": int(fair_values.size),
        "distribution": "normal",
        "random_seed": random_seed,
        "histogram_bins": histogram_bins,
        "live_price_percentile": live_price_percentile,
    }


def _binary_search_target(
    value_at: Callable[[float], Optional[float]],
    target_value: float,
    lower_bound: float,
    upper_bound: float,
    *,
    tolerance: float,
    max_iterations: int = 64,
) -> Optional[tuple[float, float]]:
    lower_value = value_at(lower_bound)
    upper_value = value_at(upper_bound)
    if lower_value is None or upper_value is None:
        return None

    lower_gap = lower_value - target_value
    upper_gap = upper_value - target_value
    if abs(lower_gap) <= tolerance:
        return lower_bound, lower_value
    if abs(upper_gap) <= tolerance:
        return upper_bound, upper_value
    if lower_gap * upper_gap > 0:
        return None

    low = lower_bound
    high = upper_bound
    low_gap = lower_gap
    high_gap = upper_gap
    best_point = lower_bound
    best_value = lower_value
    best_gap = abs(lower_gap)

    for _ in range(max_iterations):
        midpoint = (low + high) / 2
        midpoint_value = value_at(midpoint)
        if midpoint_value is None:
            break
        midpoint_gap = midpoint_value - target_value
        if abs(midpoint_gap) < best_gap:
            best_point = midpoint
            best_value = midpoint_value
            best_gap = abs(midpoint_gap)
        if abs(midpoint_gap) <= tolerance:
            return midpoint, midpoint_value
        if low_gap * midpoint_gap <= 0:
            high = midpoint
            high_gap = midpoint_gap
        else:
            low = midpoint
            low_gap = midpoint_gap

    _ = high_gap
    return best_point, best_value


def calculate_implied_expectations(
    *,
    engine_runner: EngineRunner,
    live_market_price: float,
    base_revenue_growth: float,
    base_operating_margin: Optional[float],
    revenue_growth_bounds: tuple[float, float] = (-0.05, 5.0),
    operating_margin_bounds: tuple[float, float] = (0.01, 0.95),
    tolerance: float = 0.01,
) -> Dict[str, Any]:
    """Find growth/margin assumptions that reconcile model value to market price."""
    target_value = _as_finite_float(live_market_price)
    if target_value is None or target_value <= 0:
        raise ValueError("Live market price must be positive.")

    if base_operating_margin is None:
        growth_solution = _binary_search_target(
            lambda growth: _engine_fair_value(engine_runner, growth, None),
            target_value,
            revenue_growth_bounds[0],
            revenue_growth_bounds[1],
            tolerance=tolerance,
        )
        if growth_solution is None:
            raise ValueError("Implied revenue growth did not bracket the market price.")
        implied_growth, model_value = growth_solution
        solved_result = engine_runner(float(implied_growth), None)
        trajectory = _implied_trajectory(solved_result)
        return {
            "implied_revenue_cagr": float(implied_growth),
            "implied_stage_1_revenue_cagr": float(implied_growth),
            "implied_operating_margin": None,
            **trajectory,
            "target_price": float(target_value),
            "model_fair_value": float(model_value),
            "valuation_gap": float(model_value - target_value),
            "solver_status": (
                "converged"
                if abs(model_value - target_value) <= tolerance
                else "best_effort"
            ),
            "solver_selection_basis": "single-variable growth bisection across configured extreme bounds",
            "revenue_growth_bounds": list(revenue_growth_bounds),
            "operating_margin_bounds": list(operating_margin_bounds),
        }

    candidates: list[dict[str, float]] = []
    growth_grid = np.linspace(revenue_growth_bounds[0], revenue_growth_bounds[1], 61)
    for growth in growth_grid:
        margin_solution = _binary_search_target(
            lambda margin: _engine_fair_value(engine_runner, float(growth), margin),
            target_value,
            operating_margin_bounds[0],
            operating_margin_bounds[1],
            tolerance=tolerance,
        )
        if margin_solution is None:
            continue
        margin, model_value = margin_solution
        growth_span = revenue_growth_bounds[1] - revenue_growth_bounds[0]
        margin_span = operating_margin_bounds[1] - operating_margin_bounds[0]
        normalized_distance = (
            abs(float(growth) - base_revenue_growth) / growth_span
            + abs(margin - base_operating_margin) / margin_span
        )
        candidates.append(
            {
                "growth": float(growth),
                "margin": float(margin),
                "model_value": float(model_value),
                "gap": float(model_value - target_value),
                "distance": float(normalized_distance),
            }
        )

    if not candidates:
        raise ValueError("Implied expectations did not bracket the market price.")

    candidates.sort(key=lambda item: (abs(item["gap"]) > tolerance, item["distance"], abs(item["gap"])))
    selected = candidates[0]
    solved_result = engine_runner(selected["growth"], selected["margin"])
    trajectory = _implied_trajectory(solved_result)
    return {
        "implied_revenue_cagr": selected["growth"],
        "implied_stage_1_revenue_cagr": selected["growth"],
        "implied_operating_margin": selected["margin"],
        "implied_target_ebit_margin": selected["margin"],
        **trajectory,
        "target_price": float(target_value),
        "model_fair_value": selected["model_value"],
        "valuation_gap": selected["gap"],
        "solver_status": (
            "converged"
            if abs(selected["gap"]) <= tolerance
            else "best_effort"
        ),
        "solver_selection_basis": "nearest feasible growth-margin pair to sourced base assumptions",
        "feasible_curve": [c for c in candidates if abs(c["gap"]) <= tolerance] or [candidates[0]],
        "revenue_growth_bounds": list(revenue_growth_bounds),
        "operating_margin_bounds": list(operating_margin_bounds),
    }


def _implied_trajectory(result: Dict[str, Any]) -> Dict[str, Any]:
    """Expose solved trajectory endpoints without relabeling stage-one drivers as terminal values."""
    projections = result.get("revenue_projections") or []
    final = projections[-1] if projections and isinstance(projections[-1], dict) else {}
    terminal_growth = _as_finite_float(result.get("terminal_growth_rate"))
    terminal_margin = _as_finite_float(result.get("terminal_margin"))
    return {
        "implied_terminal_revenue_growth": terminal_growth,
        "implied_terminal_ebit_margin": terminal_margin,
        "implied_year_n_revenue": _as_finite_float(final.get("revenue")),
        "implied_year_n_ebit_margin": _as_finite_float(final.get("ebit_margin")),
        "implied_year_n_fcff": _as_finite_float(
            final.get("free_cash_flow", final.get("unlevered_free_cash_flow"))
        ),
        "implied_projection_horizon_years": int(result.get("projection_years") or len(projections)),
    }


def _cap_perpetual_growth(
    perpetual_growth_rate: float,
    risk_free_rate: Optional[float],
) -> tuple[float, bool]:
    if risk_free_rate is None:
        return perpetual_growth_rate, False
    return min(perpetual_growth_rate, risk_free_rate), perpetual_growth_rate > risk_free_rate


def _clamp_sales_to_capital(raw_ratio: Optional[float]) -> tuple[float, bool]:
    if raw_ratio is None or raw_ratio <= 0:
        return MIN_SALES_TO_CAPITAL_RATIO, True
    capped = max(MIN_SALES_TO_CAPITAL_RATIO, min(raw_ratio, MAX_SALES_TO_CAPITAL_RATIO))
    return capped, capped != raw_ratio


def _projected_ebit_margin(
    base_margin: float, 
    year: int, 
    projection_years: int,
    terminal_margin: float = MATURE_EBIT_MARGIN,
    scenario: str = "base"
) -> tuple[float, bool, int]:
    if base_margin > MATURE_EBIT_MARGIN * 2 and terminal_margin == MATURE_EBIT_MARGIN:
        # Dynamic terminal margin for high-margin businesses to prevent brutal compression
        terminal_margin = max(0.20, base_margin * 0.5)

    if scenario == "bull":
        terminal_margin = min(0.65, max(base_margin * 1.25, terminal_margin * 1.2))
        inflection_point = 8.0 if projection_years >= 15 else min(projection_years, (projection_years / 2.0) + 2)
        steepness_factor = 7.0
    elif scenario == "bear":
        terminal_margin = max(0.03, min(base_margin * 0.75, terminal_margin * 0.8))
        inflection_point = 4.0 if projection_years >= 15 else max(1.0, (projection_years / 2.0) - 2)
        steepness_factor = 13.0
    else:
        inflection_point = 6.0 if projection_years >= 15 else projection_years / 2.0
        steepness_factor = 10.0

    if projection_years <= 1:
        fade_progress = 1.0
    else:
        # S-Curve (Logistic) Decay
        steepness = steepness_factor / projection_years
        
        def L(t: float) -> float:
            return 1.0 / (1.0 + math.exp(-steepness * (t - inflection_point)))
            
        l_start = L(0.0)
        l_end = L(projection_years)
        l_current = L(year)
        
        # Normalize to ensure exactly 1.0 at projection_years
        fade_progress = (l_current - l_start) / (l_end - l_start)
        fade_progress = max(0.0, min(fade_progress, 1.0))

    margin_t = base_margin + (terminal_margin - base_margin) * fade_progress
    return margin_t, True, int(math.floor(inflection_point))


def _cap_reinvestment_to_nopat(
    raw_reinvestment: float,
    projected_nopat: float,
) -> tuple[float, float, bool]:
    max_reinvestment = max(projected_nopat, 0.0) * MAX_REINVESTMENT_TO_NOPAT
    projected_reinvestment = min(raw_reinvestment, max_reinvestment)
    return projected_reinvestment, max_reinvestment, projected_reinvestment != raw_reinvestment


def _terminal_discount_rate(discount_rate: float) -> tuple[float, bool]:
    capped = min(discount_rate, MAX_TERMINAL_WACC)
    return capped, capped != discount_rate


def calculate_rnd_capitalization(
    trailing_rnd: Optional[List[Any]],
    amortization_years: int,
) -> Dict[str, Any]:
    """Restate R&D using a straight-line research asset schedule."""
    values, validation_error = _validated_rnd_history(trailing_rnd)
    if amortization_years < 2:
        raise ValueError("R&D amortization life must be at least two years.")
    if len(values) < 3:
        raise ValueError(validation_error or "At least three annual R&D observations are required.")

    effective_life = min(amortization_years, len(values) - 1)
    current = values[-1]
    prior = values[-(effective_life + 1):-1]
    amortization = sum(prior) / effective_life
    research_asset = current
    for age, value in enumerate(reversed(prior), start=1):
        research_asset += value * max(effective_life - age, 0) / effective_life
    return {
        "current_year_rnd": current,
        "amortization_of_rnd": amortization,
        "capitalized_rnd_asset": research_asset,
        "rnd_amortization_period_years": effective_life,
        "requested_rnd_amortization_period_years": amortization_years,
        "rnd_history_years_used": effective_life + 1,
        "rnd_history_shortened": effective_life != amortization_years,
    }


def _smoothstep(progress: float) -> float:
    bounded = max(0.0, min(progress, 1.0))
    return bounded * bounded * (3.0 - 2.0 * bounded)


def calculate_growth_multistage_dcf(
    *,
    base_revenue: float,
    operating_income: float,
    tax_rate: float,
    shares_outstanding: float,
    total_debt: float,
    cash_and_equivalents: float,
    current_wacc: float,
    terminal_wacc: float,
    stage_1_growth_rate: float,
    perpetual_growth_rate: float,
    sales_to_capital: float,
    projection_years: int = 15,
    consensus_estimates: Optional[List[Dict[str, Any]]] = None,
    base_fiscal_year: Optional[int] = None,
    stable_ebit_margin: Optional[float] = None,  # accepted for call-site compatibility;
    # no longer used to select the terminal margin (see terminal margin precedence below).
    trailing_rnd: Optional[List[Any]] = None,
    rnd_amortization_years: int = 5,
    scenario: str = "base",
    apply_driver_override: bool = False,
    operating_margin_override: Optional[float] = None,
    adr_ratio: float = 1.0,
) -> Dict[str, Any]:
    """Consensus-anchored multi-stage FCFF model for growth businesses."""
    if base_revenue <= 0 or shares_outstanding <= 0:
        raise ValueError("Base revenue and shares outstanding must be positive.")
    if projection_years < 2:
        raise ValueError("Growth multi-stage DCF requires at least two projection years.")
    if not 0 <= tax_rate <= 0.60:
        raise ValueError("Tax rate must be between 0% and 60%.")
    if not 0.1 <= sales_to_capital <= 20.0:
        raise ValueError("Sales-to-capital must be between 0.1x and 20.0x.")
    if min(current_wacc, terminal_wacc) <= perpetual_growth_rate:
        raise ValueError("Current and terminal WACC must exceed perpetual growth.")

    scenario_suffix = {"bear": "Low", "base": "Avg", "bull": "High"}.get(scenario)
    if scenario_suffix is None:
        raise ValueError("Scenario must be bear, base, or bull.")

    rnd_fallback_reason = None
    try:
        rnd = calculate_rnd_capitalization(trailing_rnd, rnd_amortization_years)
    except ValueError as exc:
        rnd_fallback_reason = str(exc)
        rnd = {
            "current_year_rnd": None,
            "amortization_of_rnd": None,
            "capitalized_rnd_asset": None,
            "rnd_amortization_period_years": None,
            "requested_rnd_amortization_period_years": rnd_amortization_years,
            "rnd_history_years_used": 0,
            "rnd_history_shortened": False,
        }
    net_rnd = (
        rnd["current_year_rnd"] - rnd["amortization_of_rnd"]
        if rnd["current_year_rnd"] is not None and rnd["amortization_of_rnd"] is not None
        else 0.0
    )
    rnd_adjustment_margin = net_rnd / base_revenue
    adjusted_ebit = operating_income + net_rnd
    rnd_tax_benefit = net_rnd * tax_rate
    adjusted_after_tax_operating_income = adjusted_ebit * (1.0 - tax_rate) + rnd_tax_benefit

    estimates: list[dict[str, Any]] = []
    for row in consensus_estimates or []:
        try:
            year = int(str(row.get("date"))[:4])
            revenue = float(row[f"revenue{scenario_suffix}"])
            ebit = float(row[f"ebit{scenario_suffix}"])
        except (KeyError, TypeError, ValueError):
            continue
        if base_fiscal_year is not None and year <= base_fiscal_year:
            continue
        if revenue <= 0 or not np.isfinite(revenue) or not np.isfinite(ebit):
            continue
        estimates.append({**row, "year": year, "revenue": revenue, "ebit": ebit})
    estimates.sort(key=lambda item: item["year"])
    estimates = estimates[: min(5, projection_years)]
    consensus_available = len(estimates) >= 2
    anchor_years = len(estimates) if consensus_available else min(5, projection_years)

    reported_base_margin = operating_income / base_revenue
    base_margin = adjusted_ebit / base_revenue

    # Some providers backfill out-year EBIT/EBITDA estimates with a flat
    # percentage of revenue rather than genuine per-year analyst judgment
    # (revenue consensus keeps varying normally; margin consensus does not).
    # A margin trajectory that is bit-identical across every forecast year is
    # not credible as an independent forecast when it also diverges sharply
    # from the company's own current sourced operating margin. Trust the
    # revenue consensus (validated separately) either way; only reject the
    # margin dimension when both signals of unreliability are present.
    margin_consensus_rejected = False
    margin_consensus_rejection_reason = None
    if consensus_available and reported_base_margin > 0:
        consensus_margins = [row["ebit"] / row["revenue"] for row in estimates]
        margin_spread = max(consensus_margins) - min(consensus_margins)
        first_year_raw_margin = consensus_margins[0]
        relative_deviation = abs(first_year_raw_margin - reported_base_margin) / reported_base_margin
        if margin_spread < 0.005 and relative_deviation > MARGIN_CONSENSUS_MAX_RELATIVE_DEVIATION:
            margin_consensus_rejected = True
            margin_consensus_rejection_reason = (
                f"Consensus EBIT margin is flat ({first_year_raw_margin:.1%} across every "
                f"forecast year) and diverges {relative_deviation:.0%} from the company's "
                f"current sourced operating margin ({reported_base_margin:.1%}); it reads as a "
                "formulaic provider extrapolation rather than an independent forecast, so "
                "margin is instead held at the current sourced level. Revenue consensus is "
                "still used for growth."
            )
    margin_consensus_available = consensus_available and not margin_consensus_rejected

    consensus_anchor_growth = (
        estimates[0]["revenue"] / base_revenue - 1.0
        if consensus_available
        else stage_1_growth_rate
    )
    consensus_anchor_margin = (
        estimates[0]["ebit"] / estimates[0]["revenue"] + rnd_adjustment_margin
        if margin_consensus_available
        else base_margin
    )
    # Terminal margin precedence: a validated analyst consensus trajectory is a
    # sourced provider estimate of where margins are heading, so it outranks
    # every fallback. When no usable consensus exists (absent or rejected as
    # implausible above), hold the terminal margin at the company's own
    # latest sourced operating margin (base_margin) rather than a trailing
    # multi-year median. A multi-year median can include a crisis or outlier
    # year that no longer represents the current run-rate and understates a
    # business whose margin trend is already improving; the current sourced
    # margin is the most defensible steady-state anchor when there is no
    # forward-looking signal to lean on instead.
    if margin_consensus_available:
        target_margin = estimates[-1]["ebit"] / estimates[-1]["revenue"] + rnd_adjustment_margin
        terminal_margin_basis = (
            "final validated consensus year EBIT margin + capitalized R&D adjustment"
        )
    else:
        target_margin = base_margin
        terminal_margin_basis = (
            "current sourced operating margin + capitalized R&D adjustment; consensus was rejected as implausible"
            if margin_consensus_rejected
            else "current sourced operating margin + capitalized R&D adjustment; consensus was unavailable"
        )
    target_margin = max(-0.20, min(float(target_margin), 0.80))

    projections: list[dict[str, Any]] = []
    current_revenue = base_revenue
    cumulative_discount = 1.0
    present_value_fcfs = 0.0
    previous_growth = stage_1_growth_rate
    previous_margin = base_margin

    for year in range(1, projection_years + 1):
        previous_revenue = current_revenue
        if year <= anchor_years:
            forecast_stage = "consensus" if consensus_available else "filing_derived"
            source_status = "provider_estimate" if consensus_available else "estimated_with_warning"
            if consensus_available:
                estimate = estimates[year - 1]
                raw_growth = estimate["revenue"] / previous_revenue - 1.0
                reported_consensus_margin = estimate["ebit"] / estimate["revenue"]
                raw_margin = (
                    reported_consensus_margin + rnd_adjustment_margin
                    if margin_consensus_available
                    else base_margin
                )
            else:
                raw_growth = stage_1_growth_rate
                reported_consensus_margin = None
                raw_margin = base_margin
            if apply_driver_override:
                growth_shift = stage_1_growth_rate - consensus_anchor_growth
                margin_target = operating_margin_override if operating_margin_override is not None else raw_margin
                margin_shift = margin_target - consensus_anchor_margin
                growth = max(-0.50, min(raw_growth + growth_shift, 5.0))
                margin = max(-0.20, min(raw_margin + margin_shift, 0.95))
                current_revenue = previous_revenue * (1.0 + growth)
            else:
                growth = raw_growth
                margin = raw_margin
                current_revenue = estimate["revenue"] if consensus_available else previous_revenue * (1.0 + growth)
        else:
            forecast_stage = "transition"
            source_status = "app_derived"
            progress = (year - anchor_years) / (projection_years - anchor_years)
            fade = _smoothstep(progress)
            growth = previous_growth + (perpetual_growth_rate - previous_growth) * fade
            margin = previous_margin + (target_margin - previous_margin) * fade
            current_revenue = previous_revenue * (1.0 + growth)

        if year <= anchor_years:
            previous_growth = growth
            previous_margin = margin
        transition_progress = (
            0.0 if year <= anchor_years
            else (year - anchor_years) / (projection_years - anchor_years)
        )
        year_wacc = current_wacc + (terminal_wacc - current_wacc) * _smoothstep(transition_progress)
        ebit = current_revenue * margin
        # The forecast EBIT margin already includes the capitalized-R&D EBIT
        # adjustment. Preserve the matching tax benefit in every forecast
        # year's NOPAT as required by the valuation calculation specification;
        # otherwise the adjustment is only partially applied outside year 0.
        nopat = ebit * (1.0 - tax_rate) + rnd_tax_benefit
        revenue_change = current_revenue - previous_revenue
        reinvestment = max(revenue_change, 0.0) / sales_to_capital
        free_cash_flow = nopat - reinvestment
        cumulative_discount *= 1.0 + year_wacc
        present_value = free_cash_flow / cumulative_discount
        present_value_fcfs += present_value
        projections.append({
            "year": year,
            "fiscal_year": (
                estimates[year - 1]["year"]
                if consensus_available and year <= anchor_years
                else (base_fiscal_year + year if base_fiscal_year is not None else None)
            ),
            "forecast_stage": forecast_stage,
            "source_status": source_status,
            "revenue": current_revenue,
            "growth_rate": growth,
            "revenue_growth": growth,
            "ebit_margin": margin,
            "ebit": ebit,
            "reported_consensus_ebit": (
                estimate["ebit"] if consensus_available and year <= anchor_years else None
            ),
            "reported_consensus_ebit_margin": (
                reported_consensus_margin if consensus_available and year <= anchor_years else None
            ),
            "rnd_ebit_margin_adjustment": (
                rnd_adjustment_margin if rnd_fallback_reason is None else None
            ),
            "tax_rate": tax_rate,
            "rnd_tax_benefit": rnd_tax_benefit if rnd_fallback_reason is None else None,
            "nopat": nopat,
            "sales_to_capital_ratio": sales_to_capital,
            "reinvestment": reinvestment,
            "capital_deduction_label": "Reinvestment",
            "capital_deduction_value": reinvestment,
            "free_cash_flow": free_cash_flow,
            "unlevered_free_cash_flow": free_cash_flow,
            "wacc": year_wacc,
            "discount_factor": 1.0 / cumulative_discount,
            "present_value": present_value,
            "shares_outstanding": shares_outstanding,
            "source_refs": (
                ["fmp:analyst-estimates", "app:capitalized-rnd-schedule"]
                if consensus_available and year <= anchor_years
                else ["app:smoothstep-transition", "sec:historical-financials"]
            ),
        })

    final = projections[-1]
    terminal_roic = terminal_wacc
    terminal_reinvestment_rate = perpetual_growth_rate / terminal_roic
    terminal_revenue = final["revenue"] * (1.0 + perpetual_growth_rate)
    terminal_ebit = terminal_revenue * target_margin
    terminal_nopat = terminal_ebit * (1.0 - tax_rate) + rnd_tax_benefit
    terminal_fcf = terminal_nopat * (1.0 - terminal_reinvestment_rate)
    terminal_value = terminal_fcf / (terminal_wacc - perpetual_growth_rate)
    present_value_tv = terminal_value / cumulative_discount
    enterprise_value = present_value_fcfs + present_value_tv
    equity_value = enterprise_value - total_debt + cash_and_equivalents
    computed_fair_value = normalize_equity_value_per_traded_share(
        equity_value, shares_outstanding, adr_ratio
    )

    return {
        "methodology": "Capitalized R&D DCF" if rnd_fallback_reason is None else "Standard Driver-Based DCF",
        "model_version": "growth_multistage_fcff_v3",
        "forecast_basis": "consensus_and_filings" if consensus_available else "filings_only",
        "consensus_coverage": {
            "status": "available" if consensus_available else "unavailable",
            "year_count": len(estimates) if consensus_available else 0,
            "years": [row["year"] for row in estimates] if consensus_available else [],
            "scenario": scenario,
        },
        "margin_consensus_rejected": margin_consensus_rejected,
        "margin_consensus_rejection_reason": margin_consensus_rejection_reason,
        "base_revenue": base_revenue,
        "base_ebit": operating_income,
        "base_ebit_margin": base_margin,
        "reported_base_ebit_margin": reported_base_margin,
        "adjusted_ebit": adjusted_ebit,
        "adjusted_after_tax_operating_income": adjusted_after_tax_operating_income,
        "rnd_tax_benefit": rnd_tax_benefit,
        "rnd_ebit_adjustment": net_rnd,
        "rnd_ebit_margin_adjustment": rnd_adjustment_margin,
        "rnd_nopat_adjustment": net_rnd,
        "rnd_capitalization_applied": rnd_fallback_reason is None,
        "fallback_reason": rnd_fallback_reason,
        "rnd_history_currency": "USD",
        **rnd,
        "sales_to_capital_ratio": sales_to_capital,
        "sales_to_capital_ratio_capped": False,
        "discount_rate": current_wacc,
        "discount_rate_basis": "current_wacc_fading_to_mature_wacc",
        "terminal_discount_rate": terminal_wacc,
        "terminal_growth_rate": perpetual_growth_rate,
        "terminal_roic": terminal_roic,
        "terminal_reinvestment_rate": terminal_reinvestment_rate,
        "terminal_margin": target_margin,
        "terminal_margin_basis": terminal_margin_basis,
        "terminal_revenue": terminal_revenue,
        "terminal_ebit": terminal_ebit,
        "terminal_nopat": terminal_nopat,
        "terminal_fcf": terminal_fcf,
        "terminal_value": terminal_value,
        "present_value_fcfs": present_value_fcfs,
        "present_value_terminal_value": present_value_tv,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "computed_fair_value": computed_fair_value,
        "projection_years": projection_years,
        "revenue_projections": projections,
        "fcf_projections": [row["free_cash_flow"] for row in projections],
        "shares_outstanding": shares_outstanding,
        "total_debt": total_debt,
        "cash": cash_and_equivalents,
        "adr_ratio": adr_ratio,
        "adr_ratio_applied": False,
        "share_normalization_basis": "equity_value_usd / current_point_in_time_shares",
        "harvest_start_year": anchor_years + 1,
    }


def _stage_growth_rate(
    year: int,
    projection_years: int,
    stage_1_growth_rate: float,
    perpetual_growth_rate: float,
) -> float:
    if projection_years <= 3 or year <= 3:
        return stage_1_growth_rate
    fade_progress = (year - 3) / (projection_years - 3)
    return stage_1_growth_rate + (
        perpetual_growth_rate - stage_1_growth_rate
    ) * fade_progress


def _project_driver_based_dcf(
    *,
    base_revenue: float,
    base_ebit: float,
    tax_rate: float,
    historical_reinvestment: float,
    shares_outstanding: float,
    adr_ratio: float = 1.0,
    total_debt: float,
    cash_and_equivalents: float,
    discount_rate: float,
    stage_1_growth_rate: float,
    perpetual_growth_rate: float,
    projection_years: int,
    historical_change_in_revenue: Optional[float] = None,
    risk_free_rate: Optional[float] = None,
    scenario: str = "base",
) -> Dict[str, Any]:
    if shares_outstanding == 0:
        raise ValueError("Shares outstanding cannot be zero.")
    if base_revenue <= 0:
        raise ValueError("Base revenue must be positive.")
    if projection_years <= 0:
        raise ValueError("Projection years must be positive.")
    if not 0.0 <= tax_rate <= 0.25:
        raise ValueError("Tax rate must be capped between 0% and 25%.")

    capped_perpetual_growth, terminal_growth_capped = _cap_perpetual_growth(
        perpetual_growth_rate,
        risk_free_rate,
    )
    if discount_rate <= capped_perpetual_growth:
        raise ValueError("Discount rate must be greater than terminal growth rate.")

    revenue_delta = (
        historical_change_in_revenue
        if historical_change_in_revenue is not None
        else base_revenue * stage_1_growth_rate
    )
    raw_sales_to_capital = (
        revenue_delta / historical_reinvestment
        if historical_reinvestment != 0
        else None
    )
    sales_to_capital_ratio, sales_to_capital_capped = _clamp_sales_to_capital(
        raw_sales_to_capital
    )

    base_ebit_margin = base_ebit / base_revenue
    revenue_projections = []
    fcf_projections = []
    current_revenue = base_revenue
    for year in range(1, projection_years + 1):
        growth_rate = _stage_growth_rate(
            year,
            projection_years,
            stage_1_growth_rate,
            capped_perpetual_growth,
        )
        previous_revenue = current_revenue
        current_revenue = previous_revenue * (1 + growth_rate)
        projected_change_in_revenue = current_revenue - previous_revenue
        projected_ebit_margin, ebit_margin_floor_applied, harvest_start_year = _projected_ebit_margin(
            base_ebit_margin,
            year,
            projection_years,
            scenario=scenario,
        )
        projected_ebit = current_revenue * projected_ebit_margin
        projected_nopat = projected_ebit * (1 - tax_rate)
        raw_reinvestment = (
            max(projected_change_in_revenue, 0.0) / sales_to_capital_ratio
        )
        (
            projected_reinvestment,
            max_reinvestment,
            reinvestment_cap_applied,
        ) = _cap_reinvestment_to_nopat(raw_reinvestment, projected_nopat)
        projected_fcf = projected_nopat - projected_reinvestment
        fcf_projections.append(projected_fcf)
        revenue_projections.append(
            {
                "year": year,
                "revenue": current_revenue,
                "growth_rate": growth_rate,
                "ebit_margin": projected_ebit_margin,
                "ebit": projected_ebit,
                "tax_rate": tax_rate,
                "nopat": projected_nopat,
                "sales_to_capital_ratio": sales_to_capital_ratio,
                "raw_reinvestment": raw_reinvestment,
                "max_reinvestment": max_reinvestment,
                "reinvestment_cap_applied": reinvestment_cap_applied,
                "reinvestment": projected_reinvestment,
                "free_cash_flow": projected_fcf,
                "ebit_margin_floor_applied": ebit_margin_floor_applied,
            }
        )

    terminal_fcf = fcf_projections[-1]
    terminal_discount_rate, terminal_discount_rate_capped = _terminal_discount_rate(
        discount_rate
    )
    if terminal_discount_rate <= capped_perpetual_growth:
        raise ValueError("Terminal discount rate must be greater than terminal growth rate.")
    terminal_value = (
        terminal_fcf * (1 + capped_perpetual_growth)
    ) / (terminal_discount_rate - capped_perpetual_growth)
    present_value_fcfs = sum(
        fcf / ((1 + discount_rate) ** (index + 1))
        for index, fcf in enumerate(fcf_projections)
    )
    present_value_tv = terminal_value / ((1 + discount_rate) ** projection_years)
    enterprise_value = present_value_fcfs + present_value_tv
    equity_value = enterprise_value - total_debt + cash_and_equivalents
    computed_fair_value = normalize_equity_value_per_traded_share(
        equity_value, shares_outstanding, adr_ratio
    )

    return {
        "base_ebit": base_ebit,
        "base_ebit_margin": base_ebit_margin,
        "base_nopat": base_ebit * (1 - tax_rate),
        "historical_reinvestment": historical_reinvestment,
        "historical_change_in_revenue": revenue_delta,
        "raw_sales_to_capital_ratio": raw_sales_to_capital,
        "sales_to_capital_ratio": sales_to_capital_ratio,
        "sales_to_capital_ratio_capped": sales_to_capital_capped,
        "terminal_growth_rate": capped_perpetual_growth,
        "terminal_growth_capped_to_risk_free_rate": terminal_growth_capped,
        "terminal_discount_rate": terminal_discount_rate,
        "terminal_discount_rate_capped": terminal_discount_rate_capped,
        "fcf_projections": fcf_projections,
        "revenue_projections": revenue_projections,
        "projection_years": projection_years,
        "terminal_value": terminal_value,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "computed_fair_value": computed_fair_value,
        "raw_value_per_ordinary_share": equity_value / shares_outstanding,
        "adr_ratio": adr_ratio,
        "adr_ratio_applied": False,
        "share_normalization_basis": "equity_value_usd / listed_shares",
        "harvest_start_year": harvest_start_year if projection_years > 1 else None,
    }


def calculate_standard_driver_dcf(
    *,
    base_revenue: float,
    ebit_margin: float,
    tax_rate: float,
    capex: float,
    depreciation_amortization: float,
    change_in_nwc: float,
    shares_outstanding: float,
    adr_ratio: float = 1.0,
    total_debt: float,
    cash_and_equivalents: float,
    wacc: float,
    stage_1_growth_rate: float,
    perpetual_growth_rate: float = 0.02,
    projection_years: int = 15,
    historical_change_in_revenue: Optional[float] = None,
    risk_free_rate: Optional[float] = None,
    scenario: str = "base",
) -> Dict[str, Any]:
    base_ebit = base_revenue * ebit_margin
    historical_reinvestment = capex - depreciation_amortization + change_in_nwc
    result = _project_driver_based_dcf(
        base_revenue=base_revenue,
        base_ebit=base_ebit,
        tax_rate=tax_rate,
        historical_reinvestment=historical_reinvestment,
        shares_outstanding=shares_outstanding,
        adr_ratio=adr_ratio,
        total_debt=total_debt,
        cash_and_equivalents=cash_and_equivalents,
        discount_rate=wacc,
        stage_1_growth_rate=stage_1_growth_rate,
        perpetual_growth_rate=perpetual_growth_rate,
        projection_years=projection_years,
        historical_change_in_revenue=historical_change_in_revenue,
        risk_free_rate=risk_free_rate,
        scenario=scenario,
    )
    result.update(
        {
            "methodology": "Standard Driver-Based DCF",
            "capex": capex,
            "depreciation_amortization": depreciation_amortization,
            "change_in_nwc": change_in_nwc,
            "discount_rate": wacc,
            "discount_rate_basis": "true_wacc",
        }
    )
    return result


def calculate_capitalized_rnd(
    *,
    base_revenue: float,
    operating_income: float,
    tax_rate: float,
    capex: float,
    depreciation_amortization: float,
    change_in_nwc: float,
    shares_outstanding: float,
    adr_ratio: float = 1.0,
    total_debt: float,
    cash_and_equivalents: float,
    wacc: float,
    stage_1_growth_rate: float,
    perpetual_growth_rate: float = 0.02,
    projection_years: int = 15,
    trailing_rnd: Optional[List[Any]] = None,
    historical_change_in_revenue: Optional[float] = None,
    risk_free_rate: Optional[float] = None,
    scenario: str = "base",
) -> Dict[str, Any]:
    rnd_values, rnd_validation_error = _validated_rnd_history(trailing_rnd)
    if len(rnd_values) < 3:
        fallback = calculate_standard_driver_dcf(
            base_revenue=base_revenue,
            ebit_margin=operating_income / base_revenue,
            tax_rate=tax_rate,
            capex=capex,
            depreciation_amortization=depreciation_amortization,
            change_in_nwc=change_in_nwc,
            shares_outstanding=shares_outstanding,
            adr_ratio=adr_ratio,
            total_debt=total_debt,
            cash_and_equivalents=cash_and_equivalents,
            wacc=wacc,
            stage_1_growth_rate=stage_1_growth_rate,
            perpetual_growth_rate=perpetual_growth_rate,
            projection_years=projection_years,
            historical_change_in_revenue=historical_change_in_revenue,
            risk_free_rate=risk_free_rate,
            scenario=scenario,
        )
        fallback["methodology"] = "Standard Driver-Based DCF"
        fallback["fallback_reason"] = "historical R&D data incomplete or not normalized"
        fallback["rnd_history_validation_error"] = rnd_validation_error or "fewer than three annual observations"
        fallback["rnd_capitalization_applied"] = False
        return fallback

    latest_three_rnd = rnd_values[-3:]
    current_year_rnd = latest_three_rnd[-1]
    amortization_of_rnd = sum(latest_three_rnd) / 3
    capitalized_rnd_asset = (
        latest_three_rnd[-1] * (2 / 3)
        + latest_three_rnd[-2] * (1 / 3)
    )
    adjusted_ebit = operating_income + current_year_rnd - amortization_of_rnd
    adjusted_reinvestment = (
        capex - depreciation_amortization + change_in_nwc + current_year_rnd
    )
    result = _project_driver_based_dcf(
        base_revenue=base_revenue,
        base_ebit=adjusted_ebit,
        tax_rate=tax_rate,
        historical_reinvestment=adjusted_reinvestment,
        shares_outstanding=shares_outstanding,
        adr_ratio=adr_ratio,
        total_debt=total_debt,
        cash_and_equivalents=cash_and_equivalents,
        discount_rate=wacc,
        stage_1_growth_rate=stage_1_growth_rate,
        perpetual_growth_rate=perpetual_growth_rate,
        projection_years=projection_years,
        historical_change_in_revenue=historical_change_in_revenue,
        risk_free_rate=risk_free_rate,
        scenario=scenario,
    )
    result.update(
        {
            "methodology": "Capitalized R&D DCF",
            "operating_income": operating_income,
            "current_year_rnd": current_year_rnd,
            "rnd_amortization_period_years": 3,
            "amortization_of_rnd": amortization_of_rnd,
            "capitalized_rnd_asset": capitalized_rnd_asset,
            "rnd_ebit_adjustment": current_year_rnd - amortization_of_rnd,
            "rnd_nopat_adjustment": (current_year_rnd - amortization_of_rnd) * (1 - tax_rate),
            "adjusted_ebit": adjusted_ebit,
            "adjusted_nopat": adjusted_ebit * (1 - tax_rate),
            "adjusted_reinvestment": adjusted_reinvestment,
            "discount_rate": wacc,
            "discount_rate_basis": "true_wacc",
            "rnd_capitalization_applied": True,
            "rnd_history_years_used": 3,
            "rnd_history_currency": "USD",
        }
    )
    return result


def calculate_fcfe(
    *,
    net_income: float,
    total_assets: float,
    shares_outstanding: float,
    adr_ratio: float = 1.0,
    cost_of_equity: float,
    tier1_capital_ratio: Optional[float] = None,
    net_income_growth_rate: float = 0.02,
    asset_growth_rate: Optional[float] = None,
    perpetual_growth_rate: float = 0.02,
    projection_years: int = 15,
    risk_free_rate: Optional[float] = None,
) -> Dict[str, Any]:
    if shares_outstanding == 0:
        raise ValueError("Shares outstanding cannot be zero.")
    if total_assets <= 0:
        raise ValueError("Total assets must be positive.")

    selected_tier1 = (
        tier1_capital_ratio
        if tier1_capital_ratio is not None
        else DEFAULT_TIER1_CAPITAL_RATIO
    )
    if selected_tier1 <= 0:
        selected_tier1 = DEFAULT_TIER1_CAPITAL_RATIO

    capped_perpetual_growth, terminal_growth_capped = _cap_perpetual_growth(
        perpetual_growth_rate,
        risk_free_rate,
    )
    if cost_of_equity <= capped_perpetual_growth:
        raise ValueError("Cost of equity must be greater than terminal growth rate.")

    selected_asset_growth = (
        asset_growth_rate
        if asset_growth_rate is not None
        else net_income_growth_rate
    )
    fcfe_projections = []
    asset_projections = []
    current_assets = total_assets
    current_net_income = net_income
    for year in range(1, projection_years + 1):
        growth_rate = _stage_growth_rate(
            year,
            projection_years,
            net_income_growth_rate,
            capped_perpetual_growth,
        )
        asset_growth = _stage_growth_rate(
            year,
            projection_years,
            selected_asset_growth,
            capped_perpetual_growth,
        )
        previous_assets = current_assets
        current_assets = previous_assets * (1 + asset_growth)
        current_net_income = current_net_income * (1 + growth_rate)
        change_in_total_assets = current_assets - previous_assets
        required_capital = change_in_total_assets * selected_tier1
        fcfe = current_net_income - required_capital
        fcfe_projections.append(fcfe)
        asset_projections.append(
            {
                "year": year,
                "net_income": current_net_income,
                "net_income_growth_rate": growth_rate,
                "total_assets": current_assets,
                "asset_growth_rate": asset_growth,
                "change_in_total_assets": change_in_total_assets,
                "tier1_capital_ratio": selected_tier1,
                "required_capital": required_capital,
                "fcfe": fcfe,
            }
        )

    terminal_fcfe = fcfe_projections[-1]
    terminal_value = (
        terminal_fcfe * (1 + capped_perpetual_growth)
    ) / (cost_of_equity - capped_perpetual_growth)
    present_value_fcfe = sum(
        fcfe / ((1 + cost_of_equity) ** (index + 1))
        for index, fcfe in enumerate(fcfe_projections)
    )
    present_value_terminal = terminal_value / ((1 + cost_of_equity) ** projection_years)
    equity_value = present_value_fcfe + present_value_terminal
    raw_value_per_ordinary_share = equity_value / shares_outstanding
    final_intrinsic_value_per_adr = raw_value_per_ordinary_share
    return {
        "methodology": "Regulatory FCFE",
        "net_income": net_income,
        "total_assets": total_assets,
        "tier1_capital_ratio": selected_tier1,
        "tier1_capital_ratio_defaulted": tier1_capital_ratio is None,
        "discount_rate": cost_of_equity,
        "discount_rate_basis": "cost_of_equity_only",
        "wacc_used": False,
        "terminal_growth_rate": capped_perpetual_growth,
        "terminal_growth_capped_to_risk_free_rate": terminal_growth_capped,
        "fcfe_projections": fcfe_projections,
        "asset_projections": asset_projections,
        "terminal_value": terminal_value,
        "present_value_fcfe": present_value_fcfe,
        "present_value_terminal_value": present_value_terminal,
        "equity_value": equity_value,
        "computed_fair_value": final_intrinsic_value_per_adr,
        "raw_value_per_ordinary_share": raw_value_per_ordinary_share,
        "adr_ratio": adr_ratio,
        "share_normalization_basis": "equity_value_usd / listed_shares",
    }


def calculate_normalized_median_dcf(
    *,
    base_revenue: float,
    historical_operating_margins: List[float],
    tax_rate: float,
    capex: float,
    depreciation_amortization: float,
    change_in_nwc: float,
    shares_outstanding: float,
    adr_ratio: float = 1.0,
    total_debt: float,
    cash_and_equivalents: float,
    wacc: float,
    stage_1_growth_rate: float,
    perpetual_growth_rate: float = 0.02,
    projection_years: int = 15,
    historical_change_in_revenue: Optional[float] = None,
    risk_free_rate: Optional[float] = None,
    scenario: str = "base",
) -> Dict[str, Any]:
    valid_margins = [
        value
        for value in historical_operating_margins
        if value is not None and -1.0 < value < 1.0
    ]
    if not valid_margins:
        raise ValueError("Historical operating margins are required.")

    normalized_margin = median(valid_margins)
    normalized_base_ebit = base_revenue * normalized_margin
    result = _project_driver_based_dcf(
        base_revenue=base_revenue,
        base_ebit=normalized_base_ebit,
        tax_rate=tax_rate,
        historical_reinvestment=capex - depreciation_amortization + change_in_nwc,
        shares_outstanding=shares_outstanding,
        adr_ratio=adr_ratio,
        total_debt=total_debt,
        cash_and_equivalents=cash_and_equivalents,
        discount_rate=wacc,
        stage_1_growth_rate=stage_1_growth_rate,
        perpetual_growth_rate=perpetual_growth_rate,
        projection_years=projection_years,
        historical_change_in_revenue=historical_change_in_revenue,
        risk_free_rate=risk_free_rate,
        scenario=scenario,
    )
    result.update(
        {
            "methodology": "Normalized Median DCF",
            "normalized_margin": normalized_margin,
            "normalized_base_ebit": normalized_base_ebit,
            "historical_operating_margins": valid_margins,
            "discount_rate": wacc,
            "discount_rate_basis": "true_wacc",
        }
    )
    return result

def calculate_asset_based_valuation(
    total_assets: float,
    total_liabilities: float,
    goodwill: float,
    intangible_assets: float,
    shares_outstanding: float
) -> Dict[str, Any]:
    if shares_outstanding == 0:
        raise ValueError("Shares outstanding cannot be zero.")
        
    nav = total_assets - total_liabilities
    tangible_nav = nav - goodwill - intangible_assets
    
    standard_nav_per_share = nav / shares_outstanding
    tangible_net_net_per_share = tangible_nav / shares_outstanding
    
    return {
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "goodwill": goodwill,
        "intangible_assets": intangible_assets,
        "nav": nav,
        "tangible_nav": tangible_nav,
        "standard_nav_per_share": standard_nav_per_share,
        "tangible_net_net_per_share": tangible_net_net_per_share,
        "computed_fair_value": tangible_net_net_per_share, # conservative choice for default
        "calculation_basis": {
            "nav": "total_assets - total_liabilities",
            "tangible_nav": "nav - goodwill - intangible_assets",
            "standard_nav_per_share": "nav / listed_shares",
            "tangible_net_net_per_share": "tangible_nav / listed_shares",
            "default_fair_value": "tangible_net_net_per_share",
        },
    }

def calculate_dcf_valuation(
    *,
    base_revenue: float,
    ebit_margin: float,
    tax_rate: float,
    reinvestment_rate: float,
    shares_outstanding: float,
    adr_ratio: float = 1.0,
    total_debt: float,
    cash_and_equivalents: float,
    wacc: float,
    stage_1_growth_rate: float,
    perpetual_growth_rate: float = 0.02,
    projection_years: int = 15,
    base_fcf: Optional[float] = None,
    cash_floor_per_share: Optional[float] = None,
    normalization_fcf_margin: float = 0.03,
) -> Dict[str, Any]:
    if shares_outstanding == 0:
        raise ValueError("Shares outstanding cannot be zero.")

    if base_revenue <= 0:
        raise ValueError("Base revenue must be positive.")

    if wacc <= perpetual_growth_rate:
        raise ValueError("WACC must be greater than perpetual growth rate.")

    if projection_years <= 0:
        raise ValueError("Projection years must be positive.")

    if not -1.0 < ebit_margin < 1.0:
        raise ValueError("EBIT margin must be expressed as a decimal rate.")

    if not 0.0 <= tax_rate <= 0.25:
        raise ValueError("Tax rate must be capped between 0% and 25%.")

    if reinvestment_rate < 0:
        raise ValueError("Reinvestment rate cannot be negative.")

    fcf_0 = base_fcf if base_fcf is not None else base_revenue * max(ebit_margin * (1 - tax_rate), 0)
    warnings: list[str] = []
    normalization_applied = False
    normalized_fcf_floor = base_revenue * normalization_fcf_margin
    historical_fcf_was_negative = fcf_0 < 0
    if historical_fcf_was_negative and normalized_fcf_floor > fcf_0:
        fcf_0 = normalized_fcf_floor
        normalization_applied = True
        warnings.append(
            "Negative historical FCF smoothing applied using disclosed model FCF margin floor."
        )

    revenue_projections = []
    fcf_projections = []
    current_revenue = base_revenue
    for year in range(1, projection_years + 1):
        if projection_years <= 3 or year <= 3:
            dynamic_growth = stage_1_growth_rate
        else:
            fade_progress = (year - 3) / (projection_years - 3)
            dynamic_growth = stage_1_growth_rate + (
                perpetual_growth_rate - stage_1_growth_rate
            ) * fade_progress

        previous_revenue = current_revenue
        current_revenue = previous_revenue * (1 + dynamic_growth)
        revenue_delta = current_revenue - previous_revenue
        projected_ebit_margin, ebit_margin_floor_applied = _projected_ebit_margin(
            ebit_margin,
            year,
            projection_years,
        )
        ebit = current_revenue * projected_ebit_margin
        nopat = ebit * (1 - tax_rate)
        raw_reinvestment = max(revenue_delta, 0) * reinvestment_rate
        reinvestment, max_reinvestment, reinvestment_cap_applied = _cap_reinvestment_to_nopat(
            raw_reinvestment,
            nopat,
        )
        fcf = nopat - reinvestment

        if fcf < 0 and historical_fcf_was_negative:
            fcf = min(fcf_0, normalized_fcf_floor)
            normalization_applied = True
            warnings.append(
                "Projected FCF floor applied to avoid a terminal value driven by abnormal reinvestment."
            )

        fcf_projections.append(fcf)
        revenue_projections.append({
            "year": year,
            "revenue": current_revenue,
            "growth_rate": dynamic_growth,
            "ebit_margin": projected_ebit_margin,
            "ebit": ebit,
            "tax_rate": tax_rate,
            "nopat": nopat,
            "reinvestment_rate": reinvestment_rate,
            "raw_reinvestment": raw_reinvestment,
            "max_reinvestment": max_reinvestment,
            "reinvestment_cap_applied": reinvestment_cap_applied,
            "reinvestment": reinvestment,
            "free_cash_flow": fcf,
            "ebit_margin_floor_applied": ebit_margin_floor_applied,
        })

    terminal_fcf = fcf_projections[-1]
    terminal_wacc, terminal_wacc_capped = _terminal_discount_rate(wacc)
    if terminal_wacc <= perpetual_growth_rate:
        raise ValueError("Terminal WACC must be greater than perpetual growth rate.")
    terminal_value = (terminal_fcf * (1 + perpetual_growth_rate)) / (terminal_wacc - perpetual_growth_rate)
    
    present_value_fcfs = sum([fcf / ((1 + wacc) ** (t + 1)) for t, fcf in enumerate(fcf_projections)])
    present_value_tv = terminal_value / ((1 + wacc) ** projection_years)
    
    enterprise_value = present_value_fcfs + present_value_tv
    equity_value = enterprise_value - total_debt + cash_and_equivalents
    raw_value_per_ordinary_share = equity_value / shares_outstanding
    final_intrinsic_value_per_adr = raw_value_per_ordinary_share
    distressed_floor_applied = False
    if cash_floor_per_share is not None and final_intrinsic_value_per_adr < cash_floor_per_share:
        final_intrinsic_value_per_adr = cash_floor_per_share
        distressed_floor_applied = True
        warnings.append("Distressed Valuation Floor: DCF value fell below cash/share.")
    
    return {
        "fcf_0": fcf_0,
        "fcf_projections": fcf_projections,
        "revenue_projections": revenue_projections,
        "projection_years": projection_years,
        "terminal_discount_rate": terminal_wacc,
        "terminal_discount_rate_capped": terminal_wacc_capped,
        "terminal_value": terminal_value,
        "enterprise_value": enterprise_value,
        "equity_value": equity_value,
        "raw_computed_fair_value": raw_value_per_ordinary_share,
        "computed_fair_value": final_intrinsic_value_per_adr,
        "adr_ratio": adr_ratio,
        "adr_ratio_applied": False,
        "distressed_valuation_floor_applied": distressed_floor_applied,
        "cash_floor_per_share": cash_floor_per_share,
        "fcf_normalization_applied": normalization_applied,
        "warnings": list(dict.fromkeys(warnings)),
    }

def calculate_ddm_valuation(
    dividends_paid: float,
    shares_outstanding: float,
    historical_dividends: List[float],
    cost_of_equity: float,
    adr_ratio: float = 1.0,
) -> Dict[str, Any]:
    if not dividends_paid or dividends_paid == 0:
        return {
            "status": "DDM_INAPPLICABLE",
            "computed_fair_value": None,
            "adr_ratio": adr_ratio,
            "adr_ratio_applied": False,
            "calculation_basis": "DDM unavailable because no sourced dividend distribution was reported.",
        }
        
    if shares_outstanding == 0:
        raise ValueError("Shares outstanding cannot be zero.")
        
    d_0 = dividends_paid / shares_outstanding
    
    if len(historical_dividends) >= 2:
        start_div = historical_dividends[0]
        end_div = historical_dividends[-1]
        years = len(historical_dividends) - 1
        if start_div > 0:
            g_div = (end_div / start_div) ** (1 / years) - 1
        else:
            g_div = 0
    else:
        g_div = 0
        
    if cost_of_equity <= g_div:
        return {
            "status": "DDM_INAPPLICABLE_GROWTH_RATE",
            "computed_fair_value": None,
            "annual_dividend_per_share": d_0,
            "dividend_growth_cagr": g_div,
            "adr_ratio": adr_ratio,
            "adr_ratio_applied": False,
            "calculation_basis": "DDM unavailable because dividend growth is not below cost of equity.",
        }
        
    raw_value_per_ordinary_share = (d_0 * (1 + g_div)) / (cost_of_equity - g_div)
    final_intrinsic_value_per_adr = raw_value_per_ordinary_share
    
    return {
        "status": "APPLICABLE",
        "annual_dividend_per_share": d_0,
        "dividend_growth_cagr": g_div,
        "computed_fair_value": final_intrinsic_value_per_adr,
        "adr_ratio": adr_ratio,
        "adr_ratio_applied": False,
        "calculation_basis": {
            "annual_dividend_per_share": "dividends_paid / listed_shares",
            "dividend_growth_cagr": "(ending_dividend / beginning_dividend)^(1 / years) - 1",
            "computed_fair_value": "D0 * (1 + dividend_growth_cagr) / (cost_of_equity - dividend_growth_cagr)",
        },
    }

def calculate_relative_valuation(
    target_eps: float,
    target_bvps: float,
    target_ebitda: Optional[float],
    target_debt: Optional[float],
    target_cash: Optional[float],
    shares_outstanding: float,
    peers: List[Dict[str, float]],
    adr_ratio: float = 1.0,
    is_financials: bool = False,
) -> Dict[str, Any]:
    if not peers:
        raise ValueError("Peer list cannot be empty.")
    if shares_outstanding == 0:
        raise ValueError("Shares outstanding cannot be zero.")
        
    valid_pe = [p["pe"] for p in peers if p.get("pe") is not None and p["pe"] > 0]
    valid_pb = [p["pb"] for p in peers if p.get("pb") is not None and p["pb"] > 0]
    valid_ev_ebitda = [
        p["ev_ebitda"]
        for p in peers
        if p.get("ev_ebitda") is not None and p["ev_ebitda"] > 0
    ]

    def _iqr_filtered(values: list[float]) -> list[float]:
        """Remove statistical outliers using a two-pass filter.

        Pass 1 – Tukey IQR fence (1.5× IQR): effective when the dataset
        is large enough for quartiles to be meaningful.
        Pass 2 – 10× median cap: catches extreme outliers that survive
        IQR when the outlier itself dominates a quartile boundary
        (common with ≤ 5 peers).

        Both passes run sequentially; neither is a mere fallback.
        """
        if len(values) < 3:
            return values
        result = list(values)
        # --- Pass 1: IQR fence ---
        s = sorted(result)
        n = len(s)
        q1 = s[n // 4]
        q3 = s[(3 * n) // 4]
        iqr = q3 - q1
        if iqr > 0:
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            filtered = [v for v in result if lower <= v <= upper]
            if filtered:
                result = filtered
        # --- Pass 2: 10× median cap ---
        from statistics import median as _med
        med = _med(sorted(result))
        if med > 0:
            filtered = [v for v in result if v <= 10 * med]
            if filtered:
                result = filtered
        return result

    filtered_pe = _iqr_filtered(valid_pe)
    filtered_pb = _iqr_filtered(valid_pb)
    filtered_ev_ebitda = _iqr_filtered(valid_ev_ebitda)

    from statistics import median
    avg_pe = median(filtered_pe) if filtered_pe else None
    avg_pb = median(filtered_pb) if filtered_pb else None
    avg_ev_ebitda = median(filtered_ev_ebitda) if filtered_ev_ebitda else None
    
    fv_pe = avg_pe * target_eps if avg_pe is not None and target_eps > 0 else None
    fv_pb = avg_pb * target_bvps if avg_pb is not None and target_bvps > 0 else None
    
    if not is_financials and avg_ev_ebitda is not None and target_ebitda is not None and target_ebitda > 0 and target_debt is not None and target_cash is not None:
        ev = avg_ev_ebitda * target_ebitda
        fv_ev_ebitda = (ev - target_debt + target_cash) / shares_outstanding
    else:
        fv_ev_ebitda = None
        
    # Average the models for a computed fair value per traded share
    valid_fvs = [fv for fv in [fv_pe, fv_pb, fv_ev_ebitda] if fv is not None and fv > 0]
    final_intrinsic_value_per_adr = sum(valid_fvs) / len(valid_fvs) if valid_fvs else 0
    
    return {
        "avg_pe": avg_pe,
        "avg_pb": avg_pb,
        "avg_ev_ebitda": avg_ev_ebitda,
        "fv_pe": fv_pe,
        "fv_pb": fv_pb,
        "fv_ev_ebitda": fv_ev_ebitda,
        "target_eps": target_eps,
        "target_bvps": target_bvps,
        "target_ebitda": target_ebitda,
        "target_debt": target_debt,
        "target_cash": target_cash,
        "shares_outstanding": shares_outstanding,
        "peers": peers,
        "computed_fair_value": final_intrinsic_value_per_adr,
        "adr_ratio": adr_ratio,
        "adr_ratio_applied": False,
        "outlier_filtering": {
            "method": "IQR fence (1.5× IQR) with 10× median fallback",
            "pe_input_count": len(valid_pe),
            "pe_filtered_count": len(filtered_pe),
            "pb_input_count": len(valid_pb),
            "pb_filtered_count": len(filtered_pb),
            "ev_ebitda_input_count": len(valid_ev_ebitda),
            "ev_ebitda_filtered_count": len(filtered_ev_ebitda),
        },
    }

def calculate_residual_income_valuation(
    bv_0: float,
    net_income: float,
    shares_outstanding: float,
    cost_of_equity: float,
    dividend_payout_ratio: float = 0.0,
    persistence_factor: float = 0.6,
    adr_ratio: float = 1.0,
) -> Dict[str, Any]:
    if shares_outstanding == 0:
        raise ValueError("Shares outstanding cannot be zero.")
        
    if bv_0 <= 0:
        raise ValueError("Starting book value must be positive.")
        
    roe = net_income / bv_0
    
    bv = bv_0
    residual_incomes = []
    
    for _ in range(5):
        # Forecast net income assuming ROE stays constant for simplicity
        # (in a real model, ROE might fade, but we'll use constant ROE for this baseline)
        forecast_ni = bv * roe
        dividends = forecast_ni * dividend_payout_ratio
        
        equity_charge = bv * cost_of_equity
        ri = forecast_ni - equity_charge
        residual_incomes.append(ri)
        
        bv = bv + forecast_ni - dividends
        
    ri_5 = residual_incomes[-1]
    terminal_value = (ri_5 * persistence_factor) / (1 + cost_of_equity - persistence_factor)
    
    pv_ri = sum([ri / ((1 + cost_of_equity) ** (t + 1)) for t, ri in enumerate(residual_incomes)])
    pv_tv = terminal_value / ((1 + cost_of_equity) ** 5)
    
    pv_future_wealth = pv_ri + pv_tv
    total_equity_value = bv_0 + pv_future_wealth
    
    raw_value_per_ordinary_share = total_equity_value / shares_outstanding
    final_intrinsic_value_per_adr = raw_value_per_ordinary_share
    book_value_per_share = bv_0 / shares_outstanding
    pv_future_wealth_per_share = pv_future_wealth / shares_outstanding
    composition_available = (
        total_equity_value > 0
        and bv_0 >= 0
        and pv_future_wealth >= 0
    )
    
    return {
        "roe": roe,
        "residual_incomes": residual_incomes,
        "terminal_value": terminal_value,
        "total_equity_value": total_equity_value,
        "bv_0": bv_0,
        "pv_future_wealth": pv_future_wealth,
        "book_value_per_share": book_value_per_share,
        "pv_future_wealth_per_share": pv_future_wealth_per_share,
        "book_value_component_percentage": (
            bv_0 / total_equity_value * 100 if composition_available else None
        ),
        "future_wealth_component_percentage": (
            pv_future_wealth / total_equity_value * 100 if composition_available else None
        ),
        "composition_available": composition_available,
        "computed_fair_value": final_intrinsic_value_per_adr,
        "adr_ratio": adr_ratio,
        "adr_ratio_applied": False,
        "share_normalization_basis": "equity_value_usd / listed_shares",
        "calculation_basis": {
            "residual_income": "forecast_net_income - opening_book_value * cost_of_equity",
            "total_equity_value": "opening_book_value + present_value_residual_income + present_value_terminal_value",
            "book_value_per_share": "opening_book_value / listed_shares",
            "pv_future_wealth_per_share": "pv_future_wealth / listed_shares",
        },
    }
