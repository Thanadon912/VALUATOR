-- Bound authenticated merge RPCs to prevent oversized JSON payloads from
-- consuming unbounded database CPU/memory. Keep ownership enforcement under
-- RLS and preserve the existing conflict semantics.

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
        raise exception 'Authentication is required to merge saved stocks.' using errcode = '42501';
    end if;
    if p_items is null or jsonb_typeof(p_items) <> 'array' then
        raise exception 'p_items must be a JSON array.' using errcode = '22023';
    end if;
    if jsonb_array_length(p_items) > 100 then
        raise exception 'A maximum of 100 saved stocks can be merged at once.' using errcode = '22023';
    end if;
    if exists (
        select 1 from jsonb_array_elements(p_items) as element(item)
        where jsonb_typeof(item) <> 'object'
           or coalesce(jsonb_typeof(item -> 'ticker'), 'null') <> 'string'
           or coalesce(jsonb_typeof(item -> 'added_at'), 'null') <> 'string'
           or coalesce(jsonb_typeof(item -> 'last_visited_at'), 'null') <> 'string'
           or coalesce(jsonb_typeof(item -> 'last_section'), 'null') <> 'string'
    ) then
        raise exception 'Each saved stock must include ticker, added_at, last_visited_at, and last_section strings.' using errcode = '22023';
    end if;

    return query
    with parsed as (
        select
            upper(btrim(item ->> 'ticker')) as ticker,
            least((item ->> 'added_at')::timestamptz, now() + interval '5 minutes') as added_at,
            least((item ->> 'last_visited_at')::timestamptz, now() + interval '5 minutes') as last_visited_at,
            item ->> 'last_section' as last_section,
            ordinal
        from jsonb_array_elements(p_items) with ordinality as element(item, ordinal)
    ),
    aggregated as (
        select
            parsed.ticker,
            min(parsed.added_at) as added_at,
            max(parsed.last_visited_at) as last_visited_at,
            (array_agg(parsed.last_section order by parsed.last_visited_at desc, parsed.ordinal desc))[1] as last_section
        from parsed
        group by parsed.ticker
    )
    insert into public.saved_stocks as saved (
        user_id, ticker, added_at, last_visited_at, last_section
    )
    select
        authenticated_user_id, aggregated.ticker, aggregated.added_at,
        aggregated.last_visited_at, aggregated.last_section
    from aggregated
    on conflict (user_id, ticker) do update
    set
        added_at = least(saved.added_at, excluded.added_at),
        last_section = case when excluded.last_visited_at >= saved.last_visited_at then excluded.last_section else saved.last_section end,
        last_visited_at = greatest(saved.last_visited_at, excluded.last_visited_at)
    returning saved.*;
end;
$$;

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
    if jsonb_array_length(p_items) > 100 then
        raise exception 'A maximum of 100 valuation assumptions can be merged at once.' using errcode = '22023';
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
            parsed.ticker, parsed.stage_1_growth_rate, parsed.perpetual_growth_rate,
            parsed.discount_rate, parsed.updated_at
        from parsed
        order by parsed.ticker, parsed.updated_at desc, parsed.ordinal desc
    )
    insert into public.valuation_assumptions as saved (
        user_id, ticker, stage_1_growth_rate, perpetual_growth_rate, discount_rate, updated_at
    )
    select
        authenticated_user_id, latest.ticker, latest.stage_1_growth_rate,
        latest.perpetual_growth_rate, latest.discount_rate, latest.updated_at
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

revoke all on function public.merge_saved_stocks(jsonb) from public, anon, service_role;
grant execute on function public.merge_saved_stocks(jsonb) to authenticated;
revoke all on function public.merge_valuation_assumptions(jsonb) from public, anon, service_role;
grant execute on function public.merge_valuation_assumptions(jsonb) to authenticated;
