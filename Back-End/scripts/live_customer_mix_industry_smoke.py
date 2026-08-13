from __future__ import annotations

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any

import httpx


INDUSTRY_STOCKS = (
    ("Information Technology", "Semiconductors", "TSM"),
    ("Financials", "Diversified Banks", "JPM"),
    ("Health Care", "Managed Health Care", "UNH"),
    ("Industrials", "Construction Machinery", "CAT"),
    ("Consumer Discretionary", "Broadline Retail", "AMZN"),
    ("Consumer Staples", "Household Products", "PG"),
    ("Energy", "Integrated Oil and Gas", "XOM"),
    ("Utilities", "Electric Utilities", "NEE"),
    ("Real Estate", "Industrial REITs", "PLD"),
    (
        "Communication Services",
        "Integrated Telecommunication Services",
        "VZ",
    ),
    ("Materials", "Industrial Gases", "LIN"),
)

FORBIDDEN_RISK_EVIDENCE = re.compile(
    r"\b(financing receivables?|customer financing|loan losses?|"
    r"allowance for credit losses?|past due|billing milestones)\b",
    re.I,
)


@dataclass
class LiveResult:
    sector: str
    industry: str
    ticker: str
    ok: bool
    module_status: str | None = None
    extraction_method: str | None = None
    model: str | None = None
    cache_source: str | None = None
    analyzed_forms: tuple[str, ...] = ()
    major_customers: int = 0
    customer_types: int = 0
    channel_dependencies: int = 0
    end_markets: int = 0
    risks: int = 0
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


def _validate_items(
    mix: dict[str, Any],
    errors: list[str],
) -> None:
    for collection_name, items in mix.items():
        if not isinstance(items, list):
            errors.append(f"{collection_name} is not an array")
            continue
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                errors.append(f"{collection_name}[{index}] is not an object")
                continue
            if not item.get("evidence"):
                errors.append(f"{collection_name}[{index}] missing evidence")
            source_url = item.get("source_url")
            if not (
                isinstance(source_url, str)
                and source_url.startswith("https://www.sec.gov/")
            ):
                errors.append(
                    f"{collection_name}[{index}] missing SEC source URL"
                )
            if not item.get("filing_date"):
                errors.append(
                    f"{collection_name}[{index}] missing filing date"
                )

    for index, risk in enumerate(mix.get("risks") or []):
        evidence = str(risk.get("evidence") or "")
        if FORBIDDEN_RISK_EVIDENCE.search(evidence):
            errors.append(
                f"risks[{index}] contains financing/credit false positive"
            )


def check_stock(
    base_url: str,
    sector: str,
    industry: str,
    ticker: str,
    timeout_seconds: float,
) -> LiveResult:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        response = httpx.get(
            f"{base_url.rstrip('/')}/api/stocks/{ticker}/summary",
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return LiveResult(
            sector=sector,
            industry=industry,
            ticker=ticker,
            ok=False,
            errors=(f"request failed: {exc.__class__.__name__}",),
        )

    module = payload.get("data", {}).get("customer_mix")
    if not isinstance(module, dict):
        errors.append("customer_mix module missing")
        module = {}
    module_status = module.get("status")
    if module_status not in {"success", "partial"}:
        errors.append(f"unexpected module status: {module_status}")
    data = module.get("data")
    if not isinstance(data, dict):
        errors.append("customer_mix data missing")
        data = {}
    filings = data.get("analyzed_filings")
    if not isinstance(filings, list) or not filings:
        errors.append("no annual/quarterly filing analyzed")
        filings = []
    for index, filing in enumerate(filings):
        if not filing.get("accession"):
            errors.append(f"analyzed_filings[{index}] missing accession")
        if not filing.get("source_url"):
            errors.append(f"analyzed_filings[{index}] missing source URL")

    extraction = data.get("extraction")
    if not isinstance(extraction, dict):
        errors.append("extraction provenance missing")
        extraction = {}
    elif extraction.get("method") not in {"ai", "deterministic"}:
        errors.append("invalid extraction method")

    mix = data.get("customer_mix")
    if not isinstance(mix, dict):
        errors.append("normalized customer_mix missing")
        mix = {}
    _validate_items(mix, errors)
    if not (mix.get("customer_types") or []):
        errors.append(
            "representative stock has no extracted customer type"
        )
    if not any(mix.get(name) for name in (
        "major_customers",
        "customer_types",
        "channel_dependencies",
        "end_markets",
        "risks",
    )):
        errors.append("representative stock has no customer-mix coverage")
    warnings.extend(payload.get("warnings") or [])

    return LiveResult(
        sector=sector,
        industry=industry,
        ticker=ticker,
        ok=not errors,
        module_status=module_status,
        extraction_method=extraction.get("method"),
        model=extraction.get("model"),
        cache_source=extraction.get("cache_source"),
        analyzed_forms=tuple(
            str(filing.get("form"))
            for filing in filings
            if filing.get("form")
        ),
        major_customers=len(mix.get("major_customers") or []),
        customer_types=len(mix.get("customer_types") or []),
        channel_dependencies=len(mix.get("channel_dependencies") or []),
        end_markets=len(mix.get("end_markets") or []),
        risks=len(mix.get("risks") or []),
        warnings=tuple(warnings),
        errors=tuple(errors),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8200",
    )
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=150)
    parser.add_argument("--output")
    args = parser.parse_args()

    results: list[LiveResult] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        futures = {
            executor.submit(
                check_stock,
                args.base_url,
                sector,
                industry,
                ticker,
                args.timeout,
            ): ticker
            for sector, industry, ticker in INDUSTRY_STOCKS
        }
        for future in as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda item: item.sector)
    output = {
        "summary": {
            "stocks": len(results),
            "passed": sum(item.ok for item in results),
            "failed": sum(not item.ok for item in results),
            "with_customer_types": sum(
                item.customer_types > 0 for item in results
            ),
            "with_any_customer_mix": sum(
                (
                    item.major_customers
                    + item.customer_types
                    + item.channel_dependencies
                    + item.end_markets
                    + item.risks
                )
                > 0
                for item in results
            ),
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
