import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from app.core.runtime_paths import runtime_cache_path


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


def _load_environment_files() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    load_dotenv(BACKEND_ROOT / ".env", override=False)


def _extraction_cache_dir(env_name: str, directory_name: str) -> str:
    configured = os.getenv(env_name)
    if not configured:
        return str(runtime_cache_path(directory_name))
    path = Path(configured)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


def _project_path(env_name: str, default: Path) -> str:
    configured = os.getenv(env_name)
    if not configured:
        return str(default)
    path = Path(configured)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


def _optional_env(env_name: str) -> str | None:
    value = os.getenv(env_name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@dataclass(frozen=True)
class Settings:
    enable_live_providers: bool
    performance_cache_only_enabled: bool
    sec_user_agent: str
    finnhub_api_key: str | None
    fmp_api_key: str | None
    supabase_url: str | None
    supabase_secret_key: str | None
    supabase_timeout_seconds: float
    fred_api_key: str | None
    alpha_vantage_api_key: str | None
    alpaca_api_key: str | None
    alpaca_api_secret: str | None
    alpaca_data_feed: str | None
    provider_timeout_seconds: float
    supply_chain_ai_enabled: bool
    gemini_api_key: str | None
    gemini_supply_chain_model: str
    supply_chain_cache_dir: str
    customer_mix_ai_enabled: bool
    gemini_customer_mix_primary_model: str
    gemini_customer_mix_secondary_model: str
    customer_mix_ai_rate_limit_cooldown_seconds: float
    customer_mix_cache_dir: str
    sec_13f_cache_dir: str
    sec_13f_database_path: str
    sec_13f_mapping_file: str
    cors_allowed_origins: tuple[str, ...]
    trusted_proxy_cidrs: tuple[str, ...]
    api_rate_limit_enabled: bool
    api_general_rate_per_minute: int
    api_market_rate_per_minute: int
    api_valuation_rate_per_minute: int
    api_dcf_rate_per_minute: int
    api_auth_email_rate_per_minute: int
    api_dcf_concurrency: int
    api_provider_concurrency: int
    email_delivery_mode: str
    email_internal_api_token: str | None
    resend_api_key: str | None
    resend_from_email: str
    resend_test_recipient: str | None
    resend_reply_to: str | None
    resend_timeout_seconds: float
    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from_email: str | None
    smtp_from_name: str
    smtp_reply_to: str | None
    smtp_timeout_seconds: float
    app_base_url: str | None


def get_settings() -> Settings:
    _load_environment_files()
    return Settings(
        enable_live_providers=os.getenv("ENABLE_LIVE_PROVIDERS", "true").lower()
        not in {"0", "false", "no"},
        performance_cache_only_enabled=os.getenv(
            "PERFORMANCE_CACHE_ONLY_ENABLED",
            "false",
        ).lower()
        in {"1", "true", "yes"},
        sec_user_agent=os.getenv(
            "SEC_USER_AGENT",
            "USAStockAnalysis local-development contact@example.com",
        ),
        finnhub_api_key=_optional_env("FINNHUB_API_KEY"),
        fmp_api_key=_optional_env("FMP_API_KEY"),
        supabase_url=_optional_env("SUPABASE_URL"),
        supabase_secret_key=_optional_env("SUPABASE_SECRET_KEY"),
        supabase_timeout_seconds=float(os.getenv("SUPABASE_TIMEOUT_SECONDS", "5")),
        fred_api_key=_optional_env("FRED_API_KEY"),
        alpha_vantage_api_key=_optional_env("ALPHA_VANTAGE_API_KEY"),
        alpaca_api_key=_optional_env("ALPACA_API_KEY")
        or _optional_env("APCA_API_KEY_ID"),
        alpaca_api_secret=_optional_env("ALPACA_API_SECRET")
        or _optional_env("APCA_API_SECRET_KEY"),
        alpaca_data_feed=_optional_env("ALPACA_DATA_FEED") or "iex",
        provider_timeout_seconds=float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "8")),
        supply_chain_ai_enabled=os.getenv(
            "SUPPLY_CHAIN_AI_ENABLED",
            "false",
        ).lower()
        in {"1", "true", "yes"},
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_supply_chain_model=os.getenv(
            "GEMINI_SUPPLY_CHAIN_MODEL",
            "gemini-3.1-flash-lite",
        ),
        customer_mix_ai_enabled=os.getenv(
            "CUSTOMER_MIX_AI_ENABLED",
            os.getenv("SUPPLY_CHAIN_AI_ENABLED", "false"),
        ).lower()
        in {"1", "true", "yes"},
        gemini_customer_mix_primary_model=os.getenv(
            "GEMINI_CUSTOMER_MIX_PRIMARY_MODEL",
            "gemini-3.1-flash-lite",
        ),
        gemini_customer_mix_secondary_model=os.getenv(
            "GEMINI_CUSTOMER_MIX_SECONDARY_MODEL",
            "gemini-2.5-flash-lite",
        ),
        customer_mix_ai_rate_limit_cooldown_seconds=float(os.getenv(
            "CUSTOMER_MIX_AI_RATE_LIMIT_COOLDOWN_SECONDS",
            "300",
        )),
        supply_chain_cache_dir=_extraction_cache_dir(
            "SUPPLY_CHAIN_CACHE_DIR",
            "supply_chain",
        ),
        customer_mix_cache_dir=_extraction_cache_dir(
            "CUSTOMER_MIX_CACHE_DIR",
            "customer_mix",
        ),
        sec_13f_cache_dir=_project_path(
            "SEC_13F_CACHE_DIR",
            runtime_cache_path("13f"),
        ),
        sec_13f_database_path=_project_path(
            "SEC_13F_DATABASE_PATH",
            runtime_cache_path("13f", "latest.sqlite3"),
        ),
        sec_13f_mapping_file=_project_path(
            "SEC_13F_MAPPING_FILE",
            BACKEND_ROOT / "config" / "security_identifier_mappings.json",
        ),
        cors_allowed_origins=tuple(
            origin.strip()
            for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",")
            if origin.strip()
        ),
        trusted_proxy_cidrs=tuple(
            cidr.strip()
            for cidr in os.getenv(
                "TRUSTED_PROXY_CIDRS",
                "127.0.0.1/32,::1/128,172.16.0.0/12",
            ).split(",")
            if cidr.strip()
        ),
        api_rate_limit_enabled=os.getenv("API_RATE_LIMIT_ENABLED", "true").lower()
        not in {"0", "false", "no"},
        api_general_rate_per_minute=int(os.getenv("API_GENERAL_RATE_PER_MINUTE", "120")),
        api_market_rate_per_minute=int(os.getenv("API_MARKET_RATE_PER_MINUTE", "30")),
        api_valuation_rate_per_minute=int(os.getenv("API_VALUATION_RATE_PER_MINUTE", "20")),
        api_dcf_rate_per_minute=int(os.getenv("API_DCF_RATE_PER_MINUTE", "6")),
        api_auth_email_rate_per_minute=int(
            os.getenv("API_AUTH_EMAIL_RATE_PER_MINUTE", "10")
        ),
        api_dcf_concurrency=int(os.getenv("API_DCF_CONCURRENCY", "2")),
        api_provider_concurrency=int(os.getenv("API_PROVIDER_CONCURRENCY", "8")),
        email_delivery_mode=(
            os.getenv("EMAIL_DELIVERY_MODE")
            or {
                "gmail_smtp": "smtp",
                "smtp": "smtp",
                "resend": "resend",
                "resend_test": "resend_test",
            }.get(os.getenv("EMAIL_PROVIDER", "").strip().lower(), "disabled")
        ).strip().lower(),
        email_internal_api_token=_optional_env("EMAIL_INTERNAL_API_TOKEN"),
        resend_api_key=_optional_env("RESEND_API_KEY"),
        resend_from_email=os.getenv(
            "RESEND_FROM_EMAIL",
            "VALUATOR <onboarding@resend.dev>",
        ).strip(),
        resend_test_recipient=_optional_env("RESEND_TEST_RECIPIENT"),
        resend_reply_to=_optional_env("RESEND_REPLY_TO"),
        resend_timeout_seconds=float(os.getenv("RESEND_TIMEOUT_SECONDS", "5")),
        smtp_host=_optional_env("SMTP_HOST"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_username=_optional_env("SMTP_USERNAME"),
        smtp_password=_optional_env("SMTP_PASSWORD"),
        smtp_from_email=_optional_env("EMAIL_FROM"),
        smtp_from_name=os.getenv("EMAIL_FROM_NAME", "VALUATOR").strip(),
        smtp_reply_to=_optional_env("EMAIL_REPLY_TO"),
        smtp_timeout_seconds=float(os.getenv("SMTP_TIMEOUT_SECONDS", "10")),
        app_base_url=_optional_env("APP_BASE_URL"),
    )
