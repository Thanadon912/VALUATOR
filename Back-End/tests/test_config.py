from app.core.config import get_settings


def test_settings_read_provider_environment(monkeypatch):
    monkeypatch.setenv("ENABLE_LIVE_PROVIDERS", "true")
    monkeypatch.setenv("PERFORMANCE_CACHE_ONLY_ENABLED", "true")
    monkeypatch.setenv("SEC_USER_AGENT", "TestApp test@example.com")
    monkeypatch.setenv("FRED_API_KEY", "fred-test-key")
    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "server-only-test-key")
    monkeypatch.setenv("SUPABASE_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("ALPACA_API_KEY", "alpaca-key")
    monkeypatch.setenv("ALPACA_API_SECRET", "alpaca-secret")
    monkeypatch.setenv("ALPACA_DATA_FEED", "iex")
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", "4.5")
    monkeypatch.setenv("SUPPLY_CHAIN_AI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_SUPPLY_CHAIN_MODEL", "test-model")
    monkeypatch.setenv("SUPPLY_CHAIN_CACHE_DIR", "/tmp/supply-chain-cache")
    monkeypatch.setenv("CUSTOMER_MIX_AI_ENABLED", "true")
    monkeypatch.setenv(
        "GEMINI_CUSTOMER_MIX_PRIMARY_MODEL",
        "primary-model",
    )
    monkeypatch.setenv(
        "GEMINI_CUSTOMER_MIX_SECONDARY_MODEL",
        "secondary-model",
    )
    monkeypatch.setenv(
        "CUSTOMER_MIX_AI_RATE_LIMIT_COOLDOWN_SECONDS",
        "120",
    )
    monkeypatch.setenv(
        "CUSTOMER_MIX_CACHE_DIR",
        "/tmp/customer-mix-cache",
    )
    monkeypatch.setenv("SEC_13F_CACHE_DIR", "/tmp/sec-13f-cache")
    monkeypatch.setenv("SEC_13F_DATABASE_PATH", "/tmp/sec-13f.sqlite3")
    monkeypatch.setenv("SEC_13F_MAPPING_FILE", "/tmp/sec-13f-mappings.json")
    monkeypatch.setenv("API_AUTH_EMAIL_RATE_PER_MINUTE", "7")
    monkeypatch.setenv("EMAIL_DELIVERY_MODE", "resend_test")
    monkeypatch.setenv("EMAIL_INTERNAL_API_TOKEN", "internal-email-token")
    monkeypatch.setenv("RESEND_API_KEY", "resend-test-key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "VALUATOR <onboarding@resend.dev>")
    monkeypatch.setenv("RESEND_TEST_RECIPIENT", "owner@example.com")
    monkeypatch.setenv("RESEND_REPLY_TO", "support@example.com")
    monkeypatch.setenv("RESEND_TIMEOUT_SECONDS", "2.5")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("EMAIL_FROM", "sender@example.com")
    monkeypatch.setenv("EMAIL_FROM_NAME", "Test VALUATOR")
    monkeypatch.setenv("EMAIL_REPLY_TO", "reply@example.com")
    monkeypatch.setenv("SMTP_TIMEOUT_SECONDS", "4")
    monkeypatch.setenv("APP_BASE_URL", "http://frontend.test")

    settings = get_settings()

    assert settings.enable_live_providers is True
    assert settings.performance_cache_only_enabled is True
    assert settings.sec_user_agent == "TestApp test@example.com"
    assert settings.fred_api_key == "fred-test-key"
    assert settings.supabase_url == "https://project.supabase.co"
    assert settings.supabase_secret_key == "server-only-test-key"
    assert settings.supabase_timeout_seconds == 3.5
    assert settings.alpaca_api_key == "alpaca-key"
    assert settings.alpaca_api_secret == "alpaca-secret"
    assert settings.alpaca_data_feed == "iex"
    assert settings.provider_timeout_seconds == 4.5
    assert settings.supply_chain_ai_enabled is True
    assert settings.gemini_api_key == "test-key"
    assert settings.gemini_supply_chain_model == "test-model"
    assert settings.supply_chain_cache_dir == "/tmp/supply-chain-cache"
    assert settings.customer_mix_ai_enabled is True
    assert settings.gemini_customer_mix_primary_model == "primary-model"
    assert settings.gemini_customer_mix_secondary_model == "secondary-model"
    assert settings.customer_mix_ai_rate_limit_cooldown_seconds == 120
    assert settings.customer_mix_cache_dir == "/tmp/customer-mix-cache"
    assert settings.sec_13f_cache_dir == "/tmp/sec-13f-cache"
    assert settings.sec_13f_database_path == "/tmp/sec-13f.sqlite3"
    assert settings.sec_13f_mapping_file == "/tmp/sec-13f-mappings.json"
    assert settings.api_auth_email_rate_per_minute == 7
    assert settings.email_delivery_mode == "resend_test"
    assert settings.email_internal_api_token == "internal-email-token"
    assert settings.resend_api_key == "resend-test-key"
    assert settings.resend_from_email == "VALUATOR <onboarding@resend.dev>"
    assert settings.resend_test_recipient == "owner@example.com"
    assert settings.resend_reply_to == "support@example.com"
    assert settings.resend_timeout_seconds == 2.5
    assert settings.smtp_host == "smtp.gmail.com"
    assert settings.smtp_port == 587
    assert settings.smtp_username == "sender@example.com"
    assert settings.smtp_password == "app-password"
    assert settings.smtp_from_email == "sender@example.com"
    assert settings.smtp_from_name == "Test VALUATOR"
    assert settings.smtp_reply_to == "reply@example.com"
    assert settings.smtp_timeout_seconds == 4
    assert settings.app_base_url == "http://frontend.test"


def test_supabase_configuration_is_optional(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "")

    settings = get_settings()

    assert settings.supabase_url is None
    assert settings.supabase_secret_key is None


def test_gmail_provider_selects_smtp_without_legacy_mode(monkeypatch):
    monkeypatch.delenv("EMAIL_DELIVERY_MODE", raising=False)
    monkeypatch.setenv("EMAIL_PROVIDER", "gmail_smtp")

    assert get_settings().email_delivery_mode == "smtp"
