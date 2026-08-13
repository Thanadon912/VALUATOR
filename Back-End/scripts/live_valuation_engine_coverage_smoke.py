"""Live check that every valuation category is computed as that category should be.

Complements tests/test_valuation_engine_coverage.py: the pytest suite pins the
contracts against fixtures, this one runs the same expectations against real
provider data through the running API.

Usage:
    .venv/bin/python scripts/live_valuation_engine_coverage_smoke.py \
        --base-url http://127.0.0.1:8001
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx


# (engine expected, ticker) — one representative per reachable engine.
ENGINE_STOCKS = (
    ("Capitalized R&D DCF", "NVDA"),
    ("Regulatory FCFE", "JPM"),
    ("Normalized Median DCF", "XOM"),
    ("Standard Driver-Based DCF", "KO"),
)

# Cross-cutting data shapes checked separately from engine selection.
ADR_TICKER = "TSM"
IFRS_PEER_TICKER = "ASML"
DIVIDEND_TICKER = "KO"
NON_DIVIDEND_TICKER = "NVDA"
MARGIN_REJECTION_TICKERS = ("AMZN", "TSLA")

# Multiples beyond these are provider unit/basis errors, not real comparables.
PLAUSIBLE_PB_MAX = 100.0
PLAUSIBLE_EV_EBITDA_MAX = 150.0


@dataclass
class CheckResult:
    category: str
    ticker: str
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = ()


def _get(base_url: str, path: str, timeout: float) -> dict[str, Any]:
    response = httpx.get(f"{base_url.rstrip('/')}{path}", timeout=timeout)
    response.raise_for_status()
    return response.json()


def check_engine(base_url: str, engine: str, ticker: str, timeout: float) -> CheckResult:
    errors: list[str] = []
    try:
        payload = _get(base_url, f"/api/v1/valuation/dcf?ticker={ticker}", timeout)
    except (httpx.HTTPError, ValueError) as exc:
        return CheckResult(engine, ticker, False, errors=(f"request failed: {exc.__class__.__name__}",))

    status = payload.get("valuation_status")
    methodology = payload.get("valuation_methodology")
    ua = payload.get("underlying_assumptions") or {}
    fair_value = payload.get("computed_fair_value")

    if status not in {"CALCULATED", "UNAVAILABLE"}:
        errors.append(f"unexpected status {status}")
    ran_growth_model = ua.get("model_version") == "growth_multistage_fcff_v3"
    if status == "CALCULATED":
        if fair_value is None or fair_value <= 0:
            errors.append(f"published a non-positive fair value: {fair_value}")
        if methodology != engine:
            # The growth engine relabels itself "Standard Driver-Based DCF"
            # when the R&D history is unusable. That is a legitimate downgrade
            # of the label, not a routing error, as long as the growth model
            # is the one that actually ran.
            downgraded_label = engine == "Capitalized R&D DCF" and ran_growth_model
            if not downgraded_label:
                errors.append(f"expected engine {engine}, got {methodology}")

    if engine == "Regulatory FCFE":
        if ua.get("enterprise_value") is not None:
            errors.append("bank model must not produce an enterprise value")
        for key in ("present_value_fcfe", "present_value_terminal_value", "tier1_capital_ratio"):
            if ua.get(key) is None:
                errors.append(f"missing {key}")
        if ua.get("discount_rate_basis") != "cost_of_equity_only":
            errors.append(f"discount basis is {ua.get('discount_rate_basis')}, expected cost of equity")
        if ua.get("wacc_used") is not False:
            errors.append("bank model must not discount at WACC")

    elif engine == "Normalized Median DCF":
        if ua.get("normalized_margin") is None:
            errors.append("cyclical model must expose normalized_margin")
        if ua.get("consensus_coverage") is not None:
            errors.append("consensus anchoring belongs to the growth engine only")

    elif engine == "Standard Driver-Based DCF":
        ratio = ua.get("sales_to_capital_ratio")
        if ratio is None or not (1.0 <= ratio <= 4.0):
            errors.append(f"sales_to_capital_ratio {ratio} outside clamp [1.0, 4.0]")
        for row in ua.get("revenue_projections") or []:
            nopat, reinvest = row.get("nopat"), row.get("reinvestment")
            if nopat and reinvest is not None and reinvest > nopat * 0.8 + 1e-6:
                errors.append(f"year {row.get('year')} reinvestment exceeds the 80% NOPAT cap")
                break

    elif engine == "Capitalized R&D DCF":
        if not ran_growth_model:
            errors.append("expected the growth multi-stage model")
        if not ua.get("terminal_margin_basis"):
            errors.append("terminal_margin_basis must always be disclosed")
        if ua.get("projection_years") != 15:
            errors.append(f"expected a 15-year horizon, got {ua.get('projection_years')}")

    return CheckResult(
        category=engine,
        ticker=ticker,
        ok=not errors,
        detail={
            "status": status,
            "methodology": methodology,
            "fair_value": fair_value,
            "current_price": payload.get("current_price"),
            "terminal_margin_basis": ua.get("terminal_margin_basis"),
            "sales_to_capital_basis": ua.get("sales_to_capital_basis"),
        },
        errors=tuple(errors),
    )


def check_adr(base_url: str, timeout: float) -> CheckResult:
    errors: list[str] = []
    try:
        payload = _get(base_url, f"/api/v1/valuation/dcf?ticker={ADR_TICKER}", timeout)
    except (httpx.HTTPError, ValueError) as exc:
        return CheckResult("adr_non_usd_reporting", ADR_TICKER, False,
                           errors=(f"request failed: {exc.__class__.__name__}",))
    ua = payload.get("underlying_assumptions") or {}
    telemetry = ua.get("telemetry") or {}
    fx = ua.get("fx_translation") or {}
    reported_currency = ua.get("reported_currency")
    normalization = ua.get("analyst_estimates_normalization") or {}

    # TSM's SEC-filed financial statements are already reported in USD (that
    # is genuinely its reported_currency/fx_translation, correctly identity
    # here) — only its separate FMP analyst-estimates consensus feed is
    # TWD-denominated. That mismatch was the original defect, so assert on
    # the estimate-level normalization rather than the overall statement
    # currency.
    if reported_currency is None:
        errors.append("reported_currency is missing from the response; cannot audit the FX basis")
    if fx.get("rate") is None:
        errors.append("fx_translation.rate is missing from the response")
    if normalization.get("status") != "normalized":
        errors.append(f"analyst estimate normalization status is {normalization.get('status')!r}, expected 'normalized'")
    if normalization.get("source_units") != ["TWD"]:
        errors.append(
            f"expected analyst estimates sourced in TWD, got {normalization.get('source_units')}"
        )
    adr_ratio = ua.get("adr_ratio")
    if adr_ratio is not None and adr_ratio <= 1.0:
        errors.append(f"expected an ADR ratio above 1, got {adr_ratio}")

    return CheckResult(
        "adr_non_usd_reporting", ADR_TICKER, not errors,
        detail={
            "reported_currency": reported_currency,
            "fx_rate": fx.get("rate"),
            "adr_ratio": adr_ratio,
            "estimate_normalization": normalization.get("status"),
            "estimate_source_units": normalization.get("source_units"),
            "fair_value": payload.get("computed_fair_value"),
            "current_price": payload.get("current_price") or telemetry.get("current_price"),
        },
        errors=tuple(errors),
    )


def check_ifrs_peer(base_url: str, timeout: float) -> CheckResult:
    errors: list[str] = []
    try:
        payload = _get(base_url, f"/api/v1/valuation/relative?ticker={ADR_TICKER}", timeout)
    except (httpx.HTTPError, ValueError) as exc:
        return CheckResult("ifrs_filer_with_provider_gaps", IFRS_PEER_TICKER, False,
                           errors=(f"request failed: {exc.__class__.__name__}",))
    peers = (payload.get("underlying_assumptions") or {}).get("available_peers") or []
    peer = next((p for p in peers if str(p.get("symbol", "")).upper() == IFRS_PEER_TICKER), None)
    if peer is None:
        return CheckResult("ifrs_filer_with_provider_gaps", IFRS_PEER_TICKER, False,
                           errors=(f"{IFRS_PEER_TICKER} not present in peer set",))

    pb, ev_ebitda = peer.get("pb"), peer.get("ev_ebitda")
    if pb is not None and pb > PLAUSIBLE_PB_MAX:
        errors.append(f"implausible P/B published: {pb}")
    if ev_ebitda is not None and ev_ebitda > PLAUSIBLE_EV_EBITDA_MAX:
        errors.append(f"implausible EV/EBITDA published: {ev_ebitda}")

    return CheckResult(
        "ifrs_filer_with_provider_gaps", IFRS_PEER_TICKER, not errors,
        detail={
            "pe": peer.get("pe"), "pb": pb, "ev_ebitda": ev_ebitda,
            "metric_sources": peer.get("metric_sources"),
            "rejected_provider_values": peer.get("rejected_provider_values"),
        },
        errors=tuple(errors),
    )


def check_dividend(base_url: str, ticker: str, expect_applicable: bool, timeout: float) -> CheckResult:
    category = "dividend_payer_ddm_applicable" if expect_applicable else "non_dividend_payer_ddm_inapplicable"
    errors: list[str] = []
    try:
        payload = _get(base_url, f"/api/v1/valuation/ddm?ticker={ticker}", timeout)
    except (httpx.HTTPError, ValueError) as exc:
        return CheckResult(category, ticker, False, errors=(f"request failed: {exc.__class__.__name__}",))

    status = payload.get("valuation_status")
    ua = payload.get("underlying_assumptions") or {}
    applicable = ua.get("is_ddm_applicable")
    # DDM's own status vocabulary (APPLICABLE/INAPPLICABLE) differs from the
    # DCF endpoint's (CALCULATED/UNAVAILABLE), so check applicability and the
    # fair value directly rather than assuming a specific status string.
    if expect_applicable:
        if applicable is not True or not payload.get("computed_fair_value"):
            errors.append(f"dividend payer should produce a DDM value; status={status}, applicable={applicable}")
    else:
        # The engine still computes the raw Gordon Growth number even when
        # inapplicable, so a consumer can see "what DDM would say" — the
        # frontend keys off is_ddm_applicable/applicability_reasons to hide
        # or relabel it, not off the fair value being absent. Check the flag
        # and its reasons, not whether a number was computed.
        if applicable is not False:
            errors.append(f"expected is_ddm_applicable is False, got {applicable}")
        if not ua.get("applicability_reasons"):
            errors.append("inapplicable DDM must state why")

    return CheckResult(
        category, ticker, not errors,
        detail={
            "status": status,
            "is_ddm_applicable": applicable,
            "fair_value": payload.get("computed_fair_value"),
            "reasons": ua.get("applicability_reasons"),
        },
        errors=tuple(errors),
    )


def check_margin_rejection(base_url: str, ticker: str, timeout: float) -> CheckResult:
    errors: list[str] = []
    try:
        payload = _get(base_url, f"/api/v1/valuation/dcf?ticker={ticker}", timeout)
    except (httpx.HTTPError, ValueError) as exc:
        return CheckResult("implausible_flat_consensus_margin", ticker, False,
                           errors=(f"request failed: {exc.__class__.__name__}",))
    ua = payload.get("underlying_assumptions") or {}
    rejected = ua.get("margin_consensus_rejected")
    reason = ua.get("margin_consensus_rejection_reason")
    if rejected and not reason:
        errors.append("rejection must be disclosed with a reason")
    fair_value = payload.get("computed_fair_value")
    if payload.get("valuation_status") == "CALCULATED" and (fair_value is None or fair_value <= 0):
        errors.append(f"published a non-positive fair value: {fair_value}")

    return CheckResult(
        "implausible_flat_consensus_margin", ticker, not errors,
        detail={
            "margin_consensus_rejected": rejected,
            "terminal_margin": ua.get("terminal_margin"),
            "terminal_margin_basis": ua.get("terminal_margin_basis"),
            "fair_value": fair_value,
            "current_price": payload.get("current_price"),
        },
        errors=tuple(errors),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output")
    args = parser.parse_args()

    jobs = [
        *((check_engine, (args.base_url, engine, ticker, args.timeout)) for engine, ticker in ENGINE_STOCKS),
        (check_adr, (args.base_url, args.timeout)),
        (check_ifrs_peer, (args.base_url, args.timeout)),
        (check_dividend, (args.base_url, DIVIDEND_TICKER, True, args.timeout)),
        (check_dividend, (args.base_url, NON_DIVIDEND_TICKER, False, args.timeout)),
        *((check_margin_rejection, (args.base_url, ticker, args.timeout)) for ticker in MARGIN_REJECTION_TICKERS),
    ]

    results: list[CheckResult] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = [executor.submit(fn, *fn_args) for fn, fn_args in jobs]
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: (item.category, item.ticker))
    output = {
        "summary": {
            "checks": len(results),
            "passed": sum(item.ok for item in results),
            "failed": sum(not item.ok for item in results),
        },
        "results": [asdict(item) for item in results],
    }
    rendered = json.dumps(output, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as file:
            file.write(rendered)
            file.write("\n")
    return 1 if any(not item.ok for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
