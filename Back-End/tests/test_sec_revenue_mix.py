from app.providers.sec_revenue_mix import (
    extract_revenue_mix_from_companyfacts,
    extract_revenue_mix_from_inline_xbrl,
)


def inline_filing(
    period_start: str,
    period_end: str,
    axis: str,
    members: list[tuple[str, int]],
    *,
    concept: str = (
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    ),
    unit: str = "usd",
) -> str:
    contexts = []
    facts = []
    for index, (member, value) in enumerate(members):
        context_id = f"segment-{index}"
        contexts.append(
            f"""
            <xbrli:context id="{context_id}">
              <xbrli:entity><xbrli:identifier>entity</xbrli:identifier></xbrli:entity>
              <xbrli:period>
                <xbrli:startDate>{period_start}</xbrli:startDate>
                <xbrli:endDate>{period_end}</xbrli:endDate>
              </xbrli:period>
              <xbrli:scenario>
                <xbrldi:explicitMember dimension="{axis}">
                  {member}
                </xbrldi:explicitMember>
              </xbrli:scenario>
            </xbrli:context>
            """
        )
        facts.append(
            f"""
            <ix:nonFraction
              name="{concept}"
              contextRef="{context_id}"
              unitRef="{unit}"
              scale="6"
            >{value:,}</ix:nonFraction>
            """
        )
    return f"<html><body>{''.join(contexts)}{''.join(facts)}</body></html>"


def test_microsoft_revenue_mix_uses_reported_business_segments():
    html = inline_filing(
        "2024-07-01",
        "2025-06-30",
        "us-gaap:StatementBusinessSegmentsAxis",
        [
            ("msft:ProductivityAndBusinessProcessesMember", 120_810),
            ("msft:IntelligentCloudMember", 106_265),
            ("msft:MorePersonalComputingMember", 54_649),
        ],
    )

    result = extract_revenue_mix_from_inline_xbrl(
        "MSFT",
        html,
        [{"end": "2025-06-30", "value": 281_724_000_000, "unit": "USD"}],
    )

    assert result["ticker"] == "MSFT"
    assert result["fiscal_year"] == 2025
    segments = result["revenue_mix"]["business_segments"]
    assert result["dimension_metadata"]["business_segments"]["total_revenue"] == (
        281_724_000_000
    )
    assert [row["segment"] for row in segments] == [
        "Productivity & Business Processes",
        "Intelligent Cloud",
        "More Personal Computing",
    ]
    assert sum(row["revenue"] for row in segments) == 281_724_000_000
    assert all(row["confidence"] == 0.95 for row in segments)
    assert result["revenue_mix"]["geography"] == []


def test_amazon_revenue_mix_avoids_double_counting_combined_segment():
    html = inline_filing(
        "2025-01-01",
        "2025-12-31",
        "us-gaap:StatementBusinessSegmentsAxis",
        [
            ("amzn:NorthAmericaSegmentMember", 426_305),
            ("amzn:InternationalSegmentMember", 161_894),
            ("amzn:AmazonWebServicesSegmentMember", 128_725),
            (
                "amzn:NorthAmericaAndInternationalSegmentMember",
                588_199,
            ),
        ],
    )

    result = extract_revenue_mix_from_inline_xbrl(
        "AMZN",
        html,
        [{"end": "2025-12-31", "value": 716_924_000_000, "unit": "USD"}],
    )

    segments = result["revenue_mix"]["business_segments"]
    assert [row["segment"] for row in segments] == [
        "North America",
        "International",
        "Amazon Web Services",
    ]
    assert all(
        "North America & International" != row["segment"]
        for row in segments
    )
    assert round(sum(row["percentage"] for row in segments), 1) == 100.1


def test_apple_revenue_mix_preserves_products_and_geographic_segments():
    geographic_html = inline_filing(
        "2024-09-29",
        "2025-09-27",
        "us-gaap:StatementBusinessSegmentsAxis",
        [
            ("aapl:AmericasSegmentMember", 178_353),
            ("aapl:EuropeSegmentMember", 111_032),
            ("aapl:GreaterChinaSegmentMember", 64_377),
            ("aapl:JapanSegmentMember", 28_703),
            ("aapl:RestOfAsiaPacificSegmentMember", 33_696),
        ],
    )
    product_html = inline_filing(
        "2024-09-29",
        "2025-09-27",
        "srt:ProductOrServiceAxis",
        [
            ("aapl:IPhoneMember", 209_586),
            ("aapl:MacMember", 33_708),
            ("aapl:IPadMember", 28_023),
            ("aapl:WearablesHomeandAccessoriesMember", 35_686),
            ("us-gaap:ServiceMember", 109_158),
            ("us-gaap:ProductMember", 307_003),
        ],
    ).replace("segment-", "product-")
    html = geographic_html.replace(
        "</body></html>",
        product_html.replace("<html><body>", ""),
    )

    result = extract_revenue_mix_from_inline_xbrl(
        "AAPL",
        html,
        [{"end": "2025-09-27", "value": 416_161_000_000, "unit": "USD"}],
    )

    products = result["revenue_mix"]["products"]
    geography = result["revenue_mix"]["geography"]
    assert len(products) == 5
    assert products[0]["product"] == "iPhone"
    assert products[0]["percentage"] == 50.4
    assert geography[0]["region"] == "Americas"
    assert geography[0]["revenue"] == 178_353_000_000
    assert geography[0]["confidence"] == 0.95
    assert geography[0]["evidence"]
    assert set(result["revenue_mix"]) == {
        "business_segments",
        "products",
        "geography",
        "end_markets",
    }


def test_companyfacts_is_attempted_before_filing_when_dimensions_are_available():
    payload = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "start": "2024-07-01",
                                "end": "2025-06-30",
                                "val": 60,
                                "dimensions": {
                                    "us-gaap:StatementBusinessSegmentsAxis": (
                                        "example:CloudMember"
                                    )
                                },
                            },
                            {
                                "start": "2024-07-01",
                                "end": "2025-06-30",
                                "val": 40,
                                "dimensions": {
                                    "us-gaap:StatementBusinessSegmentsAxis": (
                                        "example:DevicesMember"
                                    )
                                },
                            },
                        ]
                    },
                }
            }
        }
    }

    result = extract_revenue_mix_from_companyfacts(
        "EXMPL",
        payload,
        [{"end": "2025-06-30", "value": 100, "unit": "USD"}],
    )

    segments = result["revenue_mix"]["business_segments"]
    assert segments[0]["source"] == "sec_companyfacts"
    assert [row["percentage"] for row in segments] == [60.0, 40.0]


def test_revenue_mix_fails_closed_when_segments_do_not_reconcile():
    html = inline_filing(
        "2025-01-01",
        "2025-12-31",
        "us-gaap:StatementBusinessSegmentsAxis",
        [
            ("example:SegmentOneMember", 30),
            ("example:SegmentTwoMember", 20),
        ],
    )

    result = extract_revenue_mix_from_inline_xbrl(
        "EXMPL",
        html,
        [{"end": "2025-12-31", "value": 100_000_000, "unit": "USD"}],
    )

    assert result == {}


def test_tsm_revenue_mix_supports_ifrs_end_markets_and_twd():
    html = inline_filing(
        "2025-01-01",
        "2025-12-31",
        "ifrs-full:MarketsOfCustomersAxis",
        [
            ("tsm:HighPerformanceComputingMember", 2_192_931),
            ("tsm:SmartphoneMember", 1_110_816),
            ("tsm:InternetOfThingsMember", 191_047),
            ("tsm:AutomotiveMember", 186_667),
            ("tsm:OtherMember", 79_597),
            ("tsm:DigitalConsumerElectronicsMember", 47_996),
        ],
        concept="ifrs-full:RevenueFromContractsWithCustomers",
        unit="twd",
    )

    result = extract_revenue_mix_from_inline_xbrl(
        "TSM",
        html,
        [
            {
                "end": "2025-12-31",
                "value": 3_809_054_000_000,
                "unit": "TWD",
            }
        ],
    )

    assert result["ticker"] == "TSM"
    end_markets = result["revenue_mix"]["end_markets"]
    assert end_markets[0]["currency"] == "TWD"
    assert end_markets[0]["end_market"] == "High Performance Computing"
    assert end_markets[0]["percentage"] == 57.6


def test_geography_includes_filing_provenance_and_no_inferred_values():
    html = inline_filing(
        "2024-01-01",
        "2024-12-31",
        "us-gaap:StatementGeographicalAxis",
        [
            ("example:UnitedStatesMember", 48_200),
            ("example:InternationalMember", 51_800),
        ],
    )

    result = extract_revenue_mix_from_inline_xbrl(
        "EXMPL",
        html,
        [{"end": "2024-12-31", "value": 100_000_000_000, "unit": "USD"}],
        filing_url="https://www.sec.gov/example-10k.htm",
        filing_date="2025-02-15",
    )

    geography = result["revenue_mix"]["geography"]
    assert geography[0] == {
        "name": "International",
        "region": "International",
        "member": "example:InternationalMember",
        "revenue": 51_800_000_000,
        "percentage": 51.8,
        "currency": "USD",
        "period_end": "2024-12-31",
        "confidence": 0.95,
        "evidence": (
            "SEC XBRL fact "
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax "
            "reports International revenue of 51800000000 USD for the fiscal "
            "period ending 2024-12-31; the selected dimension reconciles to "
            "reported total revenue."
        ),
        "filing_url": "https://www.sec.gov/example-10k.htm",
        "filing_date": "2025-02-15",
        "source": "sec_filing_inline_xbrl",
        "axis": "us-gaap:StatementGeographicalAxis",
        "concept": (
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
        ),
        "coverage": "complete",
    }


def test_geographic_concentration_can_be_partial_when_explicitly_reported():
    html = inline_filing(
        "2024-01-01",
        "2024-12-31",
        "us-gaap:StatementGeographicalAxis",
        [("example:UnitedStatesMember", 48_200)],
    )

    result = extract_revenue_mix_from_inline_xbrl(
        "EXMPL",
        html,
        [{"end": "2024-12-31", "value": 100_000_000_000, "unit": "USD"}],
    )

    geography = result["revenue_mix"]["geography"]
    assert geography[0]["region"] == "United States"
    assert geography[0]["revenue"] == 48_200_000_000
    assert geography[0]["percentage"] == 48.2
    assert geography[0]["confidence"] == 0.75
    assert geography[0]["coverage"] == "partial"
    assert result["dimension_metadata"]["geography"]["coverage"] == "partial"


def test_revenue_mix_does_not_reconcile_across_currencies():
    html = inline_filing(
        "2025-01-01",
        "2025-12-31",
        "ifrs-full:MarketsOfCustomersAxis",
        [
            ("example:CloudMember", 60),
            ("example:DevicesMember", 40),
        ],
        concept="ifrs-full:RevenueFromContractsWithCustomers",
        unit="twd",
    )

    result = extract_revenue_mix_from_inline_xbrl(
        "EXMPL",
        html,
        [{"end": "2025-12-31", "value": 100_000_000, "unit": "USD"}],
    )

    assert result == {}
