from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.repositories import supabase_cache

from app.repositories.supabase_cache import (
    CacheUnavailableError,
    NewsCacheRecord,
    SupabaseCacheRepository,
)


UTC = timezone.utc


class FakeQuery:
    def __init__(self, client, table):
        self.client = client
        self.table = table
        self.operations = []

    def _record(self, name, *args, **kwargs):
        self.operations.append((name, args, kwargs))
        return self

    def select(self, *args, **kwargs):
        return self._record("select", *args, **kwargs)

    def eq(self, *args, **kwargs):
        return self._record("eq", *args, **kwargs)

    def gt(self, *args, **kwargs):
        return self._record("gt", *args, **kwargs)

    def gte(self, *args, **kwargs):
        return self._record("gte", *args, **kwargs)

    def lt(self, *args, **kwargs):
        return self._record("lt", *args, **kwargs)

    def lte(self, *args, **kwargs):
        return self._record("lte", *args, **kwargs)

    def limit(self, *args, **kwargs):
        return self._record("limit", *args, **kwargs)

    def order(self, *args, **kwargs):
        return self._record("order", *args, **kwargs)

    def upsert(self, *args, **kwargs):
        return self._record("upsert", *args, **kwargs)

    def delete(self, *args, **kwargs):
        return self._record("delete", *args, **kwargs)

    async def execute(self):
        self.client.calls.append(self)
        response = self.client.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(data=response)


class FakeClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def table(self, name):
        return FakeQuery(self, name)


class FakePostgrest:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


class LoopBoundClient(FakeClient):
    def __init__(self):
        super().__init__()
        self.loop = asyncio.get_running_loop()
        self._postgrest = FakePostgrest()


def test_financial_cache_reads_jsonb_and_timestamps():
    client = FakeClient([{
        "payload": [{"revenue": 1}],
        "fetched_at": "2026-07-19T01:00:00Z",
        "expires_at": "2026-07-20T01:00:00+00:00",
    }])
    repository = SupabaseCacheRepository(client)

    entry = asyncio.run(repository.get_financial(
        "aapl",
        "income_statement:annual",
        now=datetime(2026, 7, 19, tzinfo=UTC),
    ))

    assert entry.payload == [{"revenue": 1}]
    assert entry.fetched_at == datetime(2026, 7, 19, 1, tzinfo=UTC)
    assert client.calls[0].table == "provider_cache_entries"
    assert ("eq", ("ticker", "AAPL"), {}) in client.calls[0].operations
    assert any(operation[0] == "gt" for operation in client.calls[0].operations)


def test_news_upsert_uses_per_ticker_url_conflict_key():
    client = FakeClient([])
    repository = SupabaseCacheRepository(client)
    record = NewsCacheRecord(
        ticker="AAPL",
        url="https://example.com/story",
        published_at=datetime(2026, 7, 19, tzinfo=UTC),
        payload={"url": "https://example.com/story"},
    )

    asyncio.run(repository.upsert_news([record]))

    operation = next(op for op in client.calls[0].operations if op[0] == "upsert")
    assert operation[2]["on_conflict"] == "ticker,url"
    assert operation[1][0][0]["ticker"] == "AAPL"


def test_repository_translates_client_failure_without_leaking_detail():
    client = FakeClient(RuntimeError("credential=must-not-be-surfaced"))
    repository = SupabaseCacheRepository(client)

    with pytest.raises(CacheUnavailableError, match="Supabase cache request failed") as exc_info:
        asyncio.run(repository.list_news("AAPL"))

    assert "credential" not in str(exc_info.value)


def test_default_repository_is_scoped_to_the_current_event_loop(monkeypatch):
    created_clients = []

    async def fake_create_client(*_args):
        client = LoopBoundClient()
        created_clients.append(client)
        return client

    settings = SimpleNamespace(
        supabase_url="https://example.supabase.co",
        supabase_secret_key="secret",
        supabase_timeout_seconds=5.0,
    )
    monkeypatch.setattr(supabase_cache, "acreate_client", fake_create_client)

    async def resolve_on_current_loop():
        first = await supabase_cache.get_cache_repository(settings)
        second = await supabase_cache.get_cache_repository(settings)
        assert first is second
        assert first._client.loop is asyncio.get_running_loop()
        await supabase_cache.close_cache_repository()

    asyncio.run(resolve_on_current_loop())
    asyncio.run(resolve_on_current_loop())

    assert len(created_clients) == 2
    assert all(client._postgrest.closed for client in created_clients)
