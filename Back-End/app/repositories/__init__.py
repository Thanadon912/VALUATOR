"""Persistence boundaries for backend infrastructure data."""

from app.repositories.supabase_cache import (
    CacheEntry,
    CacheUnavailableError,
    FinancialCacheRepository,
    NewsCacheRecord,
    NewsCacheRepository,
    SupabaseCacheRepository,
    close_cache_repository,
    get_cache_repository,
)

__all__ = [
    "CacheEntry",
    "CacheUnavailableError",
    "FinancialCacheRepository",
    "NewsCacheRecord",
    "NewsCacheRepository",
    "SupabaseCacheRepository",
    "close_cache_repository",
    "get_cache_repository",
]
