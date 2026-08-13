"""Async Supabase persistence for provider and news cache data.

Only the backend secret-key client may use these repositories. Cache failures
are intentionally surfaced to callers so they can degrade to provider data
without confusing an infrastructure failure with a genuine cache miss.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from time import monotonic
from typing import Any, Protocol, Sequence
from weakref import WeakKeyDictionary

from supabase import AsyncClient, acreate_client

from app.core.config import Settings, get_settings


FINANCIAL_CACHE_TABLE = "provider_cache_entries"
NEWS_CACHE_TABLE = "news_cache_articles"
NEWS_RETENTION_DAYS = 30
NEWS_RESULT_LIMIT = 500
_CLEANUP_INTERVAL_SECONDS = 3600


class CacheUnavailableError(RuntimeError):
    """Raised when the configured Supabase cache cannot be used."""


@dataclass(frozen=True)
class CacheEntry:
    payload: Any
    fetched_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class NewsCacheRecord:
    ticker: str
    url: str
    published_at: datetime
    payload: dict[str, Any]


class FinancialCacheRepository(Protocol):
    async def get_financial(
        self,
        ticker: str,
        data_type: str,
        *,
        now: datetime | None = None,
    ) -> CacheEntry | None: ...

    async def upsert_financial(
        self,
        ticker: str,
        data_type: str,
        payload: Any,
        *,
        fetched_at: datetime,
        expires_at: datetime,
    ) -> None: ...


class NewsCacheRepository(Protocol):
    async def list_news(
        self,
        ticker: str,
        *,
        cutoff: datetime | None = None,
    ) -> list[dict[str, Any]]: ...

    async def upsert_news(self, records: Sequence[NewsCacheRecord]) -> None: ...

    async def purge_news(self, *, cutoff: datetime | None = None) -> None: ...


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _utc(value).isoformat()


def _parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Supabase returned a non-string timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return _utc(parsed)


class SupabaseCacheRepository:
    """PostgREST-backed implementation shared by active cache consumers."""

    def __init__(self, client: AsyncClient, *, timeout_seconds: float = 5.0) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._last_cleanup = 0.0

    async def _execute(self, query: Any) -> Any:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await query.execute()
        except Exception as exc:
            import logging
            logging.getLogger("uvicorn.error").error(
                "supabase_cache_request_failed",
                extra={"error_type": type(exc).__name__},
            )
            raise CacheUnavailableError("Supabase cache request failed") from exc

    async def get_financial(
        self,
        ticker: str,
        data_type: str,
        *,
        now: datetime | None = None,
    ) -> CacheEntry | None:
        current = _utc(now or datetime.now(timezone.utc))
        query = (
            self._client.table(FINANCIAL_CACHE_TABLE)
            .select("payload,fetched_at,expires_at")
            .eq("ticker", ticker.upper())
            .eq("data_type", data_type)
            .gt("expires_at", _timestamp(current))
            .limit(1)
        )
        response = await self._execute(query)
        rows = response.data or []
        if not rows:
            return None
        row = rows[0]
        return CacheEntry(
            payload=row["payload"],
            fetched_at=_parse_timestamp(row["fetched_at"]),
            expires_at=_parse_timestamp(row["expires_at"]),
        )

    async def upsert_financial(
        self,
        ticker: str,
        data_type: str,
        payload: Any,
        *,
        fetched_at: datetime,
        expires_at: datetime,
    ) -> None:
        row = {
            "ticker": ticker.upper(),
            "data_type": data_type,
            "payload": payload,
            "fetched_at": _timestamp(fetched_at),
            "expires_at": _timestamp(expires_at),
        }
        await self._execute(
            self._client.table(FINANCIAL_CACHE_TABLE).upsert(
                row,
                on_conflict="ticker,data_type",
            )
        )
        await self.cleanup_expired()

    async def list_news(
        self,
        ticker: str,
        *,
        cutoff: datetime | None = None,
    ) -> list[dict[str, Any]]:
        threshold = cutoff or (
            datetime.now(timezone.utc) - timedelta(days=NEWS_RETENTION_DAYS)
        )
        query = (
            self._client.table(NEWS_CACHE_TABLE)
            .select("payload")
            .eq("ticker", ticker.upper())
            .gte("published_at", _timestamp(threshold))
            .order("published_at", desc=True)
            .limit(NEWS_RESULT_LIMIT)
        )
        response = await self._execute(query)
        return [row["payload"] for row in (response.data or [])]

    async def upsert_news(self, records: Sequence[NewsCacheRecord]) -> None:
        if not records:
            return
        rows = [
            {
                "ticker": record.ticker.upper(),
                "url": record.url,
                "published_at": _timestamp(record.published_at),
                "payload": record.payload,
                "cached_at": _timestamp(datetime.now(timezone.utc)),
            }
            for record in records
        ]
        await self._execute(
            self._client.table(NEWS_CACHE_TABLE).upsert(
                rows,
                on_conflict="ticker,url",
            )
        )

    async def purge_news(self, *, cutoff: datetime | None = None) -> None:
        threshold = cutoff or (
            datetime.now(timezone.utc) - timedelta(days=NEWS_RETENTION_DAYS)
        )
        await self._execute(
            self._client.table(NEWS_CACHE_TABLE)
            .delete()
            .lt("published_at", _timestamp(threshold))
        )

    async def cleanup_expired(self, *, now: datetime | None = None) -> None:
        current_monotonic = monotonic()
        if current_monotonic - self._last_cleanup < _CLEANUP_INTERVAL_SECONDS:
            return
        await self._execute(
            self._client.table(FINANCIAL_CACHE_TABLE)
            .delete()
            .lte("expires_at", _timestamp(now or datetime.now(timezone.utc)))
        )
        self._last_cleanup = current_monotonic


@dataclass
class _LoopRepositoryState:
    lock: asyncio.Lock
    repository: SupabaseCacheRepository | None = None
    key: tuple[str, str, float] | None = None


_repository_states_guard = Lock()
_repository_states: WeakKeyDictionary[asyncio.AbstractEventLoop, _LoopRepositoryState] = WeakKeyDictionary()


async def _close_repository(repository: SupabaseCacheRepository | None) -> None:
    if repository is None:
        return
    postgrest = getattr(repository._client, "_postgrest", None)
    if postgrest is not None:
        await postgrest.aclose()


async def get_cache_repository(
    settings: Settings | None = None,
) -> SupabaseCacheRepository:
    """Return a secret-key cache repository bound to the current event loop."""

    resolved = settings or get_settings()
    if not resolved.supabase_url or not resolved.supabase_secret_key:
        raise CacheUnavailableError("Supabase cache is not configured")

    key = (
        resolved.supabase_url,
        resolved.supabase_secret_key,
        resolved.supabase_timeout_seconds,
    )
    loop = asyncio.get_running_loop()
    with _repository_states_guard:
        state = _repository_states.get(loop)
        if state is None:
            state = _LoopRepositoryState(lock=asyncio.Lock())
            _repository_states[loop] = state

    async with state.lock:
        if state.repository is not None and state.key == key:
            return state.repository

        await _close_repository(state.repository)
        client = await acreate_client(resolved.supabase_url, resolved.supabase_secret_key)
        state.repository = SupabaseCacheRepository(
            client,
            timeout_seconds=resolved.supabase_timeout_seconds,
        )
        state.key = key
        return state.repository


async def close_cache_repository() -> None:
    """Close the PostgREST connection pool bound to the current event loop."""
    loop = asyncio.get_running_loop()
    with _repository_states_guard:
        state = _repository_states.pop(loop, None)
    if state is None:
        return
    async with state.lock:
        await _close_repository(state.repository)
        state.repository = None
        state.key = None
