create table if not exists public.auth_email_rate_limits (
    recipient_digest text not null,
    event_type text not null,
    window_started_at timestamptz not null default now(),
    request_count integer not null default 1,
    updated_at timestamptz not null default now(),
    primary key (recipient_digest, event_type),
    constraint auth_email_rate_limits_digest
        check (recipient_digest ~ '^[0-9a-f]{64}$'),
    constraint auth_email_rate_limits_event_type
        check (event_type in ('signup', 'recovery')),
    constraint auth_email_rate_limits_request_count
        check (request_count between 1 and 1000)
);

alter table public.auth_email_rate_limits enable row level security;

revoke all on table public.auth_email_rate_limits
    from public, anon, authenticated;
grant select, insert, update, delete on table public.auth_email_rate_limits
    to service_role;

create or replace function public.consume_auth_email_rate_limit(
    p_recipient_digest text,
    p_event_type text,
    p_limit integer default 3,
    p_window_seconds integer default 900
)
returns table (allowed boolean, retry_after_seconds integer)
language plpgsql
security invoker
set search_path = ''
as $$
declare
    current_row public.auth_email_rate_limits%rowtype;
    now_at timestamptz := clock_timestamp();
    elapsed_seconds integer;
begin
    if p_recipient_digest !~ '^[0-9a-f]{64}$'
        or p_event_type not in ('signup', 'recovery')
        or p_limit < 1 or p_limit > 100
        or p_window_seconds < 60 or p_window_seconds > 86400 then
        raise exception 'Invalid auth email rate-limit input.'
            using errcode = '22023';
    end if;

    -- Serialize first-use inserts for the same digest/event pair as well as
    -- updates to an existing row.
    perform pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(p_recipient_digest || ':' || p_event_type, 0)
    );

    select * into current_row
    from public.auth_email_rate_limits
    where recipient_digest = p_recipient_digest
      and event_type = p_event_type
    for update;

    if not found then
        insert into public.auth_email_rate_limits (
            recipient_digest, event_type, window_started_at, request_count, updated_at
        ) values (
            p_recipient_digest, p_event_type, now_at, 1, now_at
        );
        return query select true, p_window_seconds;
        return;
    end if;

    elapsed_seconds := greatest(
        0,
        floor(extract(epoch from (now_at - current_row.window_started_at)))::integer
    );
    if elapsed_seconds >= p_window_seconds then
        update public.auth_email_rate_limits
        set window_started_at = now_at, request_count = 1, updated_at = now_at
        where recipient_digest = p_recipient_digest
          and event_type = p_event_type;
        return query select true, p_window_seconds;
    elsif current_row.request_count >= p_limit then
        return query select false, greatest(1, p_window_seconds - elapsed_seconds);
        return;
    end if;

    update public.auth_email_rate_limits
    set request_count = request_count + 1, updated_at = now_at
    where recipient_digest = p_recipient_digest
      and event_type = p_event_type;
    return query select true, greatest(1, p_window_seconds - elapsed_seconds);
end;
$$;

revoke all on function public.consume_auth_email_rate_limit(text, text, integer, integer)
    from public, anon, authenticated;
grant execute on function public.consume_auth_email_rate_limit(text, text, integer, integer)
    to service_role;

comment on table public.auth_email_rate_limits is
    'Server-only fixed-window email quota. Recipient identifiers are HMAC digests; raw emails and IPs are never stored.';
comment on function public.consume_auth_email_rate_limit(text, text, integer, integer) is
    'Atomically consumes the recipient quota shared by all backend instances.';
