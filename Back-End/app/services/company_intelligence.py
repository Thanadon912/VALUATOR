from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import monotonic, time
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.config import get_settings
from app.core.runtime_paths import runtime_cache_path
from app.core.validation import normalize_ticker


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FILING_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
FMP_BASE_URL = "https://financialmodelingprep.com/stable"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
CLASSIFICATION_CACHE_TTL_SECONDS = 14 * 24 * 60 * 60
DEGRADED_CLASSIFICATION_CACHE_TTL_SECONDS = 60
CLASSIFICATION_CACHE_DIR = runtime_cache_path("company-classification")


class CompetitorClassification(BaseModel):
    ticker: str
    overlap_score: float = Field(alias="overlapScore", ge=0, le=100)
    reason: str

    @field_validator("overlap_score", mode="before")
    @classmethod
    def normalize_overlap_score(cls, value: Any) -> Any:
        parsed = float(value)
        return parsed * 100 if 0 <= parsed <= 1 else parsed

    model_config = ConfigDict(populate_by_name=True)


class CompanyClassification(BaseModel):
    ticker: str
    cik: str
    sic_code: str = Field(alias="sicCode")
    sic_description: str = Field(alias="sicDescription")
    sector: str
    industry: str
    business_tags: list[str] = Field(alias="businessTags")
    revenue_segments: list[str] = Field(alias="revenueSegments")
    competitors: list[CompetitorClassification]
    is_adr: bool = Field(default=False, alias="isAdr")
    adr_ratio: float = Field(default=1.0, alias="adrRatio")
    updated_at: str = Field(alias="updatedAt")
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


_cache_lock = Lock()
_classification_cache: dict[str, tuple[float, CompanyClassification]] = {}
_classification_fetch_locks: dict[str, Lock] = {}


def _classification_fetch_lock(ticker: str) -> Lock:
    with _cache_lock:
        return _classification_fetch_locks.setdefault(ticker, Lock())


def _classification_ttl(result: CompanyClassification) -> int:
    return (
        CLASSIFICATION_CACHE_TTL_SECONDS
        if result.competitors
        else DEGRADED_CLASSIFICATION_CACHE_TTL_SECONDS
    )


def _memory_cached_classification(ticker: str) -> CompanyClassification | None:
    with _cache_lock:
        cached = _classification_cache.get(ticker)
        if cached and monotonic() - cached[0] < _classification_ttl(cached[1]):
            return cached[1]
    return None


def _classification_cache_path(ticker: str) -> Path:
    return CLASSIFICATION_CACHE_DIR / f"{ticker}.json"


def _load_persistent_classification(ticker: str) -> CompanyClassification | None:
    try:
        payload = json.loads(_classification_cache_path(ticker).read_text(encoding="utf-8"))
        saved_at = float(payload["saved_at"])
        result = CompanyClassification.model_validate(payload["classification"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if not result.competitors or time() - saved_at >= CLASSIFICATION_CACHE_TTL_SECONDS:
        return None
    with _cache_lock:
        _classification_cache[ticker] = (monotonic(), result)
    return result


def _save_persistent_classification(result: CompanyClassification) -> None:
    if not result.competitors:
        return
    path = _classification_cache_path(result.ticker)
    temporary = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(
                {
                    "saved_at": time(),
                    "classification": result.model_dump(by_alias=True),
                },
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        temporary.replace(path)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _safe_provider_failure(exc: Exception) -> str:
    """Describe provider failures without exposing credential-bearing URLs."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP_{exc.response.status_code}"
    return type(exc).__name__


def _text_from_html(raw_html: str) -> str:
    without_blocks = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw_html)
    without_tags = re.sub(r"(?s)<[^>]+>", " ", without_blocks)
    return re.sub(r"\s+", " ", html.unescape(without_tags)).strip()


def _extract_item_one(filing_html: str) -> str:
    text = _text_from_html(filing_html)
    sections: list[str] = []
    for start in re.finditer(r"\bitem\s+1[.:\s]+business\b", text, re.IGNORECASE):
        tail = text[start.start():]
        end = re.search(r"\bitem\s+1a[.:\s]+risk\s+factors\b", tail, re.IGNORECASE)
        sections.append(tail[: end.start() if end else 60_000][:60_000])
    return max(sections, key=len, default="")


def _extract_fpi_business_section(filing_html: str, form: str) -> str:
    if form != "20-F":
        return _extract_item_one(filing_html)
    text = _text_from_html(filing_html)
    sections: list[str] = []
    for start in re.finditer(r"\bitem\s+4[.:\s]+information\s+on\s+the\s+company\b", text, re.IGNORECASE):
        tail = text[start.start():]
        end = re.search(r"\bitem\s+4a[.:\s]+unresolved\s+staff\s+comments\b", tail, re.IGNORECASE)
        sections.append(tail[: end.start() if end else 60_000][:60_000])
    return max(sections, key=len, default="")


def _gemini_json(client: httpx.Client, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    response = client.post(
        GEMINI_URL.format(model=settings.gemini_supply_chain_model),
        params={"key": settings.gemini_api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        },
    )
    response.raise_for_status()
    payload = response.json()
    raw = payload["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Gemini returned a non-object response")
    return parsed


class CompanyIntelligenceService:
    """Builds filing-grounded tags and ranked peers without static fallbacks."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=settings.provider_timeout_seconds,
            headers={"User-Agent": settings.sec_user_agent},
            follow_redirects=True,
        )
        self._submissions_by_cik: dict[str, dict[str, Any]] = {}

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def classify(self, ticker: str) -> CompanyClassification:
        normalized = normalize_ticker(ticker)
        cached = _memory_cached_classification(normalized)
        if cached is not None:
            return cached
        persistent = _load_persistent_classification(normalized)
        if persistent is not None:
            return persistent

        with _classification_fetch_lock(normalized):
            cached = _memory_cached_classification(normalized)
            if cached is not None:
                return cached
            persistent = _load_persistent_classification(normalized)
            if persistent is not None:
                return persistent
            return self._classify_uncached(normalized)

    def _classify_uncached(self, normalized: str) -> CompanyClassification:

        warnings: list[str] = []
        identity = self._resolve_sec_identity(normalized)
        tags: list[str] = []
        segments: list[str] = []
        filing_text = self._fetch_latest_business_section(identity["cik"])
        if filing_text:
            try:
                tags, segments = self._extract_tags(normalized, filing_text)
            except Exception as exc:
                warnings.append(f"LLM_TAG_EXTRACTION_UNAVAILABLE: {_safe_provider_failure(exc)}")
        else:
            warnings.append("SEC_ITEM_1_UNAVAILABLE")

        candidates = self._fetch_peer_candidates(normalized, identity["sicCode"], warnings)
        competitors: list[CompetitorClassification] = []
        if candidates and tags:
            try:
                competitors = self._score_peers(normalized, tags, segments, candidates)
            except Exception as exc:
                warnings.append(f"LLM_PEER_SCORING_UNAVAILABLE: {_safe_provider_failure(exc)}")
        elif not candidates:
            warnings.append("FMP_PEER_CANDIDATES_UNAVAILABLE")
        elif not tags:
            warnings.append("BUSINESS_TAGS_UNAVAILABLE_FOR_PEER_SCORING")

        if candidates and not competitors:
            competitors = [
                CompetitorClassification(
                    ticker=c,
                    overlap_score=50.0,
                    reason="Fallback peer due to unavailable AI scoring"
                )
                for c in candidates[:4]
            ]

        result = CompanyClassification(
            ticker=normalized,
            cik=identity["cik"],
            sicCode=identity.get("sicCode", ""),
            sicDescription=identity.get("sicDescription", ""),
            sector=identity.get("sector", ""),
            industry=identity.get("industry", ""),
            businessTags=tags,
            revenueSegments=segments,
            competitors=competitors,
            isAdr=identity.get("isAdr", False),
            adrRatio=identity.get("adrRatio", 1.0),
            updatedAt=datetime.now(timezone.utc).isoformat(),
            warnings=warnings,
        )
        with _cache_lock:
            _classification_cache[normalized] = (monotonic(), result)
        _save_persistent_classification(result)
        return result

    def _resolve_sec_identity(self, ticker: str) -> dict[str, str | bool | float]:
        response = self.client.get(SEC_TICKERS_URL)
        response.raise_for_status()
        rows = response.json().values()
        match = next((row for row in rows if str(row.get("ticker", "")).upper() == ticker), None)
        if not match:
            raise ValueError(f"SEC identity not found for {ticker}")
        cik = str(match["cik_str"]).zfill(10)
        submissions = self.client.get(SEC_SUBMISSIONS_URL.format(cik=cik))
        submissions.raise_for_status()
        data = submissions.json()
        self._submissions_by_cik[cik] = data
        sector = ""
        industry = str(data.get("sicDescription") or "")
        
        addresses = data.get("addresses", {})
        business_address = addresses.get("business", {})
        is_foreign = business_address.get("isForeignLocation") == 1
        state_incorp = str(data.get("stateOfIncorporation", "")).strip()
        
        # Consider it potentially foreign if isForeignLocation is true or stateOfIncorporation is missing/unusual
        is_suspected_adr = is_foreign or (not state_incorp)
        
        is_adr = False
        adr_ratio = 1.0

        api_key = get_settings().fmp_api_key
        if api_key:
            if is_suspected_adr:
                try:
                    profile_response = self.client.get(
                        f"{FMP_BASE_URL}/sec-profile",
                        params={"symbol": ticker, "apikey": api_key},
                    )
                    profile_response.raise_for_status()
                    profiles = profile_response.json()
                    profile = profiles[0] if isinstance(profiles, list) and profiles else {}
                    sector = str(profile.get("sector") or "")
                    industry = str(profile.get("industry") or industry)
                    
                    is_adr_from_api = profile.get("isAdr", False)
                    is_adr = bool(is_adr_from_api)
                    
                    fetched_ratio = profile.get("adrRatio")
                    if fetched_ratio:
                        adr_ratio = float(fetched_ratio)
                except Exception:
                    pass
            else:
                # Domestic US stock, bypass FMP sec-profile fetch to optimize API costs
                pass
                
        return {
            "cik": cik,
            "sicCode": str(data.get("sic") or "").zfill(4),
            "sicDescription": str(data.get("sicDescription") or ""),
            "sector": sector,
            "industry": industry,
            "isAdr": is_adr,
            "adrRatio": adr_ratio,
        }

    def _fetch_latest_business_section(self, cik: str) -> str:
        submissions = getattr(self, "_submissions_by_cik", {}).get(cik)
        if submissions is None:
            response = self.client.get(SEC_SUBMISSIONS_URL.format(cik=cik))
            response.raise_for_status()
            submissions = response.json()
        recent = submissions.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        for index, form in enumerate(forms):
            if form not in {"10-K", "20-F", "40-F"}:
                continue
            accession = recent["accessionNumber"][index].replace("-", "")
            document = recent["primaryDocument"][index]
            filing = self.client.get(
                SEC_FILING_URL.format(cik=int(cik), accession=accession, document=document)
            )
            filing.raise_for_status()
            return _extract_fpi_business_section(filing.text, form)
        return ""

    def _extract_tags(self, ticker: str, item_one: str) -> tuple[list[str], list[str]]:
        prompt = (
            f"Extract company classification from {ticker}'s SEC Item 1 below. "
            "Return 3-5 concise, high-signal businessTags and factual revenueSegments explicitly supported "
            "by the filing. Use stable investor-facing labels, not broad sectors. Do not infer missing segments.\n\n"
            f"ITEM 1:\n{item_one}"
        )
        parsed = _gemini_json(self.client, prompt, {
            "type": "OBJECT",
            "properties": {
                "businessTags": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 3, "maxItems": 5},
                "revenueSegments": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
            "required": ["businessTags", "revenueSegments"],
        })
        return list(dict.fromkeys(parsed["businessTags"]))[:5], list(dict.fromkeys(parsed["revenueSegments"]))

    def _fetch_peer_candidates(self, ticker: str, sic_code: str, warnings: list[str]) -> list[str]:
        api_key = get_settings().fmp_api_key
        if not api_key:
            return []
        candidates: list[str] = []
        endpoints = [
            ("stock-peers", {"symbol": ticker, "apikey": api_key}),
            ("industry-classification-search", {"sicCode": sic_code, "apikey": api_key}),
        ]
        for endpoint, params in endpoints:
            try:
                response = self.client.get(f"{FMP_BASE_URL}/{endpoint}", params=params)
                response.raise_for_status()
                for row in response.json() if isinstance(response.json(), list) else []:
                    values = row.get("peersList", []) if isinstance(row, dict) else []
                    if isinstance(row, str):
                        values = [row]
                    elif isinstance(row, dict) and not values:
                        values = [row.get("symbol") or row.get("ticker")]
                    for value in values:
                        symbol = str(value or "").upper().strip()
                        if symbol and symbol != ticker and symbol not in candidates:
                            candidates.append(symbol)
            except Exception as exc:
                warnings.append(
                    f"FMP_{endpoint.upper().replace('-', '_')}_UNAVAILABLE: "
                    f"{_safe_provider_failure(exc)}"
                )
        return candidates

    def _score_peers(self, ticker: str, tags: list[str], segments: list[str], candidates: list[str]) -> list[CompetitorClassification]:
        prompt = (
            f"Rank true operating competitors for {ticker}. Target businessTags: {json.dumps(tags)}. "
            f"Target revenueSegments: {json.dumps(segments)}. Candidate tickers: {json.dumps(candidates[:50])}. "
            "Score only by business-tag overlap and revenue-segment alignment. Return at most 4 candidates, "
            "highest score first. Do not include a ticker outside the candidate list. Give a concise factual reason."
        )
        parsed = _gemini_json(self.client, prompt, {
            "type": "OBJECT",
            "properties": {"competitors": {"type": "ARRAY", "maxItems": 4, "items": {
                "type": "OBJECT",
                "properties": {
                    "ticker": {"type": "STRING"},
                    "overlapScore": {"type": "NUMBER"},
                    "reason": {"type": "STRING"},
                },
                "required": ["ticker", "overlapScore", "reason"],
            }}},
            "required": ["competitors"],
        })
        allowed = set(candidates)
        peers = [CompetitorClassification.model_validate(row) for row in parsed["competitors"] if row.get("ticker", "").upper() in allowed]
        return sorted(peers, key=lambda peer: peer.overlap_score, reverse=True)[:4]


def get_company_classification(ticker: str) -> CompanyClassification:
    service = CompanyIntelligenceService()
    try:
        return service.classify(ticker)
    finally:
        service.close()


def get_cached_company_classification(ticker: str) -> CompanyClassification | None:
    normalized = normalize_ticker(ticker)
    return _memory_cached_classification(normalized) or _load_persistent_classification(normalized)
