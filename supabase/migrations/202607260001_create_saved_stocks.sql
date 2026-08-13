create table if not exists public.saved_stocks (
    user_id uuid not null references auth.users (id) on delete cascade,
    ticker text not null,
    added_at timestamptz not null default now(),
    last_visited_at timestamptz not null default now(),
    last_section text not null default 'summary',
    primary key (user_id, ticker),
    constraint saved_stocks_ticker_format
        check (ticker ~ '^[A-Z][A-Z0-9.-]{0,9}$'),
    constraint saved_stocks_last_section
        check (last_section in ('summary', 'news', 'valuation'))
);

create index if not exists idx_saved_stocks_user_last_visited
    on public.saved_stocks (user_id, last_visited_at desc);

alter table public.saved_stocks enable row level security;

revoke all on table public.saved_stocks from public, anon, authenticated;
grant select, insert, update, delete on table public.saved_stocks to authenticated;
grant select, insert, update, delete on table public.saved_stocks to service_role;

create policy "saved_stocks_select_own"
    on public.saved_stocks
    for select
    to authenticated
    using ((select auth.uid()) = user_id);

create policy "saved_stocks_insert_own"
    on public.saved_stocks
    for insert
    to authenticated
    with check ((select auth.uid()) = user_id);

create policy "saved_stocks_update_own"
    on public.saved_stocks
    for update
    to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "saved_stocks_delete_own"
    on public.saved_stocks
    for delete
    to authenticated
    using ((select auth.uid()) = user_id);

create or replace function public.merge_saved_stocks(p_items jsonb)
returns setof public.saved_stocks
language plpgsql
security invoker
set search_path = ''
as $$
declare
    authenticated_user_id uuid := auth.uid();
begin
    if authenticated_user_id is null then
        raise exception 'Authentication is required to merge saved stocks.'
            using errcode = '42501';
    end if;

    if p_items is null or jsonb_typeof(p_items) <> 'array' then
        raise exception 'p_items must be a JSON array.'
            using errcode = '22023';
    end if;

    if exists (
        select 1
        from jsonb_array_elements(p_items) as element(item)
        where jsonb_typeof(item) <> 'object'
           or coalesce(jsonb_typeof(item -> 'ticker'), 'null') <> 'string'
           or coalesce(jsonb_typeof(item -> 'added_at'), 'null') <> 'string'
           or coalesce(jsonb_typeof(item -> 'last_visited_at'), 'null') <> 'string'
           or coalesce(jsonb_typeof(item -> 'last_section'), 'null') <> 'string'
    ) then
        raise exception 'Each saved stock must include ticker, added_at, last_visited_at, and last_section strings.'
            using errcode = '22023';
    end if;

    return query
    with parsed as (
        select
            upper(btrim(item ->> 'ticker')) as ticker,
            (item ->> 'added_at')::timestamptz as added_at,
            (item ->> 'last_visited_at')::timestamptz as last_visited_at,
            item ->> 'last_section' as last_section,
            ordinal
        from jsonb_array_elements(p_items) with ordinality as element(item, ordinal)
    ),
    aggregated as (
        select
            parsed.ticker,
            min(parsed.added_at) as added_at,
            max(parsed.last_visited_at) as last_visited_at,
            (array_agg(
                parsed.last_section
                order by parsed.last_visited_at desc, parsed.ordinal desc
            ))[1] as last_section
        from parsed
        group by parsed.ticker
    )
    insert into public.saved_stocks as saved (
        user_id,
        ticker,
        added_at,
        last_visited_at,
        last_section
    )
    select
        authenticated_user_id,
        aggregated.ticker,
        aggregated.added_at,
        aggregated.last_visited_at,
        aggregated.last_section
    from aggregated
    on conflict (user_id, ticker) do update
    set
        added_at = least(saved.added_at, excluded.added_at),
        last_section = case
            when excluded.last_visited_at >= saved.last_visited_at
                then excluded.last_section
            else saved.last_section
        end,
        last_visited_at = greatest(saved.last_visited_at, excluded.last_visited_at)
    returning saved.*;
end;
$$;

revoke all on function public.merge_saved_stocks(jsonb) from public, anon, service_role;
grant execute on function public.merge_saved_stocks(jsonb) to authenticated;

comment on table public.saved_stocks is
    'User-owned stock shortcuts. Live market data and valuation outputs are not persisted here.';
comment on function public.merge_saved_stocks(jsonb) is
    'Atomically merges guest saved stocks into the authenticated user account.';
