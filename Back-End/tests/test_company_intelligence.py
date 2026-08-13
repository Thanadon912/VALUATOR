from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import Mock

from app.services import company_intelligence
from app.services.company_intelligence import (
    CompanyClassification,
    CompanyIntelligenceService,
    CompetitorClassification,
    _extract_item_one,
    _extract_fpi_business_section,
    _safe_provider_failure,
    _load_persistent_classification,
    _save_persistent_classification,
)
import httpx


def test_extract_item_one_stops_before_risk_factors():
    filing = """
    <html><body><h2>Item 1. Business</h2><p>Builds electric vehicles and energy storage.</p>
    <h2>Item 1A. Risk Factors</h2><p>This text must not be included.</p></body></html>
    """

    extracted = _extract_item_one(filing)

    assert "electric vehicles" in extracted
    assert "must not be included" not in extracted


def test_extracts_20f_item_four_company_section():
    filing = """
    <h2>Item 4. Information on the Company</h2><p>Manufactures advanced semiconductors.</p>
    <h2>Item 4A. Unresolved Staff Comments</h2><p>Exclude this section.</p>
    """
    extracted = _extract_fpi_business_section(filing, "20-F")
    assert "advanced semiconductors" in extracted
    assert "Exclude this section" not in extracted


def test_peer_candidates_merge_and_deduplicate(monkeypatch):
    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        def get(self, url, params=None):
            if url.endswith("stock-peers"):
                return Response([{"peersList": ["F", "GM", "F"]}])
            return Response([{"symbol": "GM"}, {"symbol": "RIVN"}])

    monkeypatch.setattr("app.services.company_intelligence.get_settings", lambda: type("Settings", (), {"fmp_api_key": "key"})())
    service = CompanyIntelligenceService.__new__(CompanyIntelligenceService)
    service.client = Client()
    warnings = []

    assert service._fetch_peer_candidates("TSLA", "3711", warnings) == ["F", "GM", "RIVN"]
    assert warnings == []


def test_peer_scoring_is_descending_and_limited_to_candidates(monkeypatch):
    service = CompanyIntelligenceService.__new__(CompanyIntelligenceService)
    service.client = object()
    monkeypatch.setattr(
        "app.services.company_intelligence._gemini_json",
        lambda client, prompt, schema: {"competitors": [
            {"ticker": "GM", "overlapScore": 72, "reason": "Vehicle manufacturing"},
            {"ticker": "F", "overlapScore": 91, "reason": "EV and vehicle sales"},
            {"ticker": "FAKE", "overlapScore": 100, "reason": "Not a candidate"},
        ]},
    )

    peers = service._score_peers("TSLA", ["EVs"], ["Automotive"], ["F", "GM"])

    assert peers == [
        CompetitorClassification(ticker="F", overlapScore=91, reason="EV and vehicle sales"),
        CompetitorClassification(ticker="GM", overlapScore=72, reason="Vehicle manufacturing"),
    ]


def test_fractional_overlap_score_is_normalized_to_percentage():
    peer = CompetitorClassification(
        ticker="MSFT",
        overlapScore=0.95,
        reason="Cloud and AI overlap",
    )

    assert peer.overlap_score == 95


def test_provider_failure_does_not_expose_url_credentials():
    request = httpx.Request(
        "GET",
        "https://provider.example/peers?apikey=must-not-leak",
    )
    response = httpx.Response(429, request=request)
    error = httpx.HTTPStatusError("rate limited", request=request, response=response)

    warning = _safe_provider_failure(error)

    assert warning == "HTTP_429"
    assert "must-not-leak" not in warning


def _classification(ticker="CACHE", *, competitors=True):
    peer_rows = (
        [{"ticker": "MSFT", "overlapScore": 80, "reason": "Comparable business"}]
        if competitors
        else []
    )
    return CompanyClassification(
        ticker=ticker,
        cik="0000000001",
        sicCode="7372",
        sicDescription="Software",
        sector="Technology",
        industry="Software",
        businessTags=["Cloud"],
        revenueSegments=["Software"],
        competitors=peer_rows,
        updatedAt=datetime.now(timezone.utc).isoformat(),
    )


def test_classification_cache_coalesces_concurrent_provider_calls(monkeypatch, tmp_path):
    company_intelligence._classification_cache.clear()
    company_intelligence._classification_fetch_locks.clear()
    monkeypatch.setattr(company_intelligence, "CLASSIFICATION_CACHE_DIR", tmp_path)
    service = CompanyIntelligenceService.__new__(CompanyIntelligenceService)
    def classify_once(ticker):
        result = _classification(ticker)
        with company_intelligence._cache_lock:
            company_intelligence._classification_cache[ticker] = (
                company_intelligence.monotonic(),
                result,
            )
        return result

    upstream = Mock(side_effect=classify_once)
    monkeypatch.setattr(service, "_classify_uncached", upstream)

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(service.classify, ["cache"] * 8))

    assert upstream.call_count == 1
    assert all(result.competitors[0].ticker == "MSFT" for result in results)


def test_successful_classification_persists_across_memory_reset(monkeypatch, tmp_path):
    company_intelligence._classification_cache.clear()
    monkeypatch.setattr(company_intelligence, "CLASSIFICATION_CACHE_DIR", tmp_path)
    result = _classification("PERSIST")

    _save_persistent_classification(result)
    company_intelligence._classification_cache.clear()

    restored = _load_persistent_classification("PERSIST")
    assert restored is not None
    assert restored.competitors[0].ticker == "MSFT"


def test_sec_submissions_payload_is_reused_for_business_section(monkeypatch):
    class Response:
        def __init__(self, payload=None, text=""):
            self._payload = payload
            self.text = text

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    submissions = {
        "sic": "7372",
        "sicDescription": "Software",
        "stateOfIncorporation": "DE",
        "addresses": {"business": {}},
        "filings": {"recent": {
            "form": ["10-K"],
            "accessionNumber": ["0000000001-26-000001"],
            "primaryDocument": ["annual.htm"],
        }},
    }

    class Client:
        def __init__(self):
            self.urls = []

        def get(self, url, **kwargs):
            self.urls.append(url)
            if url == company_intelligence.SEC_TICKERS_URL:
                return Response({"0": {"ticker": "TEST", "cik_str": 1}})
            if "/submissions/" in url:
                return Response(submissions)
            return Response(text="<h2>Item 1. Business</h2>Cloud software<h2>Item 1A. Risk Factors</h2>")

    client = Client()
    service = CompanyIntelligenceService(client=client)
    identity = service._resolve_sec_identity("TEST")
    section = service._fetch_latest_business_section(identity["cik"])

    assert "Cloud software" in section
    assert sum("/submissions/" in url for url in client.urls) == 1
