begin;

-- This is an attested application policy, not a reader of live Auth configuration.
-- Activation and expiry require a separate reviewed provider-policy binding.
create table public.private_media_provider_policy (
  singleton boolean primary key default true check (singleton),
  enabled boolean not null default false,
  auth_version text,
  auth_source_commit text,
  timebox_seconds bigint,
  inactivity_timeout_seconds bigint,
  single_per_user boolean,
  allow_low_aal_seconds bigint,
  refresh_rotation_enabled boolean,
  refresh_reuse_interval_seconds integer,
  refresh_allow_reuse boolean,
  refresh_token_algorithm_version integer,
  refresh_token_upgrade_percentage integer,
  verified_at timestamptz,
  verified_until timestamptz
);
alter table public.private_media_provider_policy owner to postgres;
alter table public.private_media_provider_policy enable row level security;
revoke all on public.private_media_provider_policy from public, anon, authenticated, service_role;
insert into public.private_media_provider_policy (singleton) values (true);

create function public.private_media_session_is_live(p_user_id uuid, p_session_id uuid)
returns boolean
language plpgsql
volatile
security definer
set search_path = ''
as $$
declare
  v_now timestamptz := pg_catalog.clock_timestamp();
  v_live boolean;
begin
  if p_user_id is null or p_session_id is null
     or p_user_id = '00000000-0000-0000-0000-000000000000'::uuid
     or p_session_id = '00000000-0000-0000-0000-000000000000'::uuid then
    return false;
  end if;

  if not exists (
    select 1 from public.private_media_provider_policy as p
    where p.singleton and p.enabled
      and p.auth_version = 'v2.197.0'
      and p.auth_source_commit = '4eee58f296d9698a1c2c0ae14d7a0b379c7622d3'
      and p.timebox_seconds = 0 and p.inactivity_timeout_seconds = 0
      and p.single_per_user is false and p.allow_low_aal_seconds = 0
      and p.refresh_rotation_enabled is true
      and p.refresh_reuse_interval_seconds = 10 and p.refresh_allow_reuse is false
      and p.refresh_token_algorithm_version in (0, 1, 2)
      and p.refresh_token_upgrade_percentage between 0 and 100
      and pg_catalog.isfinite(p.verified_at) and pg_catalog.isfinite(p.verified_until)
      and p.verified_at <= v_now and p.verified_until > v_now
      and p.verified_until > p.verified_at
  ) then
    return false;
  end if;

  select (
    u.instance_id = '00000000-0000-0000-0000-000000000000'::uuid
    and u.deleted_at is null
    and (u.banned_until is null or (pg_catalog.isfinite(u.banned_until) and u.banned_until <= v_now))
    and u.aud = 'authenticated' and u.role = 'authenticated'
    and u.is_anonymous is false
    and pg_catalog.isfinite(s.created_at) and s.created_at <= v_now
    and (s.not_after is null or (pg_catalog.isfinite(s.not_after) and s.not_after > v_now))
    and (s.aal is null or s.aal in ('aal1', 'aal2'))
    -- OAuth-client sessions need additional client/grant validation; unsupported here.
    and s.oauth_client_id is null and s.scopes is null
    and case
      when s.refresh_token_counter is null and s.refresh_token_hmac_key is null then
        exists (
          select 1 from auth.refresh_tokens as r
          where r.session_id = s.id and r.user_id::text = p_user_id::text
            and r.instance_id = '00000000-0000-0000-0000-000000000000'::uuid
            and r.revoked is false
        )
      when s.refresh_token_counter is not null and s.refresh_token_hmac_key is not null then
        -- V2 and upgraded sessions need no active legacy row. This is not key validation.
        s.refresh_token_counter >= 0 and s.refresh_token_counter < 9223372036854775807
          and pg_catalog.length(s.refresh_token_hmac_key) > 0
      else false
    end
  ) into v_live
  from auth.sessions as s
  join auth.users as u on u.id = s.user_id
  where s.id = p_session_id and s.user_id = p_user_id;

  return v_live is true;
exception when others then
  -- Missing/changed schema, privilege failures and unreadable state never authorize media.
  return false;
end;
$$;
alter function public.private_media_session_is_live(uuid, uuid) owner to postgres;
revoke all on function public.private_media_session_is_live(uuid, uuid) from public, anon, authenticated;
grant execute on function public.private_media_session_is_live(uuid, uuid) to service_role;

comment on function public.private_media_session_is_live(uuid, uuid) is
  'Service-only provider revocation-state check for the explicitly attested Auth v2.197.0 policy. Disabled until binding; does not authenticate a JWT, prove refresh-token usability, detect external version/config drift, or replace app media/session revocation.';

-- A boolean cutoff seam for app-owned global/other-session logout. No Auth
-- timestamps or rows are returned to the service client.
create function public.private_media_session_is_live_since(
  p_user_id uuid, p_session_id uuid, p_created_after timestamptz
)
returns boolean
language plpgsql volatile security definer set search_path = ''
as $$
begin
  if p_created_after is null or not pg_catalog.isfinite(p_created_after)
     or not public.private_media_session_is_live(p_user_id, p_session_id) then
    return false;
  end if;
  return exists (
    select 1 from auth.sessions s
    where s.id = p_session_id and s.user_id = p_user_id
      and s.created_at > p_created_after
  );
exception when others then
  return false;
end;
$$;
alter function public.private_media_session_is_live_since(uuid, uuid, timestamptz) owner to postgres;
revoke all on function public.private_media_session_is_live_since(uuid, uuid, timestamptz)
  from public, anon, authenticated;
grant execute on function public.private_media_session_is_live_since(uuid, uuid, timestamptz) to service_role;

commit;
