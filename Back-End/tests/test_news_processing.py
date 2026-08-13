import asyncio
from types import SimpleNamespace

from app.api.routes import news as news_route
from app.api.routes.news import _filter_and_dedupe_news, _safe_provider_image_url


def _article(article_id: int, headline: str, timestamp: int) -> dict:
    return {
        "id": article_id,
        "headline": headline,
        "summary": "Apple product update",
        "source": "Example News",
        "url": f"https://example.com/{article_id}",
        "datetime": timestamp,
    }


def test_provider_image_url_requires_absolute_https_without_credentials() -> None:
    assert _safe_provider_image_url("https://cdn.example.com/image.jpg") == "https://cdn.example.com/image.jpg"
    assert _safe_provider_image_url("http://169.254.169.254/latest/meta-data") == ""
    assert _safe_provider_image_url("https://user:password@example.com/image.jpg") == ""
    assert _safe_provider_image_url("data:image/png;base64,AAAA") == ""


def test_filter_and_dedupe_news_removes_near_duplicates() -> None:
    data = [
        _article(1, "Apple launches a new product today", 20_000),
        _article(2, "Apple launches a new product today", 19_900),
        _article(3, "Apple reports a separate business update", 19_800),
    ]

    result = _filter_and_dedupe_news(data, "AAPL")

    assert [item["id"] for item in result] == [1, 3]


def test_filter_and_dedupe_news_keeps_similar_old_headline() -> None:
    data = [
        _article(1, "Apple launches a new product today", 100_000),
        _article(2, "Apple launches a new product today", 40_000),
    ]

    result = _filter_and_dedupe_news(data, "AAPL")

    assert [item["id"] for item in result] == [1, 2]


def test_news_serves_supabase_cache_when_provider_key_is_missing(monkeypatch) -> None:
    payload = {
        "id": 1,
        "headline": "Apple reports a business update",
        "summary": "Apple product update",
        "source": "Example News",
        "timestamp": 100_000,
        "url": "https://example.com/1",
        "image": "",
        "topic": "Company",
        "relevance_score": 90,
    }

    class NewsRepository:
        async def purge_news(self, *, cutoff=None):
            return None

        async def upsert_news(self, records):
            return None

        async def list_news(self, ticker, *, cutoff=None):
            return [payload]

    async def repository(settings):
        return NewsRepository()

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    monkeypatch.setattr(news_route, "get_cache_repository", repository)
    monkeypatch.setattr(news_route.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(
        news_route,
        "get_settings",
        lambda: SimpleNamespace(finnhub_api_key=None),
    )
    monkeypatch.setattr(
        news_route,
        "get_company_classification",
        lambda ticker: None,
    )
    news_route._last_fetch.clear()
    news_route._response_cache.clear()

    response = asyncio.run(news_route.get_news("aapl"))

    assert [article.url for article in response.articles] == [payload["url"]]
    assert "Finnhub API key not configured" in response.status


def test_news_reuses_assembled_response_without_repeating_dependencies(monkeypatch) -> None:
    calls = {"repository": 0, "classification": 0}

    class NewsRepository:
        async def list_news(self, ticker, *, cutoff=None):
            return []

    async def repository(settings):
        calls["repository"] += 1
        return NewsRepository()

    async def run_inline(function, *args, **kwargs):
        return function(*args, **kwargs)

    def classify(ticker):
        calls["classification"] += 1
        return None

    monkeypatch.setattr(news_route, "get_cache_repository", repository)
    monkeypatch.setattr(news_route.asyncio, "to_thread", run_inline)
    monkeypatch.setattr(news_route, "get_company_classification", classify)
    monkeypatch.setattr(news_route, "get_settings", lambda: SimpleNamespace(finnhub_api_key=None))
    news_route._last_fetch.clear()
    news_route._response_cache.clear()

    first = asyncio.run(news_route.get_news("AAPL"))
    second = asyncio.run(news_route.get_news("aapl"))

    assert second == first
    assert calls == {"repository": 1, "classification": 1}
