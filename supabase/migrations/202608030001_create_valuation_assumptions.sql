create table if not exists public.valuation_assumptions (
    user_id uuid not null references auth.users (id) on delete cascade,
    ticker text not null,
    stage_1_growth_rate double precision not null,
    perpetual_growth_rate double precision not null,
    discount_rate double precision not null,
    updated_at timestamptz not null default now(),
    primary key (user_id, ticker),
    constraint valuation_assumptions_ticker_format
        check (ticker ~ '^[A-Z][A-Z0-9.-]{0,9}$'),
    constraint valuation_assumptions_growth_range
        check (stage_1_growth_rate between 0.0 and 0.20),
    constraint valuation_assumptions_perpetual_range
        check (perpetual_growth_rate between 0.01 and 0.04),
    constraint valuation_assumptions_discount_range
        check (discount_rate between 0.05 and 0.15),
    constraint valuation_assumptions_discount_above_perpetual
        check (discount_rate > perpetual_growth_rate)
);

alter table public.valuation_assumptions enable row level security;

revoke all on table public.valuation_assumptions from public, anon, authenticated;
grant select, insert, update, delete on table public.valuation_assumptions to authenticated;
grant select, insert, update, delete on table public.valuation_assumptions to service_role;

create policy "valuation_assumptions_select_own"
    on public.valuation_assumptions for select to authenticated
    using ((select auth.uid()) = user_id);

create policy "valuation_assumptions_insert_own"
    on public.valuation_assumptions for insert to authenticated
    with check ((select auth.uid()) = user_id);

create policy "valuation_assumptions_update_own"
    on public.valuation_assumptions for update to authenticated
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "valuation_assumptions_delete_own"
    on public.valuation_assumptions for delete to authenticated
    using ((select auth.uid()) = user_id);

create or replace function public.merge_valuation_assumptions(p_items jsonb)
returns setof public.valuation_assumptions
language plpgsql
security invoker
set search_path = ''
as $$
declare
    authenticated_user_id uuid := auth.uid();
begin
    if authenticated_user_id is null then
        raise exception 'Authentication is required to merge valuation assumptions.' using errcode = '42501';
    end if;
    if p_items is null or jsonb_typeof(p_items) <> 'array' then
        raise exception 'p_items must be a JSON array.' using errcode = '22023';
    end if;
    if exists (
        select 1 from jsonb_array_elements(p_items) as element(item)
        where jsonb_typeof(item) <> 'object'
           or coalesce(jsonb_typeof(item -> 'ticker'), 'null') <> 'string'
           or coalesce(jsonb_typeof(item -> 'stage_1_growth_rate'), 'null') <> 'number'
           or coalesce(jsonb_typeof(item -> 'perpetual_growth_rate'), 'null') <> 'number'
           or coalesce(jsonb_typeof(item -> 'discount_rate'), 'null') <> 'number'
           or coalesce(jsonb_typeof(item -> 'updated_at'), 'null') <> 'string'
    ) then
        raise exception 'Each item must include ticker, three numeric rates, and updated_at.' using errcode = '22023';
    end if;

    return query
    with parsed as (
        select
            upper(btrim(item ->> 'ticker')) as ticker,
            (item ->> 'stage_1_growth_rate')::double precision as stage_1_growth_rate,
            (item ->> 'perpetual_growth_rate')::double precision as perpetual_growth_rate,
            (item ->> 'discount_rate')::double precision as discount_rate,
            least((item ->> 'updated_at')::timestamptz, now() + interval '5 minutes') as updated_at,
            ordinal
        from jsonb_array_elements(p_items) with ordinality as element(item, ordinal)
    ),
    latest as (
        select distinct on (parsed.ticker)
            parsed.ticker,
            parsed.stage_1_growth_rate,
            parsed.perpetual_growth_rate,
            parsed.discount_rate,
            parsed.updated_at
        from parsed
        order by parsed.ticker, parsed.updated_at desc, parsed.ordinal desc
    )
    insert into public.valuation_assumptions as saved (
        user_id, ticker, stage_1_growth_rate, perpetual_growth_rate, discount_rate, updated_at
    )
    select
        authenticated_user_id,
        latest.ticker,
        latest.stage_1_growth_rate,
        latest.perpetual_growth_rate,
        latest.discount_rate,
        latest.updated_at
    from latest
    on conflict (user_id, ticker) do update
    set
        stage_1_growth_rate = case when excluded.updated_at >= saved.updated_at then excluded.stage_1_growth_rate else saved.stage_1_growth_rate end,
        perpetual_growth_rate = case when excluded.updated_at >= saved.updated_at then excluded.perpetual_growth_rate else saved.perpetual_growth_rate end,
        discount_rate = case when excluded.updated_at >= saved.updated_at then excluded.discount_rate else saved.discount_rate end,
        updated_at = greatest(saved.updated_at, excluded.updated_at)
    returning saved.*;
end;
$$;

revoke all on function public.merge_valuation_assumptions(jsonb) from public, anon, service_role;
grant execute on function public.merge_valuation_assumptions(jsonb) to authenticated;

comment on table public.valuation_assumptions is
    'User-owned DCF assumptions only. Provider facts and calculated valuation outputs are never persisted here.';
comment on function public.merge_valuation_assumptions(jsonb) is
    'Atomically merges device DCF assumptions into the authenticated user account using latest-updated wins.';
