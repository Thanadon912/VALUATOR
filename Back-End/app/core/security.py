from __future__ import annotations

import asyncio
from dataclasses import dataclass
import ipaddress
import logging
import os
from threading import Lock
from time import monotonic
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.core.config import Settings


logger = logging.getLogger(__name__)


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class ApiSecurityController:
    """Per-process abuse controls that complement the Cloudflare edge limit."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._bucket_lock = Lock()
        self._trusted_networks = tuple(
            ipaddress.ip_network(value, strict=False)
            for value in settings.trusted_proxy_cidrs
        )
        self._dcf_slots = asyncio.Semaphore(max(1, settings.api_dcf_concurrency))
        self._provider_slots = asyncio.Semaphore(
            max(1, settings.api_provider_concurrency)
        )

    def client_ip(self, request: Request) -> str:
        if os.getenv("VERCEL") == "1" and request.headers.get("x-vercel-id"):
            vercel_forwarded = request.headers.get("x-vercel-forwarded-for", "")
            candidate = vercel_forwarded.split(",", 1)[0].strip()
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass

        peer = request.client.host if request.client else "unknown"
        try:
            peer_ip = ipaddress.ip_address(peer)
        except ValueError:
            return peer

        if not any(peer_ip in network for network in self._trusted_networks):
            return peer

        forwarded = request.headers.get("x-forwarded-for", "")
        candidates = [value.strip() for value in forwarded.split(",") if value.strip()]
        candidates.append(peer)
        for candidate in reversed(candidates):
            try:
                address = ipaddress.ip_address(candidate)
            except ValueError:
                continue
            if not any(address in network for network in self._trusted_networks):
                return str(address)
        return peer

    @staticmethod
    def route_group(path: str) -> tuple[str, int]:
        if path.startswith("/api/internal/auth/email/"):
            return "auth_email", 10
        if path == "/api/v1/valuation/dcf":
            return "dcf", 6
        if path.startswith("/api/v1/valuation/") or path.startswith(
            "/api/v1/company-intelligence/"
        ):
            return "valuation", 20
        if path.endswith("/summary") or path.endswith("/news"):
            return "market", 30
        return "general", 120

    def configured_limit(self, group: str, fallback: int) -> int:
        return {
            "dcf": self.settings.api_dcf_rate_per_minute,
            "valuation": self.settings.api_valuation_rate_per_minute,
            "market": self.settings.api_market_rate_per_minute,
            "general": self.settings.api_general_rate_per_minute,
            "auth_email": self.settings.api_auth_email_rate_per_minute,
        }.get(group, fallback)

    def consume(
        self,
        client_ip: str,
        group: str,
        limit: int,
        *,
        window_seconds: float = 60.0,
    ) -> tuple[bool, int, int]:
        now = monotonic()
        key = (client_ip, group)
        with self._bucket_lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=float(limit), updated_at=now)
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(
                float(limit),
                bucket.tokens + elapsed * limit / max(1.0, window_seconds),
            )
            bucket.updated_at = now
            allowed = bucket.tokens >= 1.0
            if allowed:
                bucket.tokens -= 1.0
            self._buckets[key] = bucket

            if len(self._buckets) > 4096:
                cutoff = now - 600
                self._buckets = {
                    item_key: item
                    for item_key, item in self._buckets.items()
                    if item.updated_at >= cutoff
                }

        remaining = max(0, int(bucket.tokens))
        retry_after = max(
            1,
            int((1.0 - bucket.tokens) * max(1.0, window_seconds) / limit) + 1,
        )
        return allowed, remaining, retry_after

    def concurrency_slot(self, group: str) -> asyncio.Semaphore | None:
        if group == "dcf":
            return self._dcf_slots
        if group in {"valuation", "market"}:
            return self._provider_slots
        return None


def security_error(
    *, status_code: int, code: str, message: str, request_id: str, retry_after: int
) -> JSONResponse:
    response = JSONResponse(
        status_code=status_code,
        content={
            "detail": {
                "code": code,
                "message": message,
                "retry_after_seconds": retry_after,
                "request_id": request_id,
            }
        },
        headers={"Retry-After": str(retry_after), "X-Request-ID": request_id},
    )
    apply_security_headers(response, request_id)
    return response


def apply_security_headers(response: Response, request_id: str) -> None:
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
    )
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
        "form-action 'self'"
    )


def request_id_for(request: Request) -> str:
    candidate = request.headers.get("x-request-id", "").strip()
    if 1 <= len(candidate) <= 64 and all(char.isalnum() or char in "-_." for char in candidate):
        return candidate
    return uuid4().hex
