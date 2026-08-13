from app.providers.sec_supply_chain import (
    collect_supply_chain_passages,
    extract_supply_chain_exposure,
)
from app.providers.sec_supply_chain_ai import (
    GeminiSupplyChainExtractor,
    SupplyChainAiError,
    SupplyChainAiRateLimited,
    extract_supply_chain_with_fallback,
)
from app.providers import sec_supply_chain_ai


def filing(
    html: str,
    *,
    accession: str = "0000000000-26-000001",
) -> dict[str, str]:
    return {
        "form": "10-K",
        "accession": accession,
        "filing_date": "2026-02-01",
        "report_date": "2025-12-31",
        "source_url": "https://www.sec.gov/example.htm",
        "html": html,
    }


def test_ai_accepts_explicit_partner_and_attaches_exact_sec_evidence(monkeypatch):
    filings = [
        filing(
            """
            <h2>Manufacturing</h2>
            <p>We rely on Acme Semiconductor Ltd. as our primary foundry for
            fabrication of advanced chips.</p>
            """
        )
    ]
    passage_id = collect_supply_chain_passages(filings)[0]["passage_id"]
    extractor = GeminiSupplyChainExtractor("key", "model", 1)
    monkeypatch.setattr(
        extractor,
        "_request",
        lambda prompt: {
            "suppliers": [
                {
                    "passage_id": passage_id,
                    "name": "Acme Semiconductor Ltd.",
                    "relationship_type": "foundry",
                    "dependency_type": "disclosed_relationship",
                }
            ],
            "manufacturing_locations": [],
            "raw_material_dependencies": [],
            "customer_concentrations": [],
            "risks": [],
        },
    )

    result = extractor.extract("EXM", filings)
    supplier = result["supply_chain_exposure"]["suppliers"][0]

    assert result["extraction"]["method"] == "ai"
    assert supplier["name"] == "Acme Semiconductor Ltd."
    assert supplier["source_url"] == "https://www.sec.gov/example.htm"
    assert supplier["confidence"] == 0.95
    assert "primary foundry" in supplier["evidence"]


def test_ai_rejects_hallucinated_partner_not_present_in_evidence(monkeypatch):
    filings = [
        filing(
            """
            <h2>Risk Factors</h2>
            <p>We rely on a limited number of unnamed suppliers for critical
            semiconductor components.</p>
            """
        )
    ]
    passage_id = collect_supply_chain_passages(filings)[0]["passage_id"]
    extractor = GeminiSupplyChainExtractor("key", "model", 1)
    monkeypatch.setattr(
        extractor,
        "_request",
        lambda prompt: {
            "suppliers": [
                {
                    "passage_id": passage_id,
                    "name": "TSMC",
                    "relationship_type": "foundry",
                    "dependency_type": "limited_source",
                }
            ],
            "manufacturing_locations": [],
            "raw_material_dependencies": [],
            "customer_concentrations": [],
            "risks": [],
        },
    )

    result = extractor.extract("EXM", filings)

    assert result["supply_chain_exposure"]["suppliers"] == []


def test_ai_accepts_named_partners_in_explicit_supplier_list(monkeypatch):
    filings = [
        filing(
            """
            <h2>Manufacturing</h2>
            <p>We utilize foundries, such as Acme Foundry Ltd. and Example
            Semiconductor Inc., to produce our semiconductor wafers.</p>
            """
        )
    ]
    passage_id = collect_supply_chain_passages(filings)[0]["passage_id"]
    extractor = GeminiSupplyChainExtractor("key", "model", 1)
    monkeypatch.setattr(
        extractor,
        "_request",
        lambda prompt: {
            "suppliers": [
                {
                    "passage_id": passage_id,
                    "name": "Acme Foundry Ltd.",
                    "relationship_type": "foundry",
                    "dependency_type": "disclosed_relationship",
                },
                {
                    "passage_id": passage_id,
                    "name": "Example Semiconductor Inc.",
                    "relationship_type": "foundry",
                    "dependency_type": "disclosed_relationship",
                },
            ],
            "manufacturing_locations": [],
            "raw_material_dependencies": [],
            "customer_concentrations": [],
            "risks": [],
        },
    )

    result = extractor.extract("EXM", filings)

    assert {
        supplier["name"]
        for supplier in result["supply_chain_exposure"]["suppliers"]
    } == {"Acme Foundry Ltd.", "Example Semiconductor Inc."}


def test_rate_limit_falls_back_to_deterministic_extractor(monkeypatch):
    filings = [
        filing(
            """
            <h2>Business</h2>
            <p>We depend on a limited number of suppliers for lithium battery
            cells.</p>
            """
        )
    ]

    def rate_limited(self, ticker, documents):
        raise SupplyChainAiRateLimited("quota")

    monkeypatch.setattr(GeminiSupplyChainExtractor, "extract", rate_limited)

    result, warning = extract_supply_chain_with_fallback(
        "EXM",
        filings,
        enabled=True,
        api_key="key",
        model="model",
        timeout_seconds=1,
    )

    assert result["extraction"]["method"] == "deterministic"
    assert result["extraction"]["fallback_used"] is True
    assert result["extraction"]["fallback_reason"] == "rate_limited"
    assert result["supply_chain_exposure"]["raw_material_dependencies"]
    assert warning and "deterministic" in warning


def test_supply_chain_ai_reports_fresh_then_memory_cache(monkeypatch):
    filings = [filing(
        "<h2>Business</h2><p>We depend on suppliers for semiconductor wafers.</p>",
        accession="memory-cache",
    )]
    calls = 0

    def successful(self, ticker, documents):
        nonlocal calls
        calls += 1
        result = extract_supply_chain_exposure(ticker, documents)
        result["extraction"].update({
            "method": "ai",
            "provider": "google_gemini",
            "model": self.model,
            "cache_source": "fresh",
        })
        return result

    sec_supply_chain_ai._ai_cache.clear()
    monkeypatch.setattr(GeminiSupplyChainExtractor, "extract", successful)
    first, _ = extract_supply_chain_with_fallback(
        "EXM", filings, enabled=True, api_key="key", model="memory-model",
        timeout_seconds=1,
    )
    second, _ = extract_supply_chain_with_fallback(
        "EXM", filings, enabled=True, api_key="key", model="memory-model",
        timeout_seconds=1,
    )

    assert calls == 1
    assert first["extraction"]["cache_source"] == "fresh"
    assert second["extraction"]["cache_source"] == "memory"


def test_supply_chain_persistent_cache_survives_memory_reset(monkeypatch, tmp_path):
    filings = [filing(
        "<h2>Business</h2><p>We depend on suppliers for semiconductor wafers.</p>",
        accession="persistent-cache",
    )]
    calls = 0

    def successful(self, ticker, documents):
        nonlocal calls
        calls += 1
        result = extract_supply_chain_exposure(ticker, documents)
        result["extraction"].update({
            "method": "ai",
            "provider": "google_gemini",
            "model": self.model,
            "cache_source": "fresh",
        })
        return result

    sec_supply_chain_ai._ai_cache.clear()
    monkeypatch.setattr(GeminiSupplyChainExtractor, "extract", successful)
    first, _ = extract_supply_chain_with_fallback(
        "EXM", filings, enabled=True, api_key="key", model="persistent-model",
        timeout_seconds=1, cache_dir=str(tmp_path),
    )
    sec_supply_chain_ai._ai_cache.clear()

    def must_not_run(self, ticker, documents):
        raise AssertionError("AI should not run when the persistent cache matches.")

    monkeypatch.setattr(GeminiSupplyChainExtractor, "extract", must_not_run)
    second, _ = extract_supply_chain_with_fallback(
        "EXM", filings, enabled=True, api_key="key", model="different-model",
        timeout_seconds=1, cache_dir=str(tmp_path),
    )

    assert calls == 1
    assert first["supply_chain_exposure"] == second["supply_chain_exposure"]
    assert second["extraction"]["cache_source"] == "persistent"


def test_supply_chain_cache_invalidates_version_and_accession(monkeypatch, tmp_path):
    filings = [filing(
        "<h2>Business</h2><p>We depend on suppliers for semiconductor wafers.</p>",
        accession="version-one",
    )]
    calls = 0

    def successful(self, ticker, documents):
        nonlocal calls
        calls += 1
        result = extract_supply_chain_exposure(ticker, documents)
        result["extraction"].update({
            "method": "ai", "provider": "google_gemini", "model": self.model,
        })
        return result

    sec_supply_chain_ai._ai_cache.clear()
    monkeypatch.setattr(GeminiSupplyChainExtractor, "extract", successful)
    extract_supply_chain_with_fallback(
        "EXM", filings, enabled=True, api_key="key", model="version-model",
        timeout_seconds=1, cache_dir=str(tmp_path),
    )
    cache_file = next(tmp_path.glob("*.json"))
    import json
    payload = json.loads(cache_file.read_text())
    payload["extractor_version"] = "obsolete"
    cache_file.write_text(json.dumps(payload))
    sec_supply_chain_ai._ai_cache.clear()

    refreshed, _ = extract_supply_chain_with_fallback(
        "EXM", filings, enabled=True, api_key="key", model="version-model",
        timeout_seconds=1, cache_dir=str(tmp_path),
    )
    changed_accession, _ = extract_supply_chain_with_fallback(
        "EXM",
        [filing(filings[0]["html"], accession="version-two")],
        enabled=True, api_key="key", model="version-model",
        timeout_seconds=1, cache_dir=str(tmp_path),
    )

    assert calls == 3
    assert refreshed["extraction"]["cache_source"] == "fresh"
    assert changed_accession["extraction"]["cache_source"] == "fresh"


def test_supply_chain_deterministic_fallback_is_not_persisted(monkeypatch, tmp_path):
    filings = [filing(
        "<h2>Business</h2><p>We depend on suppliers for semiconductor wafers.</p>",
        accession="fallback-not-cached",
    )]

    def failed(self, ticker, documents):
        raise SupplyChainAiError("provider unavailable")

    sec_supply_chain_ai._ai_cache.clear()
    monkeypatch.setattr(GeminiSupplyChainExtractor, "extract", failed)
    fallback, _ = extract_supply_chain_with_fallback(
        "EXM", filings, enabled=True, api_key="key", model="fallback-model",
        timeout_seconds=1, cache_dir=str(tmp_path),
    )
    assert fallback["extraction"]["fallback_used"] is True
    assert list(tmp_path.glob("*.json")) == []

    calls = 0

    def recovered(self, ticker, documents):
        nonlocal calls
        calls += 1
        result = extract_supply_chain_exposure(ticker, documents)
        result["extraction"].update({
            "method": "ai", "provider": "google_gemini", "model": self.model,
        })
        return result

    monkeypatch.setattr(GeminiSupplyChainExtractor, "extract", recovered)
    result, _ = extract_supply_chain_with_fallback(
        "EXM", filings, enabled=True, api_key="key", model="fallback-model",
        timeout_seconds=1, cache_dir=str(tmp_path),
    )

    assert calls == 1
    assert result["extraction"]["method"] == "ai"
    assert result["extraction"]["cache_source"] == "fresh"
