from __future__ import annotations

import re
import secrets
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, SecretStr, field_validator

from app.core.config import Settings, get_settings
from app.services.auth_email import (
    EmailConfigurationError,
    deliver_recovery_email,
    deliver_signup_email,
    deliver_welcome_email,
    consume_recipient_rate_limit,
    normalized_email,
    recipient_is_allowed,
    recipient_rate_limit_digest,
    run_email_job,
    validate_email_configuration,
)


router = APIRouter(prefix="/api/internal/auth/email", tags=["internal-auth-email"])
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AuthEmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    next_path: str = Field(default="/", max_length=500)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = normalized_email(value)
        if not _EMAIL_PATTERN.fullmatch(normalized):
            raise ValueError("Enter a valid email address")
        return normalized

    @field_validator("next_path")
    @classmethod
    def validate_next_path(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            not value.startswith("/")
            or value.startswith("//")
            or parsed.scheme
            or parsed.netloc
            or "\\" in value
        ):
            raise ValueError("next_path must be a relative application path")
        return value


class SignupEmailRequest(AuthEmailRequest):
    password: SecretStr = Field(min_length=8, max_length=128)


class WelcomeEmailRequest(BaseModel):
    user_id: UUID


class AcceptedResponse(BaseModel):
    status: str = "accepted"


async def require_internal_token(
    request: Request,
) -> Settings:
    settings = get_settings()
    expected = settings.email_internal_api_token or ""
    header = request.headers.get("authorization", "")
    supplied = header[7:] if header.startswith("Bearer ") else ""
    if not expected or not secrets.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "internal_auth_required"},
        )
    try:
        validate_email_configuration(settings)
    except EmailConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "email_delivery_unavailable"},
        ) from exc
    return settings


def _check_recipient(email: str, settings: Settings) -> None:
    if not recipient_is_allowed(email, settings):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "email_test_recipient_only"},
        )


async def _check_recipient_rate(
    request: Request,
    email: str,
    event_type: str,
    settings: Settings,
) -> None:
    controller = request.app.state.security
    digest = recipient_rate_limit_digest(
        email,
        settings.email_internal_api_token or "",
    )
    allowed, _, retry_after = controller.consume(
        digest,
        f"auth_email:{event_type}",
        3,
        window_seconds=900,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "rate_limited",
                "message": "Too many email requests. Try again later.",
                "retry_after_seconds": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )
    try:
        durable_allowed, durable_retry_after = await consume_recipient_rate_limit(
            settings,
            recipient_digest=digest,
            event_type=event_type,
        )
    except EmailConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "email_rate_limit_unavailable"},
        ) from exc
    if not durable_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "rate_limited",
                "message": "Too many email requests. Try again later.",
                "retry_after_seconds": durable_retry_after,
            },
            headers={"Retry-After": str(durable_retry_after)},
        )


@router.post("/signup", status_code=202, response_model=AcceptedResponse)
async def request_signup_email(
    payload: SignupEmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(require_internal_token)],
) -> AcceptedResponse:
    _check_recipient(payload.email, settings)
    await _check_recipient_rate(request, payload.email, "signup", settings)
    background_tasks.add_task(
        run_email_job,
        deliver_signup_email,
        settings,
        event_type="signup_confirmation",
        email=payload.email,
        password=payload.password.get_secret_value(),
        next_path=payload.next_path,
    )
    return AcceptedResponse()


@router.post("/recovery", status_code=202, response_model=AcceptedResponse)
async def request_recovery_email(
    payload: AuthEmailRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(require_internal_token)],
) -> AcceptedResponse:
    _check_recipient(payload.email, settings)
    await _check_recipient_rate(request, payload.email, "recovery", settings)
    background_tasks.add_task(
        run_email_job,
        deliver_recovery_email,
        settings,
        event_type="password_recovery",
        email=payload.email,
        next_path=payload.next_path,
    )
    return AcceptedResponse()


@router.post("/welcome", status_code=202, response_model=AcceptedResponse)
async def request_welcome_email(
    payload: WelcomeEmailRequest,
    background_tasks: BackgroundTasks,
    settings: Annotated[Settings, Depends(require_internal_token)],
) -> AcceptedResponse:
    background_tasks.add_task(
        run_email_job,
        deliver_welcome_email,
        settings,
        event_type="welcome",
        user_id=str(payload.user_id),
    )
    return AcceptedResponse()
