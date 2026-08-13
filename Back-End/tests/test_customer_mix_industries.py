import pytest

from app.providers.sec_customer_mix import collect_customer_mix_passages
from app.providers.sec_customer_mix_ai import GeminiCustomerMixExtractor
from tests.customer_mix_industry_cases import CUSTOMER_MIX_INDUSTRY_CASES


def filing(ticker: str, text: str) -> dict[str, str]:
    return {
        "form": "10-K",
        "accession": f"{ticker.lower()}-industry-fixture",
        "filing_date": "2026-02-01",
        "report_date": "2025-12-31",
        "source_url": f"https://www.sec.gov/example/{ticker}.htm",
        "html": f"<h2>Business</h2><p>{text}</p>",
    }


@pytest.mark.parametrize(
    "case",
    CUSTOMER_MIX_INDUSTRY_CASES,
    ids=lambda case: f"{case.sector}-{case.ticker}",
)
def test_ai_customer_mix_supports_representative_us_industries(
    case,
    monkeypatch,
):
    filings = [filing(case.ticker, case.filing_text)]
    passage = collect_customer_mix_passages(filings)[0]
    extractor = GeminiCustomerMixExtractor("key", "model", 1)
    monkeypatch.setattr(
        extractor,
        "_request",
        lambda prompt: {
            "major_customers": [],
            "customer_types": [
                {
                    "passage_id": passage["passage_id"],
                    "type": "other_explicit_type",
                    "label": label,
                }
                for label in case.customer_labels
            ],
            "channel_dependencies": [],
            "end_markets": [
                {
                    "passage_id": passage["passage_id"],
                    "market": market,
                }
                for market in case.end_markets
            ],
            "risks": [],
        },
    )

    result = extractor.extract(case.ticker, filings)
    mix = result["customer_mix"]

    assert {
        item.get("label")
        for item in mix["customer_types"]
    } >= set(case.customer_labels)
    assert {
        item["market"]
        for item in mix["end_markets"]
    } >= set(case.end_markets)
    for collection in mix.values():
        for item in collection:
            assert item["evidence"]
            assert item["source_url"].startswith("https://www.sec.gov/")
            assert item["source_accession"] == (
                f"{case.ticker.lower()}-industry-fixture"
            )


def test_industry_matrix_covers_all_gics_sectors_once_or_more():
    sectors = {case.sector for case in CUSTOMER_MIX_INDUSTRY_CASES}

    assert sectors == {
        "Communication Services",
        "Consumer Discretionary",
        "Consumer Staples",
        "Energy",
        "Financials",
        "Health Care",
        "Industrials",
        "Information Technology",
        "Materials",
        "Real Estate",
        "Utilities",
    }
