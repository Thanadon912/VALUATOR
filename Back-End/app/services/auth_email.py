"""Server-only transactional authentication email delivery.

This module is deliberately server-only. Passwords and Supabase verification
tokens are held only long enough to generate and deliver one message and are
never logged or persisted by the application.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage as MIMEEmailMessage
from email.utils import formataddr, parseaddr
from hashlib import sha256
import hmac
from html import escape
import logging
import smtplib
import ssl
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit

import httpx
from supabase import AsyncClient, acreate_client

from app.core.config import Settings


logger = logging.getLogger(__name__)

RESEND_EMAILS_URL = "https://api.resend.com/emails"
WELCOME_DELIVERY_TABLE = "auth_email_deliveries"
RATE_LIMIT_RPC = "consume_auth_email_rate_limit"
EmailKind = Literal["signup_confirmation", "password_recovery", "welcome"]


class EmailConfigurationError(RuntimeError):
    """Raised when transactional email is enabled without safe configuration."""


class EmailDeliveryError(RuntimeError):
    """Sanitized provider failure that contains no recipient or token data."""


@dataclass(frozen=True)
class EmailMessage:
    subject: str
    html: str
    text: str


def normalized_email(value: str) -> str:
    return value.strip().lower()


def recipient_fingerprint(email: str, secret: str) -> str:
    return sha256(f"{secret}:{normalized_email(email)}".encode()).hexdigest()[:16]


def recipient_rate_limit_digest(email: str, secret: str) -> str:
    """Create a non-reversible, deployment-stable recipient identifier."""

    return hmac.new(
        secret.encode(),
        normalized_email(email).encode(),
        sha256,
    ).hexdigest()


def _app_origin(settings: Settings) -> str:
    raw = (settings.app_base_url or "").strip().rstrip("/")
    parsed = urlsplit(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise EmailConfigurationError("APP_BASE_URL must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise EmailConfigurationError("APP_BASE_URL contains unsupported URL components")
    if (
        settings.email_delivery_mode in {"resend", "smtp"}
        and parsed.scheme != "https"
        and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise EmailConfigurationError("Production email links require HTTPS")
    return raw


def validate_email_configuration(settings: Settings) -> None:
    mode = settings.email_delivery_mode
    if mode not in {"disabled", "resend_test", "resend", "smtp"}:
        raise EmailConfigurationError("EMAIL_DELIVERY_MODE is invalid")
    if mode == "disabled":
        raise EmailConfigurationError("Transactional email is disabled")
    if not settings.email_internal_api_token or len(settings.email_internal_api_token) < 32:
        raise EmailConfigurationError("EMAIL_INTERNAL_API_TOKEN must be at least 32 characters")
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise EmailConfigurationError("Supabase admin credentials are required")
    _app_origin(settings)
    if mode in {"resend_test", "resend"}:
        if not settings.resend_api_key:
            raise EmailConfigurationError("RESEND_API_KEY is required")
        if not settings.resend_from_email:
            raise EmailConfigurationError("RESEND_FROM_EMAIL is required")
        if settings.resend_timeout_seconds <= 0 or settings.resend_timeout_seconds > 30:
            raise EmailConfigurationError("RESEND_TIMEOUT_SECONDS must be between 0 and 30")
        if mode == "resend_test" and not settings.resend_test_recipient:
            raise EmailConfigurationError("RESEND_TEST_RECIPIENT is required in test mode")
        if mode == "resend" and "@resend.dev" in settings.resend_from_email.lower():
            raise EmailConfigurationError("Production mode requires a verified sender domain")
    if mode == "smtp":
        _validate_smtp_configuration(settings)


def _single_line(value: str | None, name: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned or "\r" in cleaned or "\n" in cleaned:
        raise EmailConfigurationError(f"{name} is invalid")
    return cleaned


def _smtp_from_address(settings: Settings) -> str:
    value = _single_line(settings.smtp_from_email, "EMAIL_FROM")
    display_name, address = parseaddr(value)
    if display_name or address != value or "@" not in address:
        raise EmailConfigurationError("EMAIL_FROM must be one plain email address")
    return address.lower()


def _validate_smtp_configuration(settings: Settings) -> None:
    host = _single_line(settings.smtp_host, "SMTP_HOST").lower()
    username = _single_line(settings.smtp_username, "SMTP_USERNAME").lower()
    _single_line(settings.smtp_password, "SMTP_PASSWORD")
    from_address = _smtp_from_address(settings)
    _single_line(settings.smtp_from_name, "EMAIL_FROM_NAME")
    if settings.smtp_reply_to:
        _single_line(settings.smtp_reply_to, "EMAIL_REPLY_TO")
    if settings.smtp_port not in {465, 587}:
        raise EmailConfigurationError("SMTP_PORT must be 465 or 587")
    if settings.smtp_timeout_seconds <= 0 or settings.smtp_timeout_seconds > 30:
        raise EmailConfigurationError("SMTP_TIMEOUT_SECONDS must be between 0 and 30")
    if host == "smtp.gmail.com":
        if "@" not in username:
            raise EmailConfigurationError("SMTP_USERNAME must be a full email address")
        if username != from_address:
            raise EmailConfigurationError("EMAIL_FROM must match SMTP_USERNAME for Gmail")


def recipient_is_allowed(email: str, settings: Settings) -> bool:
    if settings.email_delivery_mode != "resend_test":
        return True
    return normalized_email(email) == normalized_email(
        settings.resend_test_recipient or ""
    )


def _safe_next_path(next_path: str) -> str:
    value = next_path.strip() or "/"
    parsed = urlsplit(value)
    if (
        len(value) > 500
        or not value.startswith("/")
        or value.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or "\\" in value
    ):
        return "/"
    return value


def _auth_link(
    settings: Settings,
    *,
    token_hash: str,
    verification_type: str,
    next_path: str,
) -> str:
    query = urlencode(
        {
            "token_hash": token_hash,
            "type": verification_type,
            "next": _safe_next_path(next_path),
        }
    )
    return f"{_app_origin(settings)}/auth/confirm?{query}"


def _email_shell(*, eyebrow: str, heading: str, body: str, cta: str, url: str) -> str:
    safe_url = escape(url, quote=True)
    return f"""<!doctype html>
<html lang="en"><body style="margin:0;background:#07100b;color:#effaf4;font-family:Arial,sans-serif">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#07100b;padding:32px 12px">
<tr><td align="center"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#0b1110;border:1px solid #20352a;border-radius:16px">
<tr><td style="padding:32px">
<p style="margin:0 0 20px;color:#b7ff3c;font-size:12px;font-weight:700;letter-spacing:1.5px">VALUATOR · {escape(eyebrow)}</p>
<h1 style="margin:0 0 16px;color:#ffffff;font-size:26px;line-height:1.25">{escape(heading)}</h1>
<p style="margin:0 0 24px;color:#b8cbbf;font-size:15px;line-height:1.65">{escape(body)}</p>
<table role="presentation" cellpadding="0" cellspacing="0"><tr><td style="background:#b7ff3c;border-radius:10px">
<a href="{safe_url}" style="display:inline-block;padding:13px 20px;color:#07100b;font-size:14px;font-weight:700;text-decoration:none">{escape(cta)}</a>
</td></tr></table>
<p style="margin:24px 0 0;color:#789083;font-size:12px;line-height:1.6">If the button does not work, copy this link into your browser:<br><span style="word-break:break-all">{safe_url}</span></p>
</td></tr></table></td></tr></table>
</body></html>"""


def confirmation_message(url: str) -> EmailMessage:
    body = (
        "Confirm this email address to finish creating your VALUATOR account. "
        "If you did not request this account, you can safely ignore this message."
    )
    return EmailMessage(
        subject="Confirm your VALUATOR email",
        html=_email_shell(
            eyebrow="SECURE ACCOUNT SETUP",
            heading="Confirm your email",
            body=body,
            cta="Confirm email",
            url=url,
        ),
        text=f"Confirm your VALUATOR email\n\n{body}\n\nConfirm email: {url}",
    )


def recovery_message(url: str) -> EmailMessage:
    body = (
        "Use this secure link to choose a new password. If you did not request "
        "a password reset, ignore this message and your password will stay unchanged."
    )
    return EmailMessage(
        subject="Reset your VALUATOR password",
        html=_email_shell(
            eyebrow="PASSWORD RECOVERY",
            heading="Reset your password",
            body=body,
            cta="Reset password",
            url=url,
        ),
        text=f"Reset your VALUATOR password\n\n{body}\n\nReset password: {url}",
    )


def welcome_message(url: str) -> EmailMessage:
    body = (
        "Your account is ready. Search for a company, review its Summary and News, "
        "then compare the five valuation engines with their source inputs and assumptions."
    )
    return EmailMessage(
        subject="Welcome to VALUATOR",
        html=_email_shell(
            eyebrow="ACCOUNT READY",
            heading="Welcome to VALUATOR",
            body=body,
            cta="Open VALUATOR",
            url=url,
        ),
        text=f"Welcome to VALUATOR\n\n{body}\n\nOpen VALUATOR: {url}",
    )


async def send_resend_email(
    settings: Settings,
    *,
    recipient: str,
    kind: EmailKind,
    message: EmailMessage,
    idempotency_key: str,
) -> str:
    validate_email_configuration(settings)
    payload: dict[str, Any] = {
        "from": settings.resend_from_email,
        "to": [normalized_email(recipient)],
        "subject": message.subject,
        "html": message.html,
        "text": message.text,
        "tags": [
            {"name": "category", "value": "authentication"},
            {"name": "template", "value": kind},
        ],
    }
    if settings.resend_reply_to:
        payload["reply_to"] = [settings.resend_reply_to]

    headers = {
        "Authorization": f"Bearer {settings.resend_api_key}",
        "Idempotency-Key": idempotency_key[:256],
    }
    timeout = httpx.Timeout(settings.resend_timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(2):
            try:
                response = await client.post(
                    RESEND_EMAILS_URL,
                    headers=headers,
                    json=payload,
                )
            except httpx.HTTPError as exc:
                if attempt == 0:
                    await asyncio.sleep(0.25)
                    continue
                raise EmailDeliveryError("Resend request failed") from exc
            if 200 <= response.status_code < 300:
                try:
                    message_id = response.json().get("id")
                except ValueError as exc:
                    raise EmailDeliveryError("Resend returned invalid JSON") from exc
                if not isinstance(message_id, str) or not message_id:
                    raise EmailDeliveryError("Resend response did not include an email id")
                return message_id
            if attempt == 0 and (
                response.status_code == 429 or response.status_code >= 500
            ):
                await asyncio.sleep(0.25)
                continue
            raise EmailDeliveryError(
                f"Resend rejected the request with status {response.status_code}"
            )
    raise EmailDeliveryError("Resend request failed")


def _send_smtp_message(
    settings: Settings,
    *,
    recipient: str,
    message: EmailMessage,
    idempotency_key: str,
) -> str:
    from_address = _smtp_from_address(settings)
    to_address = normalized_email(recipient)
    mime = MIMEEmailMessage()
    mime["Subject"] = message.subject
    mime["From"] = formataddr((settings.smtp_from_name, from_address))
    mime["To"] = to_address
    if settings.smtp_reply_to:
        mime["Reply-To"] = settings.smtp_reply_to
    digest = sha256(idempotency_key.encode()).hexdigest()
    domain = from_address.rsplit("@", 1)[1]
    message_id = f"<valuator-{digest}@{domain}>"
    mime["Message-ID"] = message_id
    mime.set_content(message.text)
    mime.add_alternative(message.html, subtype="html")

    context = ssl.create_default_context()
    try:
        if settings.smtp_port == 465:
            connection = smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
                context=context,
            )
        else:
            connection = smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
            )
        with connection as server:
            if settings.smtp_port == 587:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(mime, from_addr=from_address, to_addrs=[to_address])
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("SMTP delivery failed") from exc
    return message_id


async def send_smtp_email(
    settings: Settings,
    *,
    recipient: str,
    kind: EmailKind,
    message: EmailMessage,
    idempotency_key: str,
) -> str:
    del kind
    validate_email_configuration(settings)
    return await asyncio.to_thread(
        _send_smtp_message,
        settings,
        recipient=recipient,
        message=message,
        idempotency_key=idempotency_key,
    )


async def send_transactional_email(
    settings: Settings,
    *,
    recipient: str,
    kind: EmailKind,
    message: EmailMessage,
    idempotency_key: str,
) -> str:
    sender = send_smtp_email if settings.email_delivery_mode == "smtp" else send_resend_email
    return await sender(
        settings,
        recipient=recipient,
        kind=kind,
        message=message,
        idempotency_key=idempotency_key,
    )


async def _supabase_client(settings: Settings) -> AsyncClient:
    if not settings.supabase_url or not settings.supabase_secret_key:
        raise EmailConfigurationError("Supabase admin credentials are required")
    return await acreate_client(settings.supabase_url, settings.supabase_secret_key)


async def _close_client(client: AsyncClient) -> None:
    await client.auth.close()
    postgrest = getattr(client, "_postgrest", None)
    if postgrest is not None:
        await postgrest.aclose()


async def consume_recipient_rate_limit(
    settings: Settings,
    *,
    recipient_digest: str,
    event_type: str,
    limit: int = 3,
    window_seconds: int = 900,
) -> tuple[bool, int]:
    """Consume the durable Supabase email quota shared by all instances."""

    client = await _supabase_client(settings)
    try:
        response = await client.rpc(
            RATE_LIMIT_RPC,
            {
                "p_recipient_digest": recipient_digest,
                "p_event_type": event_type,
                "p_limit": limit,
                "p_window_seconds": window_seconds,
            },
        ).execute()
        rows = response.data
        if not isinstance(rows, list) or len(rows) != 1:
            raise EmailConfigurationError("Email rate limit returned an invalid result")
        allowed = rows[0].get("allowed")
        retry_after = rows[0].get("retry_after_seconds")
        if not isinstance(allowed, bool) or not isinstance(retry_after, int):
            raise EmailConfigurationError("Email rate limit returned an invalid result")
        return allowed, max(1, retry_after)
    except EmailConfigurationError:
        raise
    except Exception as exc:
        raise EmailConfigurationError("Email rate limit is unavailable") from exc
    finally:
        await _close_client(client)


def _email_idempotency(kind: EmailKind, token: str) -> str:
    digest = sha256(token.encode()).hexdigest()
    return f"valuator-{kind}-{digest}"


async def deliver_signup_email(
    settings: Settings,
    *,
    email: str,
    password: str,
    next_path: str,
) -> None:
    client = await _supabase_client(settings)
    try:
        response = await client.auth.admin.generate_link(
            {
                "type": "signup",
                "email": normalized_email(email),
                "password": password,
                "options": {"redirect_to": _app_origin(settings)},
            }
        )
        token_hash = response.properties.hashed_token
        link = _auth_link(
            settings,
            token_hash=token_hash,
            verification_type="signup",
            next_path=next_path,
        )
        await send_transactional_email(
            settings,
            recipient=email,
            kind="signup_confirmation",
            message=confirmation_message(link),
            idempotency_key=_email_idempotency("signup_confirmation", token_hash),
        )
    finally:
        await _close_client(client)


async def deliver_recovery_email(
    settings: Settings,
    *,
    email: str,
    next_path: str,
) -> None:
    client = await _supabase_client(settings)
    try:
        response = await client.auth.admin.generate_link(
            {
                "type": "recovery",
                "email": normalized_email(email),
                "options": {"redirect_to": _app_origin(settings)},
            }
        )
        token_hash = response.properties.hashed_token
        link = _auth_link(
            settings,
            token_hash=token_hash,
            verification_type="recovery",
            next_path=next_path,
        )
        await send_transactional_email(
            settings,
            recipient=email,
            kind="password_recovery",
            message=recovery_message(link),
            idempotency_key=_email_idempotency("password_recovery", token_hash),
        )
    finally:
        await _close_client(client)


async def _mark_welcome(
    client: AsyncClient,
    user_id: str,
    *,
    status: str,
    provider_message_id: str | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    values: dict[str, Any] = {"status": status, "updated_at": now}
    if provider_message_id:
        values["provider_message_id"] = provider_message_id
    if status == "sent":
        values["sent_at"] = now
    await (
        client.table(WELCOME_DELIVERY_TABLE)
        .update(values)
        .eq("user_id", user_id)
        .eq("event_type", "welcome")
        .execute()
    )


async def deliver_welcome_email(settings: Settings, *, user_id: str) -> None:
    client = await _supabase_client(settings)
    try:
        user_response = await client.auth.admin.get_user_by_id(user_id)
        user = user_response.user
        email = user.email if user is not None else None
        confirmed_at = (
            user.confirmed_at or user.email_confirmed_at
            if user is not None
            else None
        )
        if not email or not confirmed_at:
            return

        claim = await client.rpc(
            "claim_auth_email_delivery",
            {"p_user_id": user_id, "p_event_type": "welcome"},
        ).execute()
        if claim.data is not True:
            return
        if not recipient_is_allowed(email, settings):
            await _mark_welcome(client, user_id, status="suppressed")
            return

        try:
            message_id = await send_transactional_email(
                settings,
                recipient=email,
                kind="welcome",
                message=welcome_message(_app_origin(settings)),
                idempotency_key=f"valuator-welcome-{user_id}",
            )
        except Exception:
            await _mark_welcome(client, user_id, status="failed")
            raise
        await _mark_welcome(
            client,
            user_id,
            status="sent",
            provider_message_id=message_id,
        )
    finally:
        await _close_client(client)


async def run_email_job(
    job: Any,
    settings: Settings,
    *,
    event_type: EmailKind,
    email: str | None = None,
    **kwargs: Any,
) -> None:
    fingerprint = (
        recipient_fingerprint(email, settings.email_internal_api_token or "missing")
        if email
        else None
    )
    if email is not None:
        kwargs["email"] = email
    try:
        await job(settings, **kwargs)
    except Exception as exc:
        logger.error(
            "auth_email_delivery_failed",
            extra={
                "event_type": event_type,
                "recipient_fingerprint": fingerprint,
                "error_type": type(exc).__name__,
            },
        )
