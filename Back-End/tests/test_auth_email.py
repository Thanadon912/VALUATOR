from __future__ import annotations

import asyncio
from dataclasses import replace
import logging

import httpx
from fastapi.testclient import TestClient
import pytest

from app.api.routes import auth_email as auth_email_routes
from app.core.config import get_settings
from app.main import app
from app.services import auth_email


INTERNAL_TOKEN = "test-internal-email-token-that-is-long-enough"


def email_settings(**changes):
    base = replace(
        get_settings(),
        email_delivery_mode="resend_test",
        email_internal_api_token=INTERNAL_TOKEN,
        resend_api_key="re_test_key_not_real",
        resend_from_email="VALUATOR <onboarding@resend.dev>",
        resend_test_recipient="owner@example.com",
        resend_reply_to=None,
        resend_timeout_seconds=1.0,
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_username="valuator@example.com",
        smtp_password="app-password-not-real",
        smtp_from_email="valuator@example.com",
        smtp_from_name="VALUATOR",
        smtp_reply_to=None,
        smtp_timeout_seconds=1.0,
        app_base_url="http://frontend.test",
        supabase_url="http://supabase.test",
        supabase_secret_key="test-secret-key",
    )
    return replace(base, **changes)


def test_email_templates_are_contextual_and_escape_links() -> None:
    confirmation = auth_email.confirmation_message(
        'https://app.example/auth/confirm?token_hash=a&next="unsafe"'
    )
    recovery = auth_email.recovery_message("https://app.example/reset")
    welcome = auth_email.welcome_message("https://app.example/")

    assert confirmation.subject == "Confirm your VALUATOR email"
    assert "Confirm email" in confirmation.html
    assert '&amp;next=&quot;unsafe&quot;' in confirmation.html
    assert 'href="https://app.example/auth/confirm?token_hash=a&next=' not in confirmation.html
    assert "ignore this message" in confirmation.text.lower()
    assert recovery.subject == "Reset your VALUATOR password"
    assert "password will stay unchanged" in recovery.text
    assert welcome.subject == "Welcome to VALUATOR"
    assert "five valuation engines" in welcome.text
    assert "<img" not in confirmation.html.lower()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"email_delivery_mode": "disabled"}, "disabled"),
        ({"email_internal_api_token": "short"}, "32 characters"),
        ({"resend_api_key": None}, "RESEND_API_KEY"),
        ({"resend_test_recipient": None}, "RESEND_TEST_RECIPIENT"),
        (
            {
                "email_delivery_mode": "resend",
                "app_base_url": "https://app.example",
            },
            "verified sender domain",
        ),
        (
            {
                "email_delivery_mode": "resend",
                "resend_from_email": "VALUATOR <mail@example.com>",
                "app_base_url": "http://app.example",
            },
            "HTTPS",
        ),
    ],
)
def test_email_configuration_fails_closed(changes, message) -> None:
    with pytest.raises(auth_email.EmailConfigurationError, match=message):
        auth_email.validate_email_configuration(email_settings(**changes))


def test_resend_request_uses_server_key_plain_text_and_idempotency(monkeypatch) -> None:
    requests: list[dict] = []

    class FakeClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, headers, json):
            requests.append({"url": url, "headers": headers, "json": json})
            return httpx.Response(200, json={"id": "email_123"})

    monkeypatch.setattr(auth_email.httpx, "AsyncClient", FakeClient)
    message_id = asyncio.run(
        auth_email.send_resend_email(
            email_settings(),
            recipient="OWNER@EXAMPLE.COM",
            kind="welcome",
            message=auth_email.welcome_message("http://frontend.test"),
            idempotency_key="welcome-stable-key",
        )
    )

    assert message_id == "email_123"
    assert requests == [
        {
            "url": auth_email.RESEND_EMAILS_URL,
            "headers": {
                "Authorization": "Bearer re_test_key_not_real",
                "Idempotency-Key": "welcome-stable-key",
            },
            "json": {
                "from": "VALUATOR <onboarding@resend.dev>",
                "to": ["owner@example.com"],
                "subject": "Welcome to VALUATOR",
                "html": requests[0]["json"]["html"],
                "text": requests[0]["json"]["text"],
                "tags": [
                    {"name": "category", "value": "authentication"},
                    {"name": "template", "value": "welcome"},
                ],
            },
        }
    ]


def test_gmail_smtp_uses_starttls_login_and_multipart_message(monkeypatch) -> None:
    calls: list[tuple] = []

    class FakeSMTP:
        def __init__(self, host, port, *, timeout):
            calls.append(("connect", host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def ehlo(self):
            calls.append(("ehlo",))

        def starttls(self, *, context):
            assert context is not None
            calls.append(("starttls",))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message, *, from_addr, to_addrs):
            calls.append(("send", from_addr, to_addrs, message))

    monkeypatch.setattr(auth_email.smtplib, "SMTP", FakeSMTP)
    settings = email_settings(
        email_delivery_mode="smtp",
        app_base_url="https://frontend.test",
    )
    message_id = asyncio.run(
        auth_email.send_smtp_email(
            settings,
            recipient="OWNER@EXAMPLE.COM",
            kind="welcome",
            message=auth_email.welcome_message("http://frontend.test"),
            idempotency_key="welcome-stable-key",
        )
    )

    assert calls[:4] == [
        ("connect", "smtp.gmail.com", 587, 1.0),
        ("ehlo",),
        ("starttls",),
        ("ehlo",),
    ]
    assert calls[4] == ("login", "valuator@example.com", "app-password-not-real")
    sent = calls[5]
    assert sent[:3] == ("send", "valuator@example.com", ["owner@example.com"])
    mime = sent[3]
    assert mime["From"] == "VALUATOR <valuator@example.com>"
    assert mime["To"] == "owner@example.com"
    assert mime["Message-ID"] == message_id
    assert mime.is_multipart()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"smtp_username": "not-an-email"}, "full email address"),
        ({"smtp_from_email": "other@example.com"}, "must match"),
        ({"smtp_port": 25}, "465 or 587"),
        ({"smtp_from_name": "Bad\nBcc: victim@example.com"}, "EMAIL_FROM_NAME"),
    ],
)
def test_smtp_configuration_fails_closed(changes, message) -> None:
    settings = email_settings(
        email_delivery_mode="smtp",
        app_base_url="https://frontend.test",
        **changes,
    )
    with pytest.raises(auth_email.EmailConfigurationError, match=message):
        auth_email.validate_email_configuration(settings)


def test_internal_routes_require_token_restrict_test_recipient_and_rate_limit(
    monkeypatch,
) -> None:
    settings = email_settings()
    delivered: list[dict] = []

    async def fake_signup(_settings, **kwargs):
        delivered.append(kwargs)

    async def allow_durable_limit(_settings, **_kwargs):
        return True, 900

    monkeypatch.setattr(auth_email_routes, "deliver_signup_email", fake_signup)
    monkeypatch.setattr(
        auth_email_routes,
        "consume_recipient_rate_limit",
        allow_durable_limit,
    )
    monkeypatch.setattr(auth_email_routes, "get_settings", lambda: settings)
    client = TestClient(app)
    payload = {
        "email": "owner@example.com",
        "password": "password123",
        "next_path": "/account",
    }
    try:
        unauthorized = client.post("/api/internal/auth/email/signup", json=payload)
        restricted = client.post(
            "/api/internal/auth/email/signup",
            headers={"Authorization": f"Bearer {INTERNAL_TOKEN}"},
            json={**payload, "email": "someone@example.com"},
        )
        accepted = [
            client.post(
                "/api/internal/auth/email/signup",
                headers={"Authorization": f"Bearer {INTERNAL_TOKEN}"},
                json=payload,
            )
            for _ in range(4)
        ]
    finally:
        app.dependency_overrides.clear()

    assert unauthorized.status_code == 401
    assert restricted.status_code == 403
    assert restricted.json()["detail"]["code"] == "email_test_recipient_only"
    assert [response.status_code for response in accepted] == [202, 202, 202, 429]
    assert len(delivered) == 3
    assert all(call["email"] == "owner@example.com" for call in delivered)
    assert all(call["password"] == "password123" for call in delivered)


def test_internal_email_route_fails_closed_when_durable_limit_is_unavailable(
    monkeypatch,
) -> None:
    settings = email_settings()

    async def unavailable(_settings, **_kwargs):
        raise auth_email.EmailConfigurationError("database unavailable")

    monkeypatch.setattr(auth_email_routes, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_email_routes, "consume_recipient_rate_limit", unavailable)
    client = TestClient(app)
    try:
        response = client.post(
            "/api/internal/auth/email/recovery",
            headers={"Authorization": f"Bearer {INTERNAL_TOKEN}"},
            json={"email": "owner@example.com", "next_path": "/account"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "email_rate_limit_unavailable"


def test_recipient_rate_limit_digest_is_normalized_keyed_and_not_plaintext() -> None:
    first = auth_email.recipient_rate_limit_digest(" OWNER@example.com ", "secret-a")
    normalized = auth_email.recipient_rate_limit_digest("owner@example.com", "secret-a")
    other_key = auth_email.recipient_rate_limit_digest("owner@example.com", "secret-b")

    assert first == normalized
    assert first != other_key
    assert len(first) == 64
    assert "owner" not in first


def test_internal_route_rejects_external_redirect_and_invalid_uuid(monkeypatch) -> None:
    settings = email_settings()
    monkeypatch.setattr(auth_email_routes, "get_settings", lambda: settings)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {INTERNAL_TOKEN}"}
    try:
        redirect = client.post(
            "/api/internal/auth/email/recovery",
            headers=headers,
            json={"email": "owner@example.com", "next_path": "https://evil.example"},
        )
        welcome = client.post(
            "/api/internal/auth/email/welcome",
            headers=headers,
            json={"user_id": "not-a-uuid"},
        )
    finally:
        app.dependency_overrides.clear()

    assert redirect.status_code == 422
    assert welcome.status_code == 422


def test_background_job_logs_no_email_or_secret(caplog) -> None:
    async def fail(_settings, **_kwargs):
        raise RuntimeError("provider failure")

    settings = email_settings()
    with caplog.at_level(logging.ERROR):
        asyncio.run(
            auth_email.run_email_job(
                fail,
                settings,
                event_type="password_recovery",
                email="owner@example.com",
            )
        )

    output = caplog.text
    assert "auth_email_delivery_failed" in output
    assert "owner@example.com" not in output
    assert settings.resend_api_key not in output
    assert INTERNAL_TOKEN not in output
