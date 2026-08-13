from app.providers.sec_customer_mix import extract_customer_mix


def filing(
    html: str,
    *,
    form: str = "10-K",
    accession: str = "0000000000-26-000001",
    filing_date: str = "2026-02-01",
    report_date: str = "2025-12-31",
) -> dict[str, str]:
    return {
        "form": form,
        "accession": accession,
        "filing_date": filing_date,
        "report_date": report_date,
        "source_url": f"https://www.sec.gov/Archives/{accession}.htm",
        "html": html,
    }


from tests.allure_helpers import valuator_test

@valuator_test(
    epic="Financial Data Pipeline",
    feature="SEC Customer Mix",
    story="Anonymized Customer Extraction",
    priority="P2",
    severity="minor",
    layer="backend-unit",
    test_id="VAL-BE-UNIT-SEC-003"
)
def test_extracts_anonymized_and_unnamed_major_customers_with_provenance():
    result = extract_customer_mix(
        "EXM",
        [
            filing(
                """
                <h2>Major Customers</h2>
                <p>Customer A accounted for 13% of our revenue during fiscal
                2025.</p>
                <p>One customer accounted for 11% of our net sales during
                fiscal 2025.</p>
                <h2>Concentration of Credit Risk</h2>
                <p>Customer B represented 18% of accounts receivable at year
                end.</p>
                <p>Acme Corporation remains one of our major customers, and
                the loss of this customer could adversely affect revenue.</p>
                """
            )
        ],
    )

    mix = result["customer_mix"]
    assert result["fiscal_year"] == 2025
    assert [item["name"] for item in mix["major_customers"]] == [
        "Customer A",
        None,
        "Customer B",
        "Acme Corporation",
    ]
    assert mix["major_customers"][0]["revenue_percentage"] == 13
    assert mix["major_customers"][0]["customer_count"] == 1
    assert mix["major_customers"][1]["revenue_percentage"] == 11
    assert mix["major_customers"][2]["revenue_percentage"] is None
    assert mix["major_customers"][2]["percentage_basis"] == "accounts_receivable"
    assert mix["major_customers"][3]["percentage"] is None
    assert all(item["evidence"] for item in mix["major_customers"])
    assert all(
        item["source_url"].startswith("https://www.sec.gov")
        for item in mix["major_customers"]
    )
    assert all(
        item["filing_date"] == "2026-02-01"
        for item in mix["major_customers"]
    )
    assert any(
        risk["type"] == "customer_concentration"
        for risk in mix["risks"]
    )


def test_extracts_customer_types_channels_end_markets_and_latest_forms():
    result = extract_customer_mix(
        "EXM",
        [
            filing(
                """
                <h2>Business</h2>
                <p>We serve enterprise customers, cloud service providers,
                government agencies, and consumers.</p>
                <p>Our end markets include automotive, healthcare, financial
                services, industrial manufacturing, and telecommunications.</p>
                <p>We depend substantially on distributors and resellers to
                reach end customers in many markets.</p>
                """
            ),
            filing(
                """
                <h2>Risk Factors</h2>
                <p>Revenue remains concentrated among a limited number of
                enterprise customers, and the loss of a major customer could
                materially adversely affect our results.</p>
                """,
                form="10-Q",
                accession="0000000000-26-000002",
                filing_date="2026-05-01",
                report_date="2026-03-31",
            ),
        ],
    )

    mix = result["customer_mix"]
    assert [item["form"] for item in result["analyzed_filings"]] == [
        "10-K",
        "10-Q",
    ]
    assert {item["type"] for item in mix["customer_types"]} >= {
        "enterprise",
        "cloud_service_provider",
        "government",
        "consumer",
    }
    assert {item["type"] for item in mix["channel_dependencies"]} == {
        "distributor",
        "reseller",
    }
    assert {item["market"] for item in mix["end_markets"]} >= {
        "automotive",
        "healthcare_and_life_sciences",
        "financial_services",
        "industrial_and_manufacturing",
        "telecommunications",
    }
    assert any(
        risk["source_form"] == "10-Q"
        and risk["type"] == "customer_concentration"
        for risk in mix["risks"]
    )


def test_returns_empty_arrays_when_no_reliable_customer_mix_is_disclosed():
    result = extract_customer_mix(
        "BANK",
        [
            filing(
                """
                <h2>Business</h2>
                <p>We aim to provide high-quality service and build enduring
                relationships in the communities where we operate.</p>
                """
            )
        ],
    )

    assert result["customer_mix"] == {
        "major_customers": [],
        "customer_types": [],
        "channel_dependencies": [],
        "end_markets": [],
        "risks": [],
    }


def test_extracts_multiple_anonymous_customer_percentages_without_inventing_names():
    result = extract_customer_mix(
        "NVDA",
        [
            filing(
                """
                <h2>Customers</h2>
                <p>For the first quarter, three direct customers represented
                21%, 17%, and 16% of total revenue.</p>
                <p>For the prior year, sales to two direct customers each
                represented 11% of total revenue.</p>
                """
            )
        ],
    )

    customers = result["customer_mix"]["major_customers"]
    assert [item["revenue_percentage"] for item in customers] == [
        21,
        17,
        16,
        11,
    ]
    assert all(item["name"] is None for item in customers)
    assert customers[-1]["customer_count"] == 2


def test_rejects_geography_and_regulatory_customer_type_false_positives():
    result = extract_customer_mix(
        "NVDA",
        [
            filing(
                """
                <h2>Business</h2>
                <p>Revenue from sales to customers headquartered outside of
                the United States accounted for 22% of total revenue.</p>
                <p>The U.S. government announced export restrictions affecting
                the semiconductor industry.</p>
                <p>We are subject to consumer laws and consumer protection
                regulations in several jurisdictions.</p>
                <p>Our customers include enterprises and public sector
                entities.</p>
                """
            )
        ],
    )

    mix = result["customer_mix"]
    assert mix["major_customers"] == []
    assert mix["risks"] == []
    assert {item["type"] for item in mix["customer_types"]} == {
        "enterprise",
        "government",
    }
    assert all(
        "export restrictions" not in item["evidence"]
        and "consumer laws" not in item["evidence"]
        for item in mix["customer_types"]
    )


def test_semantically_deduplicates_repeated_filing_disclosures():
    result = extract_customer_mix(
        "EXM",
        [
            filing(
                """
                <h2>Business</h2>
                <p>Customer A represented 22% of total revenue.</p>
                <h2>Revenue Recognition</h2>
                <p>Customer A represented 22 % of total revenue.</p>
                <p>We depend on distributors to reach end customers.</p>
                <h2>Risk Factors</h2>
                <p>We depend on distributors to reach end customers.</p>
                """
            )
        ],
    )

    mix = result["customer_mix"]
    assert len(mix["major_customers"]) == 1
    assert len(mix["channel_dependencies"]) == 1


def test_reconstructs_split_industry_customer_types_from_20_f():
    result = extract_customer_mix(
        "TSM",
        [
            filing(
                """
                <h2>Business</h2>
                <p>We count among our customers many of the world's leading
                semiconductor companies, ranging from fabless</p>
                <p>semiconductor companies, system companies to integrated
                device manufacturers.</p>
                """,
                form="20-F",
            )
        ],
    )

    assert {
        item["type"]
        for item in result["customer_mix"]["customer_types"]
    } == {
        "fabless_semiconductor_company",
        "system_company",
        "integrated_device_manufacturer",
    }


def test_financing_receivables_are_not_customer_concentration_risk():
    result = extract_customer_mix(
        "SOLR",
        [
            filing(
                """
                <h2>Concentration of Credit Risk</h2>
                <p>Our accounts receivable balances associated with sales of
                energy storage products depend on billing milestones and
                contractual payment terms. We provide customer financing
                options, and financing receivables include amounts that may
                become past due. The allowance for credit losses reflects
                expected losses on customer financing receivables.</p>
                """
            )
        ],
    )

    assert result["customer_mix"]["risks"] == []


def test_extracts_energy_industry_customer_and_vehicle_markets():
    result = extract_customer_mix(
        "XOM",
        [
            filing(
                """
                <h2>Business</h2>
                <p>We see an opportunity to grow a carbon capture business
                that will enable industrial customers to reduce emissions.</p>
                <p>We are developing lithium to supply the global battery and
                electric vehicle markets.</p>
                """
            )
        ],
    )

    mix = result["customer_mix"]
    assert {
        item["type"] for item in mix["customer_types"]
    } == {"industrial_customer"}
    assert {
        item["market"] for item in mix["end_markets"]
    } >= {"automotive"}


def test_government_policy_is_not_a_government_end_market():
    result = extract_customer_mix(
        "ENER",
        [
            filing(
                """
                <h2>Business</h2>
                <p>Development of markets for lower-emission products depends
                on supportive government policies and new technology.</p>
                """
            )
        ],
    )

    assert all(
        item["market"] != "government"
        for item in result["customer_mix"]["end_markets"]
    )


def test_extracts_manufacturer_and_data_center_customer_types():
    result = extract_customer_mix(
        "CAT",
        [
            filing(
                """
                <h2>Business</h2>
                <p>We sell engines through dealers and to other manufacturers
                for use in their products.</p>
                <p>Data center customers purchase prime power solutions to
                support their growth.</p>
                """
            )
        ],
    )

    assert {
        item["type"]
        for item in result["customer_mix"]["customer_types"]
    } == {
        "manufacturer_customer",
        "data_center_customer",
    }


def test_rejects_negated_threshold_revenue_movement_and_accounting_channels():
    result = extract_customer_mix(
        "MSFT",
        [
            filing(
                """
                <h2>Business</h2>
                <p>No sales to an individual customer accounted for more than
                10% of revenue.</p>
                <p>Enterprise and partner services revenue increased during
                the year.</p>
                <p>Changes in consumer and business spending could reduce
                demand for our products.</p>
                <p>Revenue from retail stores and online marketplaces is
                recognized when control transfers to the customer.</p>
                <p>Amounts paid to resellers are accounted for as a reduction
                of revenue.</p>
                """
            )
        ],
    )

    mix = result["customer_mix"]
    assert mix["major_customers"] == []
    assert mix["customer_types"] == []
    assert mix["channel_dependencies"] == []
    assert mix["end_markets"] == []
    assert mix["risks"] == []
