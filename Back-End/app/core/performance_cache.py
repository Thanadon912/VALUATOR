from __future__ import annotations

from contextvars import ContextVar, Token
from typing import NoReturn

from fastapi import HTTPException


PERFORMANCE_CACHE_ONLY_HEADER = "X-VALUATOR-Cache-Only"

_performance_cache_only: ContextVar[bool] = ContextVar(
    "performance_cache_only",
    default=False,
)


def set_performance_cache_only(enabled: bool) -> Token[bool]:
    """Set request-scoped cache-only state and return its reset token."""
    return _performance_cache_only.set(enabled)


def reset_performance_cache_only(token: Token[bool]) -> None:
    _performance_cache_only.reset(token)


def is_performance_cache_only() -> bool:
    return _performance_cache_only.get()


def raise_performance_cache_miss(resource: str, cache_key: str) -> NoReturn:
    """Abort a cache-only request without allowing a provider fallback."""
    raise HTTPException(
        status_code=503,
        detail={
            "code": "performance_cache_miss",
            "message": "Required warmed data is not present in this API process.",
            "resource": resource,
            "cache_key": cache_key,
        },
    )
