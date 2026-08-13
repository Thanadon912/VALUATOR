from app.providers.sec_capital_allocation import extract_capital_allocation


ANNUAL_ACCESSION = "0000000000-25-000010"
QUARTERLY_ACCESSION = "0000000000-26-000020"


def fact(
    value: int,
    *,
    accession: str = ANNUAL_ACCESSION,
    form: str = "10-K",
    start: str = "2024-07-01",
    end: str = "2025-06-30",
    filed: str = "2025-07-30",
    fp: str = "FY",
) -> dict:
    return {
        "val": value,
        "accn": accession,
        "form": form,
        "start": start,
        "end": end,
        "filed": filed,
        "fp": fp,
    }


def filing(form: str, accession: str, report_date: str, filing_date: str) -> dict:
    return {
        "form": form,
        "accession": accession,
        "report_date": report_date,
        "filing_date": filing_date,
        "source_url": f"https://www.sec.gov/{accession}",
    }


def concept(value: int, **kwargs) -> dict:
    return {"units": {"USD": [fact(value, **kwargs)]}}


from tests.allure_helpers import valuator_test

@valuator_test(
    epic="Financial Data Pipeline",
    feature="SEC Capital Allocation",
    story="Annual Extraction Evidence",
    priority="P1",
    severity="normal",
    layer="backend-unit",
    test_id="VAL-BE-UNIT-SEC-002"
)
def test_extracts_annual_capital_allocation_with_metric_level_evidence():
    payload = {
        "facts": {
            "us-gaap": {
                "PaymentsForRepurchaseOfCommonStock": concept(18_000_000_000),
                "PaymentsOfDividendsCommonStock": concept(9_000_000_000),
                "PaymentsToAcquireBusinessesNetOfCashAcquired": concept(
                    1_500_000_000
                ),
                "RepaymentsOfLongTermDebt": concept(4_000_000_000),
                "ProceedsFromIssuanceOfLongTermDebt": concept(0),
                "PaymentsToAcquirePropertyPlantAndEquipment": concept(
                    28_000_000_000
                ),
                "ResearchAndDevelopmentExpense": concept(32_000_000_000),
                "ShareBasedCompensation": concept(11_000_000_000),
            },
            "dei": {
                "EntityCommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {
                                "val": 7_500_000_000,
                                "accn": "0000000000-24-000009",
                                "form": "10-K",
                                "end": "2024-07-20",
                                "filed": "2024-07-30",
                            },
                            {
                                "val": 7_440_000_000,
                                "accn": ANNUAL_ACCESSION,
                                "form": "10-K",
                                "end": "2025-07-20",
                                "filed": "2025-07-30",
                            },
                        ]
                    }
                }
            },
        }
    }
    result = extract_capital_allocation(
        "MSFT",
        payload,
        [
            filing("10-K", ANNUAL_ACCESSION, "2025-06-30", "2025-07-30"),
            filing("10-Q", QUARTERLY_ACCESSION, "2025-09-30", "2025-10-29"),
        ],
        cik="0000000000",
    )

    allocation = result["capital_allocation"]
    assert result["fiscal_year"] == 2025
    assert allocation["buybacks"]["amount"] == 18_000_000_000
    assert allocation["debt_issuance"]["amount"] == 0
    assert allocation["r_and_d"]["period_type"] == "annual"
    assert allocation["equity_compensation"]["amount"] == 11_000_000_000
    assert allocation["buybacks"]["sources"][0]["source_form"] == "10-K"
    assert "PaymentsForRepurchaseOfCommonStock" in (
        allocation["buybacks"]["sources"][0]["evidence"]
    )
    assert allocation["share_dilution"]["shares_change_percent"] == -0.8
    assert len(allocation["share_dilution"]["sources"]) == 2


def test_prefers_10k_and_uses_10q_only_as_metric_fallback():
    payload = {
        "facts": {
            "us-gaap": {
                "PaymentsOfDividendsCommonStock": {
                    "units": {
                        "USD": [
                            fact(9_000_000_000),
                            fact(
                                2_500_000_000,
                                accession=QUARTERLY_ACCESSION,
                                form="10-Q",
                                start="2025-07-01",
                                end="2025-09-30",
                                filed="2025-10-29",
                                fp="Q1",
                            ),
                        ]
                    }
                },
                "ProceedsFromIssuanceOfLongTermDebt": concept(
                    750_000_000,
                    accession=QUARTERLY_ACCESSION,
                    form="10-Q",
                    start="2025-07-01",
                    end="2025-09-30",
                    filed="2025-10-29",
                    fp="Q1",
                ),
            },
            "dei": {},
        }
    }
    result = extract_capital_allocation(
        "MSFT",
        payload,
        [
            filing("10-K", ANNUAL_ACCESSION, "2025-06-30", "2025-07-30"),
            filing("10-Q", QUARTERLY_ACCESSION, "2025-09-30", "2025-10-29"),
        ],
        cik="0000000000",
    )

    allocation = result["capital_allocation"]
    assert allocation["dividends"]["amount"] == 9_000_000_000
    assert allocation["dividends"]["period_type"] == "annual"
    assert allocation["debt_issuance"]["amount"] == 750_000_000
    assert allocation["debt_issuance"]["period_type"] == "interim"


def test_missing_values_remain_null_and_are_never_substituted_with_zero():
    annual = filing(
        "10-K",
        ANNUAL_ACCESSION,
        "2025-12-31",
        "2026-02-01",
    )
    annual["html"] = """
        <h2>Liquidity and Capital Resources</h2>
        <p>Capital expenditures primarily supported new production capacity.</p>
    """
    result = extract_capital_allocation(
        "NONE",
        {"facts": {"us-gaap": {}, "dei": {}}},
        [annual],
        cik="0000000000",
    )

    allocation = result["capital_allocation"]
    assert allocation["buybacks"]["amount"] is None
    assert allocation["buybacks"]["status"] == "unavailable"
    assert allocation["buybacks"]["sources"] == []
    assert allocation["share_dilution"]["shares_change_percent"] is None
    assert allocation["capex"]["amount"] is None
    assert allocation["capex"]["filing_evidence"][0]["section"] == (
        "liquidity_and_capital_resources"
    )
