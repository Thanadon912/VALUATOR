from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from app.providers.fmp_financials import (
    EARNINGS_WINDOW_STATEMENT_TTL,
    METADATA_TTL,
    OFF_SEASON_STATEMENT_TTL,
    FMPFinancialsProvider,
    STATIC_ADR_MAP,
    _apply_adr_fallback,
    statement_ttl,
)
from app.repositories import CacheEntry
from app.providers.unified_financials import _map_fmp_to_sec_rows
from app.api.routes.valuation import format_response


UTC = timezone.utc


class MemoryFinancialCache:
    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], CacheEntry] = {}

    async def get_financial(self, ticker, data_type, *, now=None):
        current = now or datetime.now(UTC)
        entry = self.entries.get((ticker.upper(), data_type))
        if entry is None or entry.expires_at <= current:
            return None
        return entry

    async def upsert_financial(
        self,
        ticker,
        data_type,
        payload,
        *,
        fetched_at,
        expires_at,
    ):
        self.entries[(ticker.upper(), data_type)] = CacheEntry(
            payload=payload,
            fetched_at=fetched_at,
            expires_at=expires_at,
        )


def test_statement_ttl_uses_inclusive_earnings_window():
    now = datetime(2026, 7, 12, 8, tzinfo=UTC)
    for offset in (-7, 0, 7):
        assert statement_ttl(now, now.date() + timedelta(days=offset)) == EARNINGS_WINDOW_STATEMENT_TTL
    for offset in (-8, 8):
        assert statement_ttl(now, now.date() + timedelta(days=offset)) == OFF_SEASON_STATEMENT_TTL
    assert statement_ttl(now, None) == OFF_SEASON_STATEMENT_TTL


def test_financial_cache_contract_expires_entries():
    cache = MemoryFinancialCache()
    now = datetime(2026, 7, 12, tzinfo=UTC)
    asyncio.run(cache.upsert_financial(
        "aapl",
        "income_statement:annual",
        [{"revenue": 1}],
        fetched_at=now,
        expires_at=now + timedelta(hours=1),
    ))

    fresh = asyncio.run(cache.get_financial("AAPL", "income_statement:annual", now=now))
    expired = asyncio.run(cache.get_financial(
        "AAPL",
        "income_statement:annual",
        now=now + timedelta(hours=1),
    ))
    assert fresh.payload == [{"revenue": 1}]
    assert expired is None


def test_fmp_provider_cache_hit_makes_zero_followup_api_calls():
    now = datetime(2026, 7, 12, 8, tzinfo=UTC)
    cache = MemoryFinancialCache()

    class FakeProvider(FMPFinancialsProvider):
        calls = 0

        async def _get_json(self, client, url, params):
            self.calls += 1
            if url.endswith("/sec-profile"):
                return [{"isAdr": True, "adrRatio": 5}]
            if url.endswith("/earnings"):
                return [{"date": "2026-07-15"}]
            return [{"date": "2026-03-31", "period": "Q1", "reportedCurrency": "USD"}]

    provider = FakeProvider(api_key="test", cache=cache, now=lambda: now)
    first = asyncio.run(provider.fetch_financials("tsm"))
    assert provider.calls == 9  # profile + earnings + six statements + annual consensus
    assert first["metadata"]["next_earnings_date"] == "2026-07-15"

    provider.calls = 0
    second = asyncio.run(provider.fetch_financials("TSM"))
    assert provider.calls == 0
    assert second["statements"] == first["statements"]

    metadata = asyncio.run(cache.get_financial("TSM", "company_metadata", now=now))
    assert metadata.expires_at == now + METADATA_TTL
    statement = asyncio.run(cache.get_financial("TSM", "income_statement:quarter", now=now))
    assert statement.expires_at == now + EARNINGS_WINDOW_STATEMENT_TTL


def test_concurrent_requests_share_one_fmp_refresh():
    now = datetime(2026, 7, 12, 8, tzinfo=UTC)
    cache = MemoryFinancialCache()

    class FakeProvider(FMPFinancialsProvider):
        calls = 0

        async def _get_json(self, client, url, params):
            self.calls += 1
            await asyncio.sleep(0)
            if url.endswith("/sec-profile"):
                return [{}]
            if url.endswith("/earnings"):
                return [{"date": "2026-10-20"}]
            return [{"date": "2026-03-31", "period": "Q1", "reportedCurrency": "USD"}]

    provider = FakeProvider(api_key="test", cache=cache, now=lambda: now)

    async def fetch_twice():
        return await asyncio.gather(provider.fetch_financials("AAPL"), provider.fetch_financials("AAPL"))

    first, second = asyncio.run(fetch_twice())
    assert provider.calls == 9
    assert first["statements"] == second["statements"]


def test_requests_in_different_event_loops_share_one_fmp_refresh():
    now = datetime(2026, 7, 12, 8, tzinfo=UTC)
    cache = MemoryFinancialCache()

    class FakeProvider(FMPFinancialsProvider):
        calls = 0

        async def _get_json(self, client, url, params):
            self.calls += 1
            await asyncio.sleep(0.01)
            if url.endswith("/sec-profile"):
                return [{}]
            if url.endswith("/earnings"):
                return []
            return [{"date": "2026-03-31", "period": "Q1", "reportedCurrency": "USD"}]

    provider = FakeProvider(api_key="test", cache=cache, now=lambda: now)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: asyncio.run(provider.fetch_financials("AAPL")), range(2)))

    assert provider.calls == 9
    assert results[0]["statements"] == results[1]["statements"]


def test_fmp_analyst_estimates_keeps_only_ordered_complete_rows():
    now = datetime(2026, 7, 12, 8, tzinfo=UTC)

    class FakeProvider(FMPFinancialsProvider):
        async def _get_json(self, client, url, params):
            if url.endswith("/analyst-estimates"):
                return [
                    {
                        "symbol": "TSLA", "date": "2027-12-31",
                        "revenueLow": 100, "revenueAvg": 110, "revenueHigh": 120,
                        "ebitLow": 10, "ebitAvg": 12, "ebitHigh": 14,
                        "numAnalystsRevenue": 7,
                    },
                    {
                        "symbol": "TSLA", "date": "2028-12-31",
                        "revenueLow": 130, "revenueAvg": 120, "revenueHigh": 140,
                        "ebitLow": 13, "ebitAvg": 14, "ebitHigh": 15,
                    },
                ]
            if url.endswith("/sec-profile"):
                return [{}]
            if url.endswith("/earnings"):
                return []
            return []

    result = asyncio.run(FakeProvider(
        api_key="test", cache=MemoryFinancialCache(), now=lambda: now
    ).fetch_financials("TSLA"))
    assert [row["date"] for row in result["analyst_estimates"]] == ["2027-12-31"]
    assert result["analyst_estimates"][0]["status"] == "provider_estimate"
    assert result["analyst_estimates"][0]["numAnalystsRevenue"] == 7


def test_fmp_cache_failure_returns_provider_data_with_warning():
    now = datetime(2026, 7, 12, 8, tzinfo=UTC)

    class BrokenCache:
        async def get_financial(self, ticker, data_type, *, now=None):
            raise RuntimeError("cache offline")

        async def upsert_financial(self, *args, **kwargs):
            raise RuntimeError("cache offline")

    class FakeProvider(FMPFinancialsProvider):
        async def _get_json(self, client, url, params):
            if url.endswith("/sec-profile"):
                return [{}]
            if url.endswith("/earnings"):
                return []
            return [{"date": "2026-03-31", "period": "Q1", "reportedCurrency": "USD"}]

    provider = FakeProvider(api_key="test", cache=BrokenCache(), now=lambda: now)
    result = asyncio.run(provider.fetch_financials("AAPL"))

    assert result["statements"]["income_statement"]["annual"]
    assert "SUPABASE_CACHE_READ_UNAVAILABLE" not in result["warnings"]
    assert "SUPABASE_CACHE_WRITE_UNAVAILABLE" not in result["warnings"]


def test_fmp_mapper_exposes_valuation_inputs_without_turning_zero_into_missing():
    report = {
        "date": "2026-03-31",
        "calendarYear": "2026",
        "period": "Q1",
        "reportedCurrency": "USD",
        "revenue": 100,
        "operatingIncome": 20,
        "incomeTaxExpense": 0,
        "researchAndDevelopmentExpenses": 7,
        "weightedAverageShsOutDil": 11,
        "totalDebt": 30,
        "commonStockSharesOutstanding": 12,
        "netCashProvidedByOperatingActivities": 25,
        "capitalExpenditure": -5,
        "freeCashFlow": 20,
        "dividendsPaid": -9,
    }
    income_rows, periods = _map_fmp_to_sec_rows([report], "income", [], is_annual=False)
    income = {row["id"]: row["cells"] for row in income_rows}
    key = periods[0]["key"]
    assert income["total_revenue"][key]["value"] == 100
    assert income["operating_income"][key]["value"] == 20
    assert income["tax_provision"][key]["value"] == 0
    assert income["research_development"][key]["value"] == 7
    assert income["shares_outstanding"][key]["value"] == 11
    assert income["shares_outstanding"][key]["unit"] == "shares"
    assert income["diluted_average_shares"][key]["value"] == 11

    balance_rows, _ = _map_fmp_to_sec_rows([report], "balance_sheet", [], is_annual=False)
    balance = {row["id"]: row["cells"] for row in balance_rows}
    assert balance["total_debt"][key]["value"] == 30
    assert balance["shares_outstanding"][key]["value"] == 12

    cash_rows, _ = _map_fmp_to_sec_rows([report], "cash_flow", [], is_annual=False)
    cash = {row["id"]: row["cells"] for row in cash_rows}
    assert cash["operating_cash_flow"][key]["value"] == 25
    assert cash["capital_expenditure"][key]["value"] == -5
    assert cash["free_cash_flow"][key]["value"] == 20
    assert cash["dividends_paid"][key]["value"] == 9


def test_income_share_mapper_falls_back_to_basic_weighted_shares():
    report = {
        "date": "2026-03-31",
        "period": "Q1",
        "reportedCurrency": "USD",
        "weightedAverageShsOut": 25_900_000_000,
    }
    rows, periods = _map_fmp_to_sec_rows([report], "income", [], is_annual=False)
    by_id = {row["id"]: row["cells"] for row in rows}
    key = periods[0]["key"]
    assert by_id["shares_outstanding"][key]["value"] == 25_900_000_000
    assert by_id["diluted_average_shares"][key]["value"] == 25_900_000_000


def test_static_adr_fallback_is_exact_and_api_ratio_wins():
    assert STATIC_ADR_MAP == {
        "TSM": 5.0, "BABA": 8.0, "ASML": 1.0, "BIDU": 8.0,
        "JD": 2.0, "PDD": 4.0, "NVO": 1.0, "SONY": 1.0,
    }
    tsm = _apply_adr_fallback("tsm", {"is_adr": False, "adr_ratio": None})
    assert tsm == {"is_adr": True, "adr_ratio": 5.0, "adr_ratio_source": "static_adr_map"}
    unknown = _apply_adr_fallback("AAPL", {"is_adr": False, "adr_ratio": None})
    assert unknown["adr_ratio"] == 1.0
    sourced = _apply_adr_fallback(
        "TSM",
        {"is_adr": True, "adr_ratio": 10.0, "adr_ratio_source": "fmp_sec_profile"},
    )
    assert sourced["adr_ratio"] == 10.0


def test_legacy_cached_adr_ratio_is_repaired_and_persisted():
    now = datetime(2026, 7, 12, tzinfo=UTC)
    cache = MemoryFinancialCache()
    asyncio.run(cache.upsert_financial(
        "TSM",
        "company_metadata",
        {"is_adr": True, "adr_ratio": 1.0, "next_earnings_date": "2026-07-16"},
        fetched_at=now,
        expires_at=now + timedelta(days=30),
    ))
    provider = FMPFinancialsProvider(api_key="test", cache=cache, now=lambda: now)

    class NoNetwork:
        pass

    repaired = asyncio.run(provider._fetch_metadata(NoNetwork(), "TSM"))
    assert repaired["adr_ratio"] == 5.0
    persisted = asyncio.run(cache.get_financial("TSM", "company_metadata", now=now))
    assert persisted.payload["adr_ratio"] == 5.0


def test_format_response_applies_adr_ratio_exactly_once(monkeypatch):
    monkeypatch.setattr("app.api.routes.valuation.get_valuation_telemetry", lambda ticker: {})
    already_scaled = format_response(
        "TSM", 100.0, "CALCULATED",
        {"adr_ratio": 5.0, "adr_ratio_applied": True},
        current_price=100.0,
    )
    assert already_scaled["computed_fair_value"] == 100.0

    raw = format_response(
        "TSM", 20.0, "CALCULATED",
        {"adr_ratio": 5.0, "adr_ratio_applied": False},
        current_price=100.0,
    )
    # The adr_ratio is NOT applied as a multiplier because shares_outstanding already
    # represents the listed ADR count. Thus, the raw computed fair value is inherently per-ADR.
    assert raw["computed_fair_value"] == 20.0
    assert raw["underlying_assumptions"]["adr_ratio"] == 5.0
