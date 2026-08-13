from app.providers.sec_customer_mix import (
    collect_customer_mix_passages,
    extract_customer_mix,
)
from app.providers.sec_customer_mix_ai import (
    CustomerMixAiInvalidResponse,
    CustomerMixAiRateLimited,
    CustomerMixAiTimeout,
    GeminiCustomerMixExtractor,
    extract_customer_mix_with_fallback,
    _customer_type_supported,
)
from app.providers import sec_customer_mix_ai


def filing(
    html: str,
    *,
    accession: str = "0000000000-26-000001",
) -> dict[str, str]:
    return {
        "form": "20-F",
        "accession": accession,
        "filing_date": "2026-04-16",
        "report_date": "2025-12-31",
        "source_url": "https://www.sec.gov/example.htm",
        "html": html,
    }


def tsm_like_filing() -> dict[str, str]:
    return filing(
        """
        <h2>Customers</h2>
        <p>Over the years, our customer profile and the nature of our
        customers' business have changed dramatically.</p>
        <p>Our ten largest customers in 2023, 2024 and 2025 accounted for</p>
        <p>approximately 70%, 76% and 78% of our net revenue in the respective
        year. Our largest customer in 2023, 2024 and 2025</p>
        <p>accounted for 25%, 22% and 19% of our net revenue in the respective
        year. Our second largest customer in 2023, 2024 and</p>
        <p>2025 accounted for 11%, 12%, and 17% of our net revenue in the
        respective year.</p>
        <p>This customer concentration results in part from the structural
        shift to HPC and smartphone applications.</p>
        <p>Our customers include system companies.</p>
        """
    )


def test_candidate_windows_reconstruct_split_20_f_disclosure():
    passages = collect_customer_mix_passages([tsm_like_filing()])

    assert any(
        "ten largest customers" in item["evidence"]
        and "second largest customer" in item["evidence"]
        and "17%" in item["evidence"]
        for item in passages
    )


def test_ai_extracts_multi_year_customer_groups_with_exact_evidence(monkeypatch):
    filings = [tsm_like_filing()]
    passage = next(
        item
        for item in collect_customer_mix_passages(filings)
        if "second largest customer" in item["evidence"]
    )
    extractor = GeminiCustomerMixExtractor("key", "model", 1)
    monkeypatch.setattr(
        extractor,
        "_request",
        lambda prompt: {
            "major_customers": [
                {
                    "passage_id": passage["passage_id"],
                    "name": None,
                    "customer_count": 10,
                    "percentage": 0.78,
                    "percentage_basis": "revenue",
                    "percentage_scope": "customer_group",
                    "period": "2025",
                    "rank": "top_customers",
                },
                {
                    "passage_id": passage["passage_id"],
                    "name": None,
                    "customer_count": 1,
                    "percentage": 19,
                    "percentage_basis": "revenue",
                    "percentage_scope": "single_customer",
                    "period": "2025",
                    "rank": "largest",
                },
                {
                    "passage_id": passage["passage_id"],
                    "name": None,
                    "customer_count": 1,
                    "percentage": 17,
                    "percentage_basis": "revenue",
                    "percentage_scope": "single_customer",
                    "period": "2025",
                    "rank": "second_largest",
                },
            ],
            "customer_types": [
                {
                    "passage_id": passage["passage_id"],
                    "type": "system_company",
                }
            ],
            "channel_dependencies": [],
            "end_markets": [
                {
                    "passage_id": passage["passage_id"],
                    "market": "HPC",
                },
                {
                    "passage_id": passage["passage_id"],
                    "market": "smartphone applications",
                },
            ],
            "risks": [
                {
                    "passage_id": passage["passage_id"],
                    "type": "customer_concentration",
                }
            ],
        },
    )

    result = extractor.extract("TSM", filings)
    mix = result["customer_mix"]

    assert result["extraction"]["method"] == "ai"
    assert {
        (
            item["period"],
            item["revenue_percentage"],
            item["percentage_scope"],
        )
        for item in mix["major_customers"]
    } == {
        ("2025", 78, "customer_group"),
        ("2025", 19, "single_customer"),
        ("2025", 17, "single_customer"),
    }
    assert {item["market"] for item in mix["end_markets"]} == {
        "HPC",
        "smartphone applications",
    }
    assert {item["type"] for item in mix["customer_types"]} == {
        "system_company",
    }
    assert mix["risks"][0]["type"] == "customer_concentration"
    assert all(
        item["source_url"] == "https://www.sec.gov/example.htm"
        for item in mix["major_customers"]
    )


def test_ai_rejects_hallucinated_customer_name(monkeypatch):
    filings = [tsm_like_filing()]
    passage = next(
        item
        for item in collect_customer_mix_passages(filings)
        if "largest customer" in item["evidence"]
    )
    extractor = GeminiCustomerMixExtractor("key", "model", 1)
    monkeypatch.setattr(
        extractor,
        "_request",
        lambda prompt: {
            "major_customers": [
                {
                    "passage_id": passage["passage_id"],
                    "name": "Apple Inc.",
                    "customer_count": 1,
                    "percentage": 19,
                    "percentage_basis": "revenue",
                    "percentage_scope": "single_customer",
                    "period": "2025",
                    "rank": "largest",
                }
            ],
            "customer_types": [],
            "channel_dependencies": [],
            "end_markets": [],
            "risks": [],
        },
    )

    result = extractor.extract("TSM", filings)

    assert result["customer_mix"]["major_customers"] == []


def test_rate_limit_uses_different_secondary_model(monkeypatch):
    filings = [filing(
        "<h2>Customers</h2><p>Customer A represented 12% of revenue.</p>",
        accession="rate-limit-secondary",
    )]

    def extract(self, ticker, documents):
        if self.model == "primary":
            raise CustomerMixAiRateLimited("quota")
        result = extract_customer_mix(ticker, documents)
        result["extraction"].update(
            {
                "method": "ai",
                "provider": "google_gemini",
                "model": self.model,
            }
        )
        return result

    monkeypatch.setattr(GeminiCustomerMixExtractor, "extract", extract)

    result, warning = extract_customer_mix_with_fallback(
        "EXM",
        filings,
        enabled=True,
        api_key="key",
        primary_model="primary",
        secondary_model="secondary",
        timeout_seconds=1,
        rate_limit_cooldown_seconds=60,
    )

    assert result["extraction"]["method"] == "ai"
    assert result["extraction"]["model"] == "secondary"
    assert result["extraction"]["attempted_models"] == [
        "primary",
        "secondary",
    ]
    assert result["extraction"]["model_failover_used"] is True
    assert result["extraction"]["model_failover_reason"] == "rate_limited"
    assert warning and "secondary" in warning


def test_all_models_fall_back_to_deterministic(monkeypatch):
    filings = [filing(
        "<h2>Customers</h2><p>Customer A represented 12% of revenue.</p>",
        accession="all-models-fail",
    )]

    def unavailable(self, ticker, documents):
        if self.model == "primary-all-fail":
            raise CustomerMixAiRateLimited("quota")
        raise CustomerMixAiTimeout("timeout")

    monkeypatch.setattr(GeminiCustomerMixExtractor, "extract", unavailable)

    result, warning = extract_customer_mix_with_fallback(
        "EXM",
        filings,
        enabled=True,
        api_key="key",
        primary_model="primary-all-fail",
        secondary_model="secondary-all-fail",
        timeout_seconds=1,
        rate_limit_cooldown_seconds=60,
    )

    assert result["extraction"]["method"] == "deterministic"
    assert result["extraction"]["fallback_used"] is True
    assert result["extraction"]["attempted_models"] == [
        "primary-all-fail",
        "secondary-all-fail",
    ]
    assert (
        "primary-all-fail=rate_limited"
        in result["extraction"]["fallback_reason"]
    )
    assert (
        "secondary-all-fail=timeout"
        in result["extraction"]["fallback_reason"]
    )
    assert result["customer_mix"]["major_customers"]
    assert warning and "deterministic" in warning


def test_invalid_primary_response_uses_secondary_model(monkeypatch):
    filings = [filing(
        "<h2>Customers</h2><p>Customer A represented 12% of revenue.</p>",
        accession="invalid-primary",
    )]

    def extract(self, ticker, documents):
        if self.model == "invalid-primary-model":
            raise CustomerMixAiInvalidResponse("invalid json")
        result = extract_customer_mix(ticker, documents)
        result["extraction"].update(
            {
                "method": "ai",
                "provider": "google_gemini",
                "model": self.model,
            }
        )
        return result

    monkeypatch.setattr(GeminiCustomerMixExtractor, "extract", extract)

    result, warning = extract_customer_mix_with_fallback(
        "EXM",
        filings,
        enabled=True,
        api_key="key",
        primary_model="invalid-primary-model",
        secondary_model="valid-secondary-model",
        timeout_seconds=1,
    )

    assert result["extraction"]["model"] == "valid-secondary-model"
    assert result["extraction"]["model_failover_reason"] == "invalid_response"
    assert warning and "valid-secondary-model" in warning


def test_ai_result_merges_deterministic_customer_type_coverage(monkeypatch):
    filings = [filing(
        """
        <h2>Business</h2>
        <p>We count among our customers fabless semiconductor companies,
        system companies and integrated device manufacturers.</p>
        """
    )]
    passage = collect_customer_mix_passages(filings)[0]
    extractor = GeminiCustomerMixExtractor("key", "model", 1)
    monkeypatch.setattr(
        extractor,
        "_request",
        lambda prompt: {
            "major_customers": [],
            "customer_types": [],
            "channel_dependencies": [],
            "end_markets": [],
            "risks": [],
        },
    )

    result = extractor.extract("TSM", filings)

    assert {
        item["type"]
        for item in result["customer_mix"]["customer_types"]
    } == {
        "fabless_semiconductor_company",
        "system_company",
        "integrated_device_manufacturer",
    }


def test_ai_preserves_generic_explicit_customer_type_label(monkeypatch):
    filings = [filing(
        """
        <h2>Business</h2>
        <p>Our customers include commercial airlines and cargo carriers.</p>
        """
    )]
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
                    "label": "commercial airlines",
                }
            ],
            "channel_dependencies": [],
            "end_markets": [],
            "risks": [],
        },
    )

    result = extractor.extract("AIR", filings)
    customer_type = result["customer_mix"]["customer_types"][0]

    assert customer_type["type"] == "other_explicit_type"
    assert customer_type["label"] == "commercial airlines"


def test_industrial_customer_type_validator_is_registered():
    assert _customer_type_supported(
        "industrial_customer",
        "We provide carbon capture services to industrial customers.",
    )


def test_industrial_customer_validators_cover_manufacturing_and_data_centers():
    assert _customer_type_supported(
        "manufacturer_customer",
        "We sell engines to other manufacturers for use in products.",
    )
    assert _customer_type_supported(
        "data_center_customer",
        "Data center customers purchase prime power solutions.",
    )


def test_persistent_cache_survives_in_memory_cache_reset(
    monkeypatch,
    tmp_path,
):
    filings = [filing(
        "<h2>Customers</h2><p>Customer A represented 12% of revenue.</p>",
        accession="persistent-cache",
    )]
    calls = 0

    def successful(self, ticker, documents):
        nonlocal calls
        calls += 1
        result = extract_customer_mix(ticker, documents)
        result["extraction"].update(
            {
                "method": "ai",
                "provider": "google_gemini",
                "model": self.model,
            }
        )
        return result

    monkeypatch.setattr(GeminiCustomerMixExtractor, "extract", successful)
    first, _ = extract_customer_mix_with_fallback(
        "EXM",
        filings,
        enabled=True,
        api_key="key",
        primary_model="persistent-primary",
        secondary_model="persistent-secondary",
        timeout_seconds=1,
        cache_dir=str(tmp_path),
    )
    sec_customer_mix_ai._ai_cache.clear()
    sec_customer_mix_ai._model_cooldowns.clear()

    def must_not_run(self, ticker, documents):
        raise AssertionError("AI should not run after a process restart.")

    monkeypatch.setattr(
        GeminiCustomerMixExtractor,
        "extract",
        must_not_run,
    )
    second, _ = extract_customer_mix_with_fallback(
        "EXM",
        filings,
        enabled=True,
        api_key="key",
        primary_model="different-primary",
        secondary_model="different-secondary",
        timeout_seconds=1,
        cache_dir=str(tmp_path),
    )

    assert calls == 1
    assert first["customer_mix"] == second["customer_mix"]
    assert second["extraction"]["cache_source"] == "persistent"


def test_extractor_version_mismatch_invalidates_persistent_cache(
    monkeypatch,
    tmp_path,
):
    filings = [filing(
        "<h2>Customers</h2><p>Customer A represented 12% of revenue.</p>",
        accession="versioned-cache",
    )]

    def successful(self, ticker, documents):
        result = extract_customer_mix(ticker, documents)
        result["extraction"].update(
            {
                "method": "ai",
                "provider": "google_gemini",
                "model": self.model,
            }
        )
        return result

    monkeypatch.setattr(GeminiCustomerMixExtractor, "extract", successful)
    extract_customer_mix_with_fallback(
        "EXM",
        filings,
        enabled=True,
        api_key="key",
        primary_model="version-primary",
        secondary_model="version-secondary",
        timeout_seconds=1,
        cache_dir=str(tmp_path),
    )
    cache_file = next(tmp_path.glob("*.json"))
    payload = __import__("json").loads(cache_file.read_text())
    payload["extractor_version"] = "obsolete-version"
    cache_file.write_text(__import__("json").dumps(payload))
    sec_customer_mix_ai._ai_cache.clear()
    calls = 0

    def refreshed(self, ticker, documents):
        nonlocal calls
        calls += 1
        return successful(self, ticker, documents)

    monkeypatch.setattr(GeminiCustomerMixExtractor, "extract", refreshed)
    result, _ = extract_customer_mix_with_fallback(
        "EXM",
        filings,
        enabled=True,
        api_key="key",
        primary_model="version-primary",
        secondary_model="version-secondary",
        timeout_seconds=1,
        cache_dir=str(tmp_path),
    )

    assert calls == 1
    assert result["extraction"]["cache_source"] == "fresh"
