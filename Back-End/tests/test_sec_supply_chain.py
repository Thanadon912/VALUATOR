from app.providers.sec_supply_chain import extract_supply_chain_exposure


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


def test_extracts_only_explicit_named_relationships_with_evidence():
    result = extract_supply_chain_exposure(
        "EXM",
        [
            filing(
                """
                <h2>Risk Factors</h2>
                <p>We rely on TSMC for substantially all fabrication of our
                advanced semiconductors, and a disruption at TSMC could
                materially adversely affect production.</p>
                <p>Industry reports identify another possible supplier.</p>
                """
            )
        ],
    )

    exposure = result["supply_chain_exposure"]
    assert result["fiscal_year"] == 2025
    assert exposure["suppliers"][0]["name"] == "TSMC"
    assert exposure["suppliers"][0]["relationship_type"] == "foundry"
    assert exposure["suppliers"][0]["confidence"] == 0.98
    assert exposure["suppliers"][0]["section"] == "risk_factors"
    assert exposure["suppliers"][0]["source_url"].startswith("https://www.sec.gov")
    assert "advanced semiconductors" in exposure["suppliers"][0]["evidence"]
    assert all(
        item["name"] != "another possible supplier"
        for item in exposure["suppliers"]
    )
    assert any(
        risk["type"] == "supply_chain_disruption"
        for risk in exposure["risks"]
    )


def test_extracts_locations_materials_concentration_and_latest_forms():
    result = extract_supply_chain_exposure(
        "EXM",
        [
            filing(
                """
                <h2>Business</h2>
                <p>Approximately 80% of our products are manufactured in China
                by contract manufacturers.</p>
                <p>We depend on a limited number of suppliers for lithium
                battery cells and semiconductors.</p>
                <p>Our largest customer accounted for 31% of revenue.</p>
                """
            ),
            filing(
                """
                <h2>Management's Discussion and Analysis</h2>
                <p>Supplier shortages delayed production during the quarter.</p>
                """,
                form="10-Q",
                accession="0000000000-26-000002",
                filing_date="2026-05-01",
                report_date="2026-03-31",
            ),
        ],
    )

    exposure = result["supply_chain_exposure"]
    assert [item["form"] for item in result["analyzed_filings"]] == [
        "10-K",
        "10-Q",
    ]
    assert exposure["manufacturing_locations"][0]["country"] == "China"
    assert exposure["manufacturing_locations"][0]["percentage"] == 80
    assert {
        item["material"] for item in exposure["raw_material_dependencies"]
    } == {"battery cells", "lithium", "semiconductors"}
    assert exposure["customer_concentrations"][0]["percentage"] == 31
    assert exposure["customer_concentrations"][0]["name"] is None
    assert any(
        risk["type"] == "supplier_concentration"
        for risk in exposure["risks"]
    )
    assert any(
        risk["source_form"] == "10-Q"
        and risk["type"] == "supply_chain_disruption"
        for risk in exposure["risks"]
    )


def test_returns_empty_arrays_when_filing_has_no_reliable_disclosure():
    result = extract_supply_chain_exposure(
        "BANK",
        [
            filing(
                """
                <h2>Business</h2>
                <p>We provide commercial banking and wealth management
                services to customers throughout the United States.</p>
                """
            )
        ],
    )

    assert result["supply_chain_exposure"] == {
        "suppliers": [],
        "manufacturing_locations": [],
        "raw_material_dependencies": [],
        "customer_concentrations": [],
        "risks": [],
    }


def test_rejects_generic_components_and_ranks_one_best_risk_per_type():
    result = extract_supply_chain_exposure(
        "MSFT",
        [
            filing(
                """
                <h2>Risk Factors</h2>
                <p>Unexpected events could disrupt the supply of components
                used by our operations.</p>
                """,
                accession="older",
                filing_date="2025-02-01",
            ),
            filing(
                """
                <h2>Risk Factors</h2>
                <p>A significant disruption of our semiconductor supply chain
                could have a material adverse effect on production.</p>
                """,
                form="10-Q",
                accession="newer",
                filing_date="2026-05-01",
            ),
        ],
    )

    exposure = result["supply_chain_exposure"]
    assert "components" not in {
        item["material"] for item in exposure["raw_material_dependencies"]
    }
    disruption_risks = [
        item for item in exposure["risks"]
        if item["type"] == "supply_chain_disruption"
    ]
    assert len(disruption_risks) == 1
    assert disruption_risks[0]["severity"] == "high"
    assert disruption_risks[0]["source_accession"] == "newer"
