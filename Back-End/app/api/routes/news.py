import datetime
import difflib
import httpx
import logging
import asyncio
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List

from app.core.config import get_settings
from app.core.performance_cache import (
    is_performance_cache_only,
    raise_performance_cache_miss,
)
from app.core.validation import normalize_ticker
from app.repositories import NewsCacheRecord, NewsCacheRepository, get_cache_repository
from app.services.company_intelligence import CompanyClassification, get_company_classification

router = APIRouter(tags=["news"])
logger = logging.getLogger(__name__)

# Bucket C — Transient Dynamics cache.
# News feeds refresh realistically throughout the trading day but do not
# change second-by-second. A 30-minute store isolates news from the 14-day
# Bucket A structural cache while avoiding hammering Finnhub + og:image
# scrapers on every page re-entry.
NEWS_CACHE_TTL_SECONDS = 1800

_news_cache_lock = Lock()
_last_fetch: dict[str, float] = {}
_response_cache: dict[str, tuple[float, "NewsResponse"]] = {}

class NewsArticle(BaseModel):
    id: int
    headline: str
    summary: str
    source: str
    timestamp: int
    url: str
    image: str
    topic: str
    relevance_score: float

class NewsResponse(BaseModel):
    ticker: str
    articles: List[NewsArticle]
    status: str
    classification: CompanyClassification | None = None

BLACKLIST = [
    "options trading", "call option", "put option", "implied volatility", 
    "technical analysis", "short squeeze", "volatility alert", "option alert", 
    "shareholder lawsuit", "moving average", "death cross", "golden cross", 
    "bullish pennant"
]

RELEVANCE_MAP = {
    "AAPL": ["apple", "iphone", "mac", "ios", "ipad", "vision pro", "tim cook"],
    "MSFT": ["microsoft", "windows", "azure", "xbox", "copilot", "satya nadella"],
    "GOOGL": ["google", "alphabet", "youtube", "android", "pixel", "waymo", "sundar pichai"],
    "GOOG": ["google", "alphabet", "youtube", "android", "pixel", "waymo", "sundar pichai"],
    "AMZN": ["amazon", "aws", "prime", "alexa", "andy jassy", "jeff bezos"],
    "META": ["meta", "facebook", "instagram", "whatsapp", "oculus", "zuckerberg"],
    "TSLA": ["tesla", "musk", "model 3", "model y", "cybertruck", "gigafactory"],
    "NVDA": ["nvidia", "gpu", "rtx", "cuda", "jensen", "hopper", "blackwell"]
}


def _filter_and_dedupe_news(data: list[dict], ticker: str) -> list[dict]:
    """Run CPU-heavy relevance and similarity work outside the event loop."""
    valid_articles = []
    for item in data:
        headline = item.get("headline", "")
        url_link = item.get("url", "")
        source = item.get("source", "")
        if not headline or not url_link or not source:
            continue

        summary = item.get("summary", "")
        text_to_check = (headline + " " + summary).lower()
        if any(keyword in text_to_check for keyword in BLACKLIST):
            continue

        if ticker in RELEVANCE_MAP:
            tokens = RELEVANCE_MAP[ticker]
            if not any(token in text_to_check for token in tokens):
                continue
        valid_articles.append(item)

    valid_articles.sort(key=lambda item: item.get("datetime", 0), reverse=True)
    deduped = []
    for item in valid_articles:
        is_duplicate = False
        dt = item.get("datetime", 0)
        headline = item.get("headline", "")
        for existing in deduped:
            existing_dt = existing.get("datetime", 0)
            if existing_dt - dt > 12 * 3600:
                break
            if abs(existing_dt - dt) <= 12 * 3600:
                similarity = difflib.SequenceMatcher(
                    None,
                    headline.lower(),
                    existing.get("headline", "").lower(),
                ).ratio()
                if similarity >= 0.85:
                    is_duplicate = True
                    break
        if not is_duplicate:
            deduped.append(item)
    return deduped

def _safe_provider_image_url(value: object) -> str:
    """Return only absolute HTTPS image URLs; the backend never fetches them."""
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return ""
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return ""
    return value.strip()


@router.get("/api/stocks/{ticker}/news", response_model=NewsResponse)
async def get_news(ticker: str) -> NewsResponse:
    try:
        normalized_ticker = normalize_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if is_performance_cache_only():
        with _news_cache_lock:
            cached = _response_cache.get(normalized_ticker)
        if cached is None:
            raise_performance_cache_miss("news", normalized_ticker)
        return cached[1]

    # The assembled response is already fresh for the same interval as the
    # provider reservation. Return it before repeating classification and
    # Supabase reads on every tab revisit.
    with _news_cache_lock:
        cached = _response_cache.get(normalized_ticker)
        if cached and monotonic() - cached[0] < NEWS_CACHE_TTL_SECONDS:
            return cached[1]

    settings = get_settings()
    classification = None
    status_messages: list[str] = []
    try:
        classification = await asyncio.to_thread(get_company_classification, normalized_ticker)
    except Exception:
        status_messages.append("COMPANY_CLASSIFICATION_UNAVAILABLE")
        logger.exception(
            "news_company_classification_unavailable",
            extra={"ticker": normalized_ticker},
        )

    repository: NewsCacheRepository | None = None
    try:
        repository = await get_cache_repository(settings)
    except Exception:
        logger.warning(
            "supabase_cache_unavailable",
            extra={"cache_kind": "news", "ticker": normalized_ticker},
        )

    with _news_cache_lock:
        last_fetch = _last_fetch.get(normalized_ticker)
        should_fetch = last_fetch is None or (monotonic() - last_fetch > NEWS_CACHE_TTL_SECONDS)
        # Reserve this ticker before doing network work. Concurrent requests
        # serve the shared cache instead of duplicating provider traffic.
        if should_fetch:
            _last_fetch[normalized_ticker] = monotonic()

    fetched_articles: list[NewsArticle] = []
    data = None
    if should_fetch:
        if not settings.finnhub_api_key:
            status_messages.append("Finnhub API key not configured")
            with _news_cache_lock:
                _last_fetch.pop(normalized_ticker, None)
        else:
            if repository is not None:
                try:
                    await repository.purge_news()
                except Exception:
                    logger.warning(
                        "supabase_cache_cleanup_unavailable",
                        extra={"cache_kind": "news"},
                    )

            today = datetime.datetime.now(datetime.timezone.utc)
            from_date = (today - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
            to_date = today.strftime("%Y-%m-%d")
            provider_url = (
                "https://finnhub.io/api/v1/company-news"
                f"?symbol={normalized_ticker}&from={from_date}&to={to_date}"
                f"&token={settings.finnhub_api_key}"
            )
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(provider_url, timeout=15.0)
                    response.raise_for_status()
                    data = response.json()
            except Exception:
                status_messages.append("FINNHUB_NEWS_UNAVAILABLE")
                logger.warning(
                    "finnhub_news_unavailable",
                    extra={"ticker": normalized_ticker},
                )
                with _news_cache_lock:
                    _last_fetch.pop(normalized_ticker, None)

        if isinstance(data, list):
            deduped = await asyncio.to_thread(
                _filter_and_dedupe_news,
                data,
                normalized_ticker,
            )

            async def enrich_article(item: dict) -> NewsArticle:
                image = _safe_provider_image_url(item.get("image"))
                source = item.get("source", "")
                url = item.get("url", "")

                text_to_check = (item.get("headline", "") + " " + item.get("summary", "")).lower()
                topic = "Company"
                if "earnings" in text_to_check or "revenue" in text_to_check: topic = "Earnings"
                elif "rate" in text_to_check or "inflation" in text_to_check or "fed" in text_to_check: topic = "Macro"
                elif "lawsuit" in text_to_check or "regulator" in text_to_check or "sec " in text_to_check or "probe" in text_to_check: topic = "Regulatory"
                elif classification:
                    for business_tag in classification.business_tags:
                        normalized_tag = business_tag.lower().replace("-", " ")
                        tag_terms = [term for term in normalized_tag.split() if len(term) > 2]
                        if normalized_tag in text_to_check or (tag_terms and all(term in text_to_check for term in tag_terms)):
                            topic = business_tag
                            break

                relevance_score = round(min(100.0, 75.0 + (len(item.get("headline", "")) % 25)), 1)
                            
                return NewsArticle(
                    id=item.get("id", 0),
                    headline=item.get("headline", ""),
                    summary=item.get("summary", ""),
                    source=source,
                    timestamp=item.get("datetime", 0),
                    url=url,
                    image=image or "",
                    topic=topic,
                    relevance_score=relevance_score
                )

            tasks = [enrich_article(item) for item in deduped]
            fetched_articles = list(await asyncio.gather(*tasks))

            if repository is not None:
                records = [
                    NewsCacheRecord(
                        ticker=normalized_ticker,
                        url=article.url,
                        published_at=datetime.datetime.fromtimestamp(
                            article.timestamp,
                            tz=datetime.timezone.utc,
                        ),
                        payload=article.model_dump(),
                    )
                    for article in fetched_articles
                ]
                try:
                    await repository.upsert_news(records)
                except Exception:
                    logger.warning(
                        "supabase_cache_write_unavailable",
                        extra={"cache_kind": "news", "ticker": normalized_ticker},
                    )

    cached_articles: list[NewsArticle] = []
    if repository is not None:
        try:
            payloads = await repository.list_news(normalized_ticker)
            for payload in payloads:
                try:
                    cached_articles.append(NewsArticle.model_validate(payload))
                except (TypeError, ValueError):
                    pass
        except Exception:
            logger.warning(
                "supabase_cache_read_unavailable",
                extra={"cache_kind": "news", "ticker": normalized_ticker},
            )

    articles = cached_articles or fetched_articles
    if not articles:
        with _news_cache_lock:
            memory_cached = _response_cache.get(normalized_ticker)
        if memory_cached is not None:
            articles = memory_cached[1].articles

    status = "success"
    if status_messages:
        status = f"success; {'; '.join(dict.fromkeys(status_messages))}"
    result = NewsResponse(
        ticker=normalized_ticker,
        articles=articles,
        status=status,
        classification=classification,
    )
    with _news_cache_lock:
        _response_cache[normalized_ticker] = (monotonic(), result)
    return result
