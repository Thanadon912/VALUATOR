import socket
from contextlib import asynccontextmanager

# Monkey patch socket to only return IPv4 (AF_INET) to prevent 
# 60-second timeouts from IPv6 blackholes in the sandbox environment.
old_getaddrinfo = socket.getaddrinfo

def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [response for response in responses if response[0] == socket.AF_INET]

socket.getaddrinfo = new_getaddrinfo

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio

from app.api.routes.summary import router as summary_router
from app.api.routes.news import router as news_router
from app.api.routes.quote import router as quote_router
from app.api.routes.valuation import router as valuation_router
from app.api.routes.company_intelligence import router as company_intelligence_router
from app.api.routes.auth_email import router as auth_email_router
from app.core.validation import normalize_ticker
from app.core.config import get_settings
from app.core.performance_cache import (
    PERFORMANCE_CACHE_ONLY_HEADER,
    reset_performance_cache_only,
    set_performance_cache_only,
)
from app.models import WorkspaceResponse
from app.providers.placeholder import build_placeholder_sections
from app.repositories import close_cache_repository
from app.core.security import (
    ApiSecurityController,
    apply_security_headers,
    request_id_for,
    security_error,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        yield
    finally:
        await close_cache_repository()


app = FastAPI(
    title="USA Stock Analysis API",
    version="0.2.0",
    description="Universal Fair Value Engine & AI-Ready API",
    lifespan=lifespan,
)

_settings = get_settings()
if "*" in _settings.cors_allowed_origins:
    raise RuntimeError("CORS_ALLOWED_ORIGINS must contain exact origins, not '*'.")
if _settings.cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_settings.cors_allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", PERFORMANCE_CACHE_ONLY_HEADER],
    )

_security = ApiSecurityController(_settings)
app.state.security = _security


@app.middleware("http")
async def api_security_middleware(request: Request, call_next):
    request_id = request_id_for(request)
    path = request.url.path
    request.state.client_ip = _security.client_ip(request)
    if (
        not _settings.api_rate_limit_enabled
        or request.method == "OPTIONS"
        or path == "/health"
        or not path.startswith("/api/")
    ):
        response = await call_next(request)
        apply_security_headers(response, request_id)
        return response

    group, fallback_limit = _security.route_group(path)
    limit = max(1, _security.configured_limit(group, fallback_limit))
    allowed, remaining, retry_after = _security.consume(
        request.state.client_ip, group, limit
    )
    if not allowed:
        return security_error(
            status_code=429,
            code="rate_limited",
            message="Too many requests. Try again after the indicated delay.",
            request_id=request_id,
            retry_after=retry_after,
        )

    slot = _security.concurrency_slot(group)
    acquired = False
    try:
        if slot is not None:
            try:
                await asyncio.wait_for(slot.acquire(), timeout=0.05)
                acquired = True
            except TimeoutError:
                return security_error(
                    status_code=503,
                    code="capacity_exceeded",
                    message="This calculation is at capacity. Try again shortly.",
                    request_id=request_id,
                    retry_after=5,
                )
        response = await call_next(request)
    finally:
        if acquired and slot is not None:
            slot.release()

    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    apply_security_headers(response, request_id)
    return response


@app.middleware("http")
async def performance_cache_only_middleware(request: Request, call_next):
    cache_only_requested = (
        request.headers.get(PERFORMANCE_CACHE_ONLY_HEADER, "").strip().lower()
        == "true"
    )
    if not cache_only_requested:
        return await call_next(request)

    if not get_settings().performance_cache_only_enabled:
        response = JSONResponse(
            status_code=403,
            content={
                "detail": {
                    "code": "performance_cache_only_disabled",
                    "message": (
                        "Cache-only performance requests require "
                        "PERFORMANCE_CACHE_ONLY_ENABLED=true."
                    ),
                }
            },
        )
        apply_security_headers(response, request_id_for(request))
        return response

    token = set_performance_cache_only(True)
    try:
        return await call_next(request)
    finally:
        reset_performance_cache_only(token)

app.include_router(summary_router)
app.include_router(news_router)
app.include_router(quote_router)
app.include_router(valuation_router)
app.include_router(company_intelligence_router)
app.include_router(auth_email_router)

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

@app.get("/api/workspace/{ticker}", response_model=WorkspaceResponse)
def get_workspace(ticker: str) -> WorkspaceResponse:
    try:
        normalized = normalize_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return WorkspaceResponse(
        ticker=normalized,
        mode="placeholder",
        sections=build_placeholder_sections(),
        required_user_inputs=[
            "DCF revenue growth rate",
            "DCF free cash flow margin",
            "DCF discount rate",
            "DCF terminal growth rate",
            "DCF forecast period",
            "Base revenue",
            "Cash and equivalents",
            "Total debt",
            "Shares outstanding",
        ],
    )
