from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from postgrest.exceptions import APIError
from supabase import acreate_client

from app.repositories.supabase_cache import SupabaseCacheRepository


pytestmark = pytest.mark.supabase_integration


from tests.allure_helpers import valuator_test


async def _close_clients(*clients):
    for client in clients:
        postgrest = getattr(client, "_postgrest", None)
        if postgrest is not None:
            await postgrest.aclose()


@valuator_test(
    epic="Authentication",
    feature="Supabase Integration",
    story="Public Role Access Denial",
    priority="P0",
    severity="blocker",
    layer="backend-integration",
    test_id="VAL-BE-INT-AUTH-001"
)
def test_secret_cache_access_and_public_role_denial():
    if os.getenv("SUPABASE_INTEGRATION_TEST", "").lower() != "true":
        pytest.skip("Set SUPABASE_INTEGRATION_TEST=true for local Supabase checks")

    url = os.environ["SUPABASE_URL"]
    secret_key = os.environ["SUPABASE_SECRET_KEY"]
    publishable_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]

    async def scenario():
        secret_client = await acreate_client(url, secret_key)
        public_client = await acreate_client(url, publishable_key)
        repository = SupabaseCacheRepository(secret_client)
        now = datetime.now(timezone.utc)
        try:
            await repository.upsert_financial(
                "TSTCACHE",
                "integration",
                {"source": "integration-test"},
                fetched_at=now,
                expires_at=now + timedelta(minutes=5),
            )
            cached = await repository.get_financial(
                "TSTCACHE",
                "integration",
                now=now,
            )
            assert cached is not None
            assert cached.payload == {"source": "integration-test"}

            for table in ("provider_cache_entries", "news_cache_articles"):
                with pytest.raises(APIError):
                    await public_client.table(table).select("*").limit(1).execute()
        finally:
            await secret_client.table("provider_cache_entries").delete().eq(
                "ticker",
                "TSTCACHE",
            ).execute()
            await _close_clients(secret_client, public_client)

    asyncio.run(scenario())


@valuator_test(
    epic="Authentication",
    feature="Supabase Integration",
    story="Saved Stocks Row Level Security",
    priority="P0",
    severity="blocker",
    layer="backend-integration",
    test_id="VAL-BE-INT-AUTH-002",
)
def test_saved_stocks_rls_and_atomic_guest_merge():
    if os.getenv("SUPABASE_INTEGRATION_TEST", "").lower() != "true":
        pytest.skip("Set SUPABASE_INTEGRATION_TEST=true for local Supabase checks")

    url = os.environ["SUPABASE_URL"]
    secret_key = os.environ["SUPABASE_SECRET_KEY"]
    publishable_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]

    async def scenario():
        secret_client = await acreate_client(url, secret_key)
        anon_client = await acreate_client(url, publishable_key)
        user_a_client = await acreate_client(url, publishable_key)
        user_b_client = await acreate_client(url, publishable_key)
        created_user_ids: list[str] = []
        suffix = uuid4().hex
        user_a_credentials = {
            "email": f"saved-a-{suffix}@example.com",
            "password": "integration-password-a",
        }
        user_b_credentials = {
            "email": f"saved-b-{suffix}@example.com",
            "password": "integration-password-b",
        }

        try:
            user_a_response = await secret_client.auth.admin.create_user(
                {**user_a_credentials, "email_confirm": True}
            )
            user_b_response = await secret_client.auth.admin.create_user(
                {**user_b_credentials, "email_confirm": True}
            )
            assert user_a_response.user is not None
            assert user_b_response.user is not None
            user_a_id = str(user_a_response.user.id)
            user_b_id = str(user_b_response.user.id)
            created_user_ids.extend((user_a_id, user_b_id))

            await user_a_client.auth.sign_in_with_password(user_a_credentials)
            await user_b_client.auth.sign_in_with_password(user_b_credentials)

            with pytest.raises(APIError):
                await anon_client.table("saved_stocks").select("*").execute()
            with pytest.raises(APIError):
                await anon_client.rpc("merge_saved_stocks", {"p_items": []}).execute()

            await user_a_client.table("saved_stocks").insert(
                {
                    "user_id": user_a_id,
                    "ticker": "AAPL",
                    "added_at": "2025-01-05T00:00:00Z",
                    "last_visited_at": "2025-01-06T00:00:00Z",
                    "last_section": "summary",
                }
            ).execute()
            await user_b_client.table("saved_stocks").insert(
                {
                    "user_id": user_b_id,
                    "ticker": "TSLA",
                    "added_at": "2025-01-02T00:00:00Z",
                    "last_visited_at": "2025-01-03T00:00:00Z",
                    "last_section": "news",
                }
            ).execute()

            with pytest.raises(APIError):
                await user_a_client.table("saved_stocks").insert(
                    {"user_id": user_b_id, "ticker": "NVDA"}
                ).execute()

            merge_response = await user_a_client.rpc(
                "merge_saved_stocks",
                {
                    "p_items": [
                        {
                            "ticker": "aapl",
                            "added_at": "2025-01-01T00:00:00Z",
                            "last_visited_at": "2025-01-07T00:00:00Z",
                            "last_section": "valuation",
                            "user_id": user_b_id,
                        },
                        {
                            "ticker": "MSFT",
                            "added_at": "2025-01-04T00:00:00Z",
                            "last_visited_at": "2025-01-04T12:00:00Z",
                            "last_section": "summary",
                        },
                        {
                            "ticker": "MSFT",
                            "added_at": "2025-01-03T00:00:00Z",
                            "last_visited_at": "2025-01-08T00:00:00Z",
                            "last_section": "news",
                        },
                    ]
                },
            ).execute()
            merged = {row["ticker"]: row for row in merge_response.data}
            assert set(merged) == {"AAPL", "MSFT"}
            assert merged["AAPL"]["user_id"] == user_a_id
            assert merged["AAPL"]["added_at"] == "2025-01-01T00:00:00+00:00"
            assert merged["AAPL"]["last_visited_at"] == "2025-01-07T00:00:00+00:00"
            assert merged["AAPL"]["last_section"] == "valuation"
            assert merged["MSFT"]["added_at"] == "2025-01-03T00:00:00+00:00"
            assert merged["MSFT"]["last_visited_at"] == "2025-01-08T00:00:00+00:00"
            assert merged["MSFT"]["last_section"] == "news"

            user_a_rows = await user_a_client.table("saved_stocks").select(
                "user_id,ticker"
            ).execute()
            assert {row["ticker"] for row in user_a_rows.data} == {"AAPL", "MSFT"}
            assert {row["user_id"] for row in user_a_rows.data} == {user_a_id}

            user_b_rows = await user_b_client.table("saved_stocks").select(
                "user_id,ticker"
            ).execute()
            assert user_b_rows.data == [{"user_id": user_b_id, "ticker": "TSLA"}]

            cross_update = await user_a_client.table("saved_stocks").update(
                {"last_section": "valuation"}
            ).eq("user_id", user_b_id).execute()
            assert cross_update.data == []
            cross_delete = await user_a_client.table("saved_stocks").delete().eq(
                "user_id", user_b_id
            ).execute()
            assert cross_delete.data == []

            with pytest.raises(APIError):
                await user_a_client.table("saved_stocks").insert(
                    {"user_id": user_a_id, "ticker": "INVALID/TICKER"}
                ).execute()
            with pytest.raises(APIError):
                await user_a_client.table("saved_stocks").insert(
                    {
                        "user_id": user_a_id,
                        "ticker": "NFLX",
                        "last_section": "financials",
                    }
                ).execute()

            with pytest.raises(APIError):
                await user_a_client.rpc(
                    "merge_saved_stocks",
                    {
                        "p_items": [
                            {
                                "ticker": "GOOG",
                                "added_at": "2025-01-01T00:00:00Z",
                                "last_visited_at": "2025-01-02T00:00:00Z",
                                "last_section": "summary",
                            },
                            {
                                "ticker": "META",
                                "added_at": "2025-01-01T00:00:00Z",
                                "last_visited_at": "2025-01-02T00:00:00Z",
                                "last_section": "financials",
                            },
                        ]
                    },
                ).execute()
            atomic_check = await user_a_client.table("saved_stocks").select(
                "ticker"
            ).eq("ticker", "GOOG").execute()
            assert atomic_check.data == []

            with pytest.raises(APIError):
                await user_a_client.rpc(
                    "merge_saved_stocks",
                    {
                        "p_items": [
                            {
                                "ticker": "AAPL",
                                "added_at": "2025-01-01T00:00:00Z",
                                "last_visited_at": "2025-01-02T00:00:00Z",
                                "last_section": "summary",
                            }
                            for _ in range(101)
                        ]
                    },
                ).execute()

            for client in (user_a_client, user_b_client):
                for table in ("provider_cache_entries", "news_cache_articles"):
                    with pytest.raises(APIError):
                        await client.table(table).select("*").limit(1).execute()
        finally:
            for user_id in created_user_ids:
                await secret_client.auth.admin.delete_user(user_id)
            await _close_clients(
                secret_client,
                anon_client,
                user_a_client,
                user_b_client,
            )

    asyncio.run(scenario())


@valuator_test(
    epic="Authentication",
    feature="Supabase Integration",
    story="Valuation Assumptions Row Level Security",
    priority="P0",
    severity="blocker",
    layer="backend-integration",
    test_id="VAL-BE-INT-AUTH-003",
)
def test_valuation_assumptions_rls_validation_and_latest_merge():
    if os.getenv("SUPABASE_INTEGRATION_TEST", "").lower() != "true":
        pytest.skip("Set SUPABASE_INTEGRATION_TEST=true for local Supabase checks")

    url = os.environ["SUPABASE_URL"]
    secret_key = os.environ["SUPABASE_SECRET_KEY"]
    publishable_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]

    async def scenario():
        secret_client = await acreate_client(url, secret_key)
        anon_client = await acreate_client(url, publishable_key)
        user_a_client = await acreate_client(url, publishable_key)
        user_b_client = await acreate_client(url, publishable_key)
        created_user_ids: list[str] = []
        suffix = uuid4().hex
        credentials_a = {
            "email": f"assumptions-a-{suffix}@example.com",
            "password": "integration-password-a",
        }
        credentials_b = {
            "email": f"assumptions-b-{suffix}@example.com",
            "password": "integration-password-b",
        }

        try:
            response_a = await secret_client.auth.admin.create_user(
                {**credentials_a, "email_confirm": True}
            )
            response_b = await secret_client.auth.admin.create_user(
                {**credentials_b, "email_confirm": True}
            )
            assert response_a.user is not None
            assert response_b.user is not None
            user_a_id = str(response_a.user.id)
            user_b_id = str(response_b.user.id)
            created_user_ids.extend((user_a_id, user_b_id))
            await user_a_client.auth.sign_in_with_password(credentials_a)
            await user_b_client.auth.sign_in_with_password(credentials_b)

            with pytest.raises(APIError):
                await anon_client.table("valuation_assumptions").select("*").execute()
            with pytest.raises(APIError):
                await anon_client.rpc(
                    "merge_valuation_assumptions", {"p_items": []}
                ).execute()

            await user_b_client.table("valuation_assumptions").insert(
                {
                    "user_id": user_b_id,
                    "ticker": "TSLA",
                    "stage_1_growth_rate": 0.10,
                    "perpetual_growth_rate": 0.02,
                    "discount_rate": 0.09,
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            ).execute()
            with pytest.raises(APIError):
                await user_a_client.table("valuation_assumptions").insert(
                    {
                        "user_id": user_b_id,
                        "ticker": "MSFT",
                        "stage_1_growth_rate": 0.10,
                        "perpetual_growth_rate": 0.02,
                        "discount_rate": 0.09,
                    }
                ).execute()

            await user_a_client.rpc(
                "merge_valuation_assumptions",
                {
                    "p_items": [
                        {
                            "ticker": "aapl",
                            "stage_1_growth_rate": 0.08,
                            "perpetual_growth_rate": 0.02,
                            "discount_rate": 0.10,
                            "updated_at": "2026-01-01T00:00:00Z",
                            "user_id": user_b_id,
                        },
                        {
                            "ticker": "AAPL",
                            "stage_1_growth_rate": 0.125,
                            "perpetual_growth_rate": 0.025,
                            "discount_rate": 0.085,
                            "updated_at": "2026-01-02T00:00:00Z",
                        },
                    ]
                },
            ).execute()
            rows_a = await user_a_client.table("valuation_assumptions").select(
                "user_id,ticker,stage_1_growth_rate,perpetual_growth_rate,discount_rate"
            ).execute()
            assert rows_a.data == [
                {
                    "user_id": user_a_id,
                    "ticker": "AAPL",
                    "stage_1_growth_rate": 0.125,
                    "perpetual_growth_rate": 0.025,
                    "discount_rate": 0.085,
                }
            ]

            rows_b = await user_b_client.table("valuation_assumptions").select(
                "user_id,ticker"
            ).execute()
            assert rows_b.data == [{"user_id": user_b_id, "ticker": "TSLA"}]

            with pytest.raises(APIError):
                await user_a_client.rpc(
                    "merge_valuation_assumptions",
                    {
                        "p_items": [
                            {
                                "ticker": "MSFT",
                                "stage_1_growth_rate": 0.10,
                                "perpetual_growth_rate": 0.02,
                                "discount_rate": 0.09,
                                "updated_at": "2026-01-03T00:00:00Z",
                            },
                            {
                                "ticker": "NVDA",
                                "stage_1_growth_rate": -0.05,
                                "perpetual_growth_rate": 0.02,
                                "discount_rate": 0.09,
                                "updated_at": "2026-01-03T00:00:00Z",
                            },
                        ]
                    },
                ).execute()
            atomic_check = await user_a_client.table("valuation_assumptions").select(
                "ticker"
            ).eq("ticker", "MSFT").execute()
            assert atomic_check.data == []

            with pytest.raises(APIError):
                await user_a_client.rpc(
                    "merge_valuation_assumptions",
                    {
                        "p_items": [
                            {
                                "ticker": "AAPL",
                                "stage_1_growth_rate": 0.10,
                                "perpetual_growth_rate": 0.02,
                                "discount_rate": 0.09,
                                "updated_at": "2026-01-03T00:00:00Z",
                            }
                            for _ in range(101)
                        ]
                    },
                ).execute()

            cross_delete = await user_a_client.table("valuation_assumptions").delete().eq(
                "user_id", user_b_id
            ).execute()
            assert cross_delete.data == []
        finally:
            for user_id in created_user_ids:
                await secret_client.auth.admin.delete_user(user_id)
            await _close_clients(
                secret_client,
                anon_client,
                user_a_client,
                user_b_client,
            )

    asyncio.run(scenario())


@valuator_test(
    epic="Authentication",
    feature="Transactional Email",
    story="Welcome Email Delivery Ledger",
    priority="P0",
    severity="blocker",
    layer="backend-integration",
    test_id="VAL-BE-INT-AUTH-004",
)
def test_auth_email_delivery_ledger_is_service_only_and_idempotent():
    if os.getenv("SUPABASE_INTEGRATION_TEST", "").lower() != "true":
        pytest.skip("Set SUPABASE_INTEGRATION_TEST=true for local Supabase checks")

    url = os.environ["SUPABASE_URL"]
    secret_key = os.environ["SUPABASE_SECRET_KEY"]
    publishable_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]

    async def scenario():
        secret_client = await acreate_client(url, secret_key)
        anon_client = await acreate_client(url, publishable_key)
        user_client = await acreate_client(url, publishable_key)
        suffix = uuid4().hex
        credentials = {
            "email": f"email-ledger-{suffix}@example.com",
            "password": "integration-password-email-ledger",
        }
        user_id: str | None = None
        try:
            response = await secret_client.auth.admin.create_user(
                {**credentials, "email_confirm": True}
            )
            assert response.user is not None
            user_id = str(response.user.id)
            await user_client.auth.sign_in_with_password(credentials)

            with pytest.raises(APIError):
                await anon_client.table("auth_email_deliveries").select("*").execute()
            with pytest.raises(APIError):
                await user_client.table("auth_email_deliveries").select("*").execute()
            with pytest.raises(APIError):
                await anon_client.rpc(
                    "claim_auth_email_delivery",
                    {"p_user_id": user_id, "p_event_type": "welcome"},
                ).execute()
            with pytest.raises(APIError):
                await user_client.rpc(
                    "claim_auth_email_delivery",
                    {"p_user_id": user_id, "p_event_type": "welcome"},
                ).execute()

            first = await secret_client.rpc(
                "claim_auth_email_delivery",
                {"p_user_id": user_id, "p_event_type": "welcome"},
            ).execute()
            duplicate = await secret_client.rpc(
                "claim_auth_email_delivery",
                {"p_user_id": user_id, "p_event_type": "welcome"},
            ).execute()
            assert first.data is True
            assert duplicate.data is False

            await secret_client.table("auth_email_deliveries").update(
                {"status": "failed"}
            ).eq("user_id", user_id).eq("event_type", "welcome").execute()
            retry = await secret_client.rpc(
                "claim_auth_email_delivery",
                {"p_user_id": user_id, "p_event_type": "welcome"},
            ).execute()
            assert retry.data is True

            await secret_client.table("auth_email_deliveries").update(
                {"status": "sent", "provider_message_id": "email_test_123"}
            ).eq("user_id", user_id).eq("event_type", "welcome").execute()
            sent_duplicate = await secret_client.rpc(
                "claim_auth_email_delivery",
                {"p_user_id": user_id, "p_event_type": "welcome"},
            ).execute()
            assert sent_duplicate.data is False

            rows = await secret_client.table("auth_email_deliveries").select(
                "user_id,event_type,status,attempt_count,provider_message_id"
            ).eq("user_id", user_id).execute()
            assert rows.data == [
                {
                    "user_id": user_id,
                    "event_type": "welcome",
                    "status": "sent",
                    "attempt_count": 2,
                    "provider_message_id": "email_test_123",
                }
            ]
        finally:
            if user_id is not None:
                await secret_client.auth.admin.delete_user(user_id)
            await _close_clients(secret_client, anon_client, user_client)

    asyncio.run(scenario())


@valuator_test(
    epic="Authentication",
    feature="Transactional Email",
    story="Durable Recipient Rate Limit",
    priority="P0",
    severity="blocker",
    layer="backend-integration",
    test_id="VAL-BE-INT-AUTH-005",
)
def test_auth_email_rate_limit_is_service_only_and_atomic():
    if os.getenv("SUPABASE_INTEGRATION_TEST", "").lower() != "true":
        pytest.skip("Set SUPABASE_INTEGRATION_TEST=true for local Supabase checks")

    url = os.environ["SUPABASE_URL"]
    secret_key = os.environ["SUPABASE_SECRET_KEY"]
    publishable_key = os.environ["SUPABASE_PUBLISHABLE_KEY"]

    async def scenario():
        secret_client = await acreate_client(url, secret_key)
        anon_client = await acreate_client(url, publishable_key)
        digest = uuid4().hex + uuid4().hex
        params = {
            "p_recipient_digest": digest,
            "p_event_type": "recovery",
            "p_limit": 3,
            "p_window_seconds": 900,
        }
        try:
            with pytest.raises(APIError):
                await anon_client.table("auth_email_rate_limits").select("*").execute()
            with pytest.raises(APIError):
                await anon_client.rpc("consume_auth_email_rate_limit", params).execute()

            results = await asyncio.gather(
                *[
                    secret_client.rpc(
                        "consume_auth_email_rate_limit",
                        params,
                    ).execute()
                    for _ in range(4)
                ]
            )
            allowed = sorted(row.data[0]["allowed"] for row in results)
            assert allowed == [False, True, True, True]

            rows = await secret_client.table("auth_email_rate_limits").select(
                "recipient_digest,event_type,request_count"
            ).eq("recipient_digest", digest).execute()
            assert rows.data == [
                {
                    "recipient_digest": digest,
                    "event_type": "recovery",
                    "request_count": 3,
                }
            ]
        finally:
            await secret_client.table("auth_email_rate_limits").delete().eq(
                "recipient_digest", digest
            ).execute()
            await _close_clients(secret_client, anon_client)

    asyncio.run(scenario())
