from app.providers.sec_capital_allocation import extract_capital_allocation
from app.providers.sec_debt_share_analysis import extract_debt_share_analysis
from app.providers.sec_financials import extract_financial_statements


ANNUAL_ACCESSION = "0000000000-25-000010"
PRIOR_ACCESSION = "0000000000-24-000009"


def duration_fact(
    value,
    end="2025-12-31",
    *,
    start="2025-01-01",
    accession=ANNUAL_ACCESSION,
    form="10-K",
    fp="FY",
    filed="2026-02-15",
):
    return {
        "val": value,
        "start": start,
        "end": end,
        "accn": accession,
        "form": form,
        "fp": fp,
        "filed": filed,
    }


def instant_fact(
    value,
    end="2025-12-31",
    *,
    accession=ANNUAL_ACCESSION,
    form="10-K",
    filed="2026-02-15",
):
    return {
        "val": value,
        "end": end,
        "accn": accession,
        "form": form,
        "filed": filed,
    }


def usd_concept(*facts):
    return {"units": {"USD": list(facts)}}


def share_concept(*facts):
    return {"units": {"shares": list(facts)}}


def filing(html=""):
    return {
        "form": "10-K",
        "accession": ANNUAL_ACCESSION,
        "report_date": "2025-12-31",
        "filing_date": "2026-02-15",
        "source_url": f"https://www.sec.gov/{ANNUAL_ACCESSION}",
        "html": html,
    }


def analyze(payload, html=""):
    financial_statements = extract_financial_statements(payload)
    filings = [filing(html)]
    capital_allocation = extract_capital_allocation(
        "TEST",
        payload,
        filings,
        cik="0000000000",
    )
    return extract_debt_share_analysis(
        "TEST",
        financial_statements,
        capital_allocation,
        filings,
        cik="0000000000",
        companyfacts=payload,
    )


def base_payload(
    *,
    short_debt=0,
    long_debt=0,
    cash=0,
    equity=100_000_000_000,
    assets=200_000_000_000,
    interest=1_000_000_000,
    operating_income=10_000_000_000,
    operating_cash_flow=20_000_000_000,
    basic_current=1_000_000_000,
    diluted_current=1_010_000_000,
    basic_prior=1_000_000_000,
    diluted_prior=1_010_000_000,
    buybacks=0,
    stock_comp=0,
    equity_issuance=0,
):
    return {
        "entityName": "Test Corp",
        "facts": {
            "us-gaap": {
                "ShortTermBorrowings": usd_concept(instant_fact(short_debt)),
                "LongTermDebtNoncurrent": usd_concept(instant_fact(long_debt)),
                "CashAndCashEquivalentsAtCarryingValue": usd_concept(
                    instant_fact(cash)
                ),
                "StockholdersEquity": usd_concept(instant_fact(equity)),
                "Assets": usd_concept(instant_fact(assets)),
                "InterestExpenseNonOperating": usd_concept(
                    duration_fact(interest)
                ),
                "OperatingIncomeLoss": usd_concept(duration_fact(operating_income)),
                "NetCashProvidedByUsedInOperatingActivities": usd_concept(
                    duration_fact(operating_cash_flow)
                ),
                "RevenueFromContractWithCustomerExcludingAssessedTax": usd_concept(
                    duration_fact(100_000_000, "2024-12-31", start="2024-01-01", accession=PRIOR_ACCESSION, filed="2025-02-15")
                ),
                "Revenues": usd_concept(duration_fact(100_000_000)),
                "CostOfGoodsAndServicesSold": {
                    "units": {
                        "USD": [
                            duration_fact(50_000_000, "2024-12-31", start="2024-01-01", accession=PRIOR_ACCESSION, filed="2025-02-15"),
                            duration_fact(50_000_000)
                        ]
                    }
                },
                "OperatingExpenses": {
                    "units": {
                        "USD": [
                            duration_fact(20_000_000, "2024-12-31", start="2024-01-01", accession=PRIOR_ACCESSION, filed="2025-02-15"),
                            duration_fact(20_000_000)
                        ]
                    }
                },
                "WeightedAverageNumberOfSharesOutstandingBasic": {
                    "units": {
                        "shares": [
                            duration_fact(
                                basic_prior,
                                "2024-12-31",
                                start="2024-01-01",
                                accession=PRIOR_ACCESSION,
                                filed="2025-02-15",
                            ),
                            duration_fact(basic_current),
                        ]
                    }
                },
                "WeightedAverageNumberOfDilutedSharesOutstanding": {
                    "units": {
                        "shares": [
                            duration_fact(
                                diluted_prior,
                                "2024-12-31",
                                start="2024-01-01",
                                accession=PRIOR_ACCESSION,
                                filed="2025-02-15",
                            ),
                            duration_fact(diluted_current),
                        ]
                    }
                },
                "PaymentsForRepurchaseOfCommonStock": usd_concept(
                    duration_fact(buybacks)
                ),
                "ShareBasedCompensation": usd_concept(duration_fact(stock_comp)),
                "ProceedsFromIssuanceOfCommonStock": usd_concept(
                    duration_fact(equity_issuance)
                ),
                "ProceedsFromIssuanceOfLongTermDebt": usd_concept(
                    duration_fact(2_000_000_000)
                ),
                "RepaymentsOfLongTermDebt": usd_concept(
                    duration_fact(1_500_000_000)
                ),
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": share_concept(
                    instant_fact(
                        basic_prior,
                        "2024-12-31",
                        accession=PRIOR_ACCESSION,
                        filed="2025-02-15",
                    ),
                    instant_fact(basic_current),
                )
            },
        },
    }


def test_debt_profile_company_with_large_debt_and_maturity_evidence():
    result = analyze(
        base_payload(
            short_debt=20_000_000_000,
            long_debt=80_000_000_000,
            cash=10_000_000_000,
            equity=100_000_000_000,
            assets=250_000_000_000,
            interest=4_000_000_000,
            operating_income=20_000_000_000,
            operating_cash_flow=30_000_000_000,
        ),
        """
        <h2>Debt</h2>
        <p>The Company has $5.0 billion of senior notes maturing in 2027.</p>
        """,
    )

    debt = result["debt_profile"]
    assert result["fiscal_year"] == 2025
    assert debt["short_term_debt"] == 20_000_000_000
    assert debt["long_term_debt"] == 80_000_000_000
    assert debt["total_debt"] == 100_000_000_000
    assert debt["net_debt"] == 90_000_000_000
    assert debt["debt_to_equity"] == 1
    assert debt["debt_to_assets"] == 0.4
    assert debt["interest_coverage"] == 5
    assert debt["net_debt_to_operating_cash_flow"] == 3
    assert debt["debt_maturities"][0]["year"] == 2027
    assert debt["debt_maturities"][0]["amount"] == 5_000_000_000
    assert debt["sources"]["total_debt"][0]["source_url"]


def test_debt_profile_company_with_net_cash():
    result = analyze(
        base_payload(
            short_debt=1_000_000_000,
            long_debt=2_000_000_000,
            cash=10_000_000_000,
        )
    )

    debt = result["debt_profile"]
    assert debt["total_debt"] == 3_000_000_000
    assert debt["net_debt"] == -7_000_000_000
    assert debt["debt_issuance"] == 2_000_000_000
    assert debt["debt_repayment"] == 1_500_000_000


def test_share_dilution_declining_share_count_due_to_buybacks_is_low_risk():
    result = analyze(
        base_payload(
            basic_prior=1_000_000_000,
            diluted_prior=1_020_000_000,
            basic_current=950_000_000,
            diluted_current=970_000_000,
            buybacks=12_000_000_000,
            stock_comp=2_000_000_000,
        ),
        """
        <h2>Share Repurchase Programs</h2>
        <p>Share repurchases reduced common shares outstanding during the year.</p>
        """,
    )

    share = result["share_dilution"]
    assert share["weighted_average_shares"] == 970_000_000
    assert share["year_over_year_diluted_share_change_percent"] == -4.902
    assert share["net_share_change_percent"] == -4.902
    assert share["dilution_risk"] == "low"
    assert share["buyback_offset"]["offset_amount"] == 10_000_000_000
    assert share["share_repurchases"] == 12_000_000_000


def test_share_dilution_increasing_share_count_due_to_dilution_is_high_risk():
    result = analyze(
        base_payload(
            basic_prior=1_000_000_000,
            diluted_prior=1_010_000_000,
            basic_current=1_080_000_000,
            diluted_current=1_100_000_000,
            buybacks=0,
            stock_comp=3_000_000_000,
            equity_issuance=5_000_000_000,
        ),
        """
        <h2>Stock-Based Compensation</h2>
        <p>Diluted shares increased as equity awards vested during the year.</p>
        """,
    )

    share = result["share_dilution"]
    assert share["diluted_vs_basic_spread_percent"] == 1.8519
    assert share["year_over_year_diluted_share_change_percent"] == 8.9109
    assert share["net_share_change_percent"] == 8.9109
    assert share["dilution_risk"] == "high"
    assert share["equity_issuance"] == 5_000_000_000
    assert share["sources"]["equity_issuance"][0]["filing_date"] == "2026-02-15"
