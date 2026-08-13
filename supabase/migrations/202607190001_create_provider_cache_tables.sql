create table if not exists public.provider_cache_entries (
    ticker text not null,
    data_type text not null,
    payload jsonb not null,
    fetched_at timestamptz not null,
    expires_at timestamptz not null,
    primary key (ticker, data_type),
    constraint provider_cache_ticker_format
        check (ticker ~ '^[A-Z][A-Z0-9.-]{0,9}$'),
    constraint provider_cache_data_type_not_blank
        check (length(btrim(data_type)) > 0),
    constraint provider_cache_expiry_after_fetch
        check (expires_at > fetched_at)
);

create index if not exists idx_provider_cache_expires_at
    on public.provider_cache_entries (expires_at);

create table if not exists public.news_cache_articles (
    ticker text not null,
    url text not null,
    published_at timestamptz not null,
    payload jsonb not null,
    cached_at timestamptz not null default now(),
    primary key (ticker, url),
    constraint news_cache_ticker_format
        check (ticker ~ '^[A-Z][A-Z0-9.-]{0,9}$'),
    constraint news_cache_url_not_blank
        check (length(btrim(url)) > 0)
);

create index if not exists idx_news_cache_ticker_published_at
    on public.news_cache_articles (ticker, published_at desc);

create index if not exists idx_news_cache_published_at
    on public.news_cache_articles (published_at);

alter table public.provider_cache_entries enable row level security;
alter table public.news_cache_articles enable row level security;

-- Cache tables are backend infrastructure. Future browser/authenticated clients
-- must not gain access when Supabase Auth is introduced.
revoke all on table public.provider_cache_entries from anon, authenticated;
revoke all on table public.news_cache_articles from anon, authenticated;
grant select, insert, update, delete on table public.provider_cache_entries to service_role;
grant select, insert, update, delete on table public.news_cache_articles to service_role;

comment on table public.provider_cache_entries is
    'Backend-only provider payload cache. Access requires the server secret key.';
comment on table public.news_cache_articles is
    'Backend-only per-ticker news cache. Access requires the server secret key.';
