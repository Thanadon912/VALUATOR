create table if not exists public.auth_email_deliveries (
    user_id uuid not null references auth.users (id) on delete cascade,
    event_type text not null,
    status text not null default 'pending',
    attempt_count integer not null default 1,
    provider_message_id text,
    claimed_at timestamptz not null default now(),
    sent_at timestamptz,
    updated_at timestamptz not null default now(),
    primary key (user_id, event_type),
    constraint auth_email_deliveries_event_type
        check (event_type in ('welcome')),
    constraint auth_email_deliveries_status
        check (status in ('pending', 'sent', 'failed', 'suppressed')),
    constraint auth_email_deliveries_attempt_count
        check (attempt_count between 1 and 20)
);

alter table public.auth_email_deliveries enable row level security;

revoke all on table public.auth_email_deliveries
    from public, anon, authenticated;
grant select, insert, update, delete on table public.auth_email_deliveries
    to service_role;

-- Existing accounts must not receive a delayed welcome email after rollout.
insert into public.auth_email_deliveries (
    user_id,
    event_type,
    status,
    attempt_count,
    claimed_at,
    updated_at
)
select id, 'welcome', 'suppressed', 1, now(), now()
from auth.users
on conflict (user_id, event_type) do nothing;

create or replace function public.claim_auth_email_delivery(
    p_user_id uuid,
    p_event_type text
)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
    claimed boolean := false;
begin
    if p_event_type <> 'welcome' then
        raise exception 'Unsupported email event type.'
            using errcode = '22023';
    end if;

    insert into public.auth_email_deliveries as delivery (
        user_id,
        event_type,
        status,
        attempt_count,
        claimed_at,
        updated_at
    )
    values (p_user_id, p_event_type, 'pending', 1, now(), now())
    on conflict (user_id, event_type) do update
    set
        status = 'pending',
        attempt_count = delivery.attempt_count + 1,
        provider_message_id = null,
        claimed_at = now(),
        updated_at = now()
    where (
        delivery.status = 'failed'
        or (
            delivery.status = 'pending'
            and delivery.claimed_at < now() - interval '10 minutes'
        )
    )
    and delivery.attempt_count < 20
    returning true into claimed;

    return coalesce(claimed, false);
end;
$$;

revoke all on function public.claim_auth_email_delivery(uuid, text)
    from public, anon, authenticated;
grant execute on function public.claim_auth_email_delivery(uuid, text)
    to service_role;

comment on table public.auth_email_deliveries is
    'Server-only delivery ledger. It stores no recipient address or authentication token.';
comment on function public.claim_auth_email_delivery(uuid, text) is
    'Atomically claims a welcome email, retrying only failed or stale pending deliveries.';
