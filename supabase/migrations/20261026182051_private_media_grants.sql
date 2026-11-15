begin;

-- The owner row serializes grant issuance, byte authorization and app logout.
create table public.private_media_owners (user_id uuid primary key);
create table public.private_media_session_revocations (
  user_id uuid not null references public.private_media_owners(user_id),
  session_id uuid not null,
  revoked_at timestamptz not null default clock_timestamp(),
  primary key (user_id, session_id)
);
create table public.private_media_logout_events (
  id bigint generated always as identity primary key,
  user_id uuid not null references public.private_media_owners(user_id),
  cutoff timestamptz not null,
  exempt_session_id uuid
);
create index private_media_logout_owner_idx on public.private_media_logout_events(user_id, cutoff desc);
create table public.private_media_grants (
  token_hash text primary key check (token_hash ~ '^[0-9a-f]{64}$'),
  user_id uuid not null references public.private_media_owners(user_id),
  session_id uuid not null,
  resource_kind text not null check (resource_kind in ('video', 'archive')),
  resource_id uuid not null,
  asset_kinds text[] not null,
  expires_at timestamptz not null,
  created_at timestamptz not null default clock_timestamp(),
  revoked_at timestamptz
);
create index private_media_grants_session_idx on public.private_media_grants(user_id, session_id);
create index private_media_grants_expiry_idx on public.private_media_grants(expires_at);
alter table public.private_media_owners enable row level security;
alter table public.private_media_session_revocations enable row level security;
alter table public.private_media_logout_events enable row level security;
alter table public.private_media_grants enable row level security;
revoke all on public.private_media_owners, public.private_media_session_revocations,
  public.private_media_logout_events, public.private_media_grants from public, anon, authenticated;
grant select, insert, update on public.private_media_owners, public.private_media_session_revocations,
  public.private_media_logout_events, public.private_media_grants to service_role;
grant usage, select on sequence public.private_media_logout_events_id_seq to service_role;

create function public.private_media_app_session_is_live(p_user_id uuid, p_session_id uuid)
returns boolean language plpgsql volatile security invoker set search_path = ''
as $$
declare v_cutoff timestamptz;
begin
  if not public.private_media_session_is_live(p_user_id, p_session_id)
     or exists (select 1 from public.private_media_session_revocations r
                where r.user_id = p_user_id and r.session_id = p_session_id) then
    return false;
  end if;
  -- Keep every scope's restriction: a later 'others' cannot undo an earlier
  -- global/local revocation by exempting a previously revoked session.
  select max(e.cutoff) into v_cutoff from public.private_media_logout_events e
    where e.user_id = p_user_id and e.exempt_session_id is distinct from p_session_id;
  if v_cutoff is not null then
    return public.private_media_session_is_live_since(p_user_id, p_session_id, v_cutoff);
  end if;
  return true;
end;
$$;

-- Locks and validates only server-owned resource IDs; no caller Storage paths.
create function public.private_media_resource_video_ids(p_user_id uuid, p_kind text, p_id uuid)
returns uuid[] language plpgsql volatile security invoker set search_path = ''
as $$
declare
  v_ids uuid[];
  v_current uuid[];
  v_archive public.saved_lift_export_jobs%rowtype;
  v_now timestamptz := clock_timestamp();
begin
  if p_user_id is null or p_id is null or p_kind is null
     or p_user_id = '00000000-0000-0000-0000-000000000000'::uuid
     or p_id = '00000000-0000-0000-0000-000000000000'::uuid then return null; end if;
  if p_kind = 'video' then
    v_ids := array[p_id];
  elsif p_kind = 'archive' then
    select e.video_ids into v_ids from public.saved_lift_export_jobs e
      where e.id = p_id and e.user_id = p_user_id;
    if v_ids is null or cardinality(v_ids) not between 1 and 50
       or array_ndims(v_ids) <> 1 or array_position(v_ids, null) is not null
       or (select count(distinct x) from unnest(v_ids) x) <> cardinality(v_ids) then return null; end if;
  else return null;
  end if;
  select array_agg(x order by x) into v_ids from unnest(v_ids) x;
  perform v.id from public.videos v where v.id = any(v_ids) order by v.id for share;
  v_now := clock_timestamp();
  if (select count(*) from public.videos v where v.id = any(v_ids) and v.user_id = p_user_id
       and v.discarded_at is null and v.storage_state is distinct from 'pruned'
       and (v.expires_at is null or (isfinite(v.expires_at) and v.expires_at > v_now))
       and (p_kind = 'video' or (v.save_state = 'saved' and v.is_saved is true))) <> cardinality(v_ids) then
    return null;
  end if;
  if p_kind = 'archive' then
    select e.* into v_archive from public.saved_lift_export_jobs e
      where e.id = p_id and e.user_id = p_user_id for share;
    if not found or v_archive.status <> 'completed' or v_archive.archive_path is null
       or v_archive.expires_at is null or not isfinite(v_archive.expires_at)
       or v_archive.expires_at <= clock_timestamp() then return null; end if;
    select array_agg(x order by x) into v_current from unnest(v_archive.video_ids) x;
    if v_current is distinct from v_ids then return null; end if;
  end if;
  -- A row lock may have waited; wall-clock expiry must be checked at the
  -- completed authorization boundary, not at the start of that wait.
  if exists (select 1 from public.videos v where v.id = any(v_ids)
             and v.expires_at is not null and v.expires_at <= clock_timestamp()) then return null; end if;
  return v_ids;
end;
$$;

create function public.issue_private_media_grant(
  p_user_id uuid, p_session_id uuid, p_token_hash text,
  p_resource_kind text, p_resource_id uuid, p_asset_kinds text[],
  p_jwt_expires_at timestamptz
)
returns table(resource_kind text, resource_id uuid, expires_at timestamptz)
language plpgsql volatile security invoker set search_path = ''
as $$
declare v_expiry timestamptz; v_now timestamptz; v_ids uuid[];
begin
  if p_user_id is null or p_session_id is null or p_token_hash is null
     or p_token_hash !~ '^[0-9a-f]{64}$' or p_jwt_expires_at is null
     or not isfinite(p_jwt_expires_at)
     or p_asset_kinds is null or array_ndims(p_asset_kinds) is distinct from 1
     or cardinality(p_asset_kinds) not between 1 and 6
     or array_position(p_asset_kinds, null) is not null
     or (select count(distinct x) from unnest(p_asset_kinds) x) <> cardinality(p_asset_kinds)
     or p_resource_kind is null or p_resource_kind not in ('video', 'archive')
     or (p_resource_kind = 'video' and not p_asset_kinds <@ array['playback','thumbnail','export:clean','export:pose','export:barbell','export:pose-barbell'])
     or (p_resource_kind = 'archive' and p_asset_kinds <> array['archive']) then
    raise exception 'Invalid media grant request.' using errcode = '22023';
  end if;
  insert into public.private_media_owners(user_id) values(p_user_id) on conflict do nothing;
  perform o.user_id from public.private_media_owners o where o.user_id = p_user_id for update;
  if not public.private_media_app_session_is_live(p_user_id, p_session_id) then
    raise exception 'Media session unavailable.' using errcode = '42501';
  end if;
  v_ids := public.private_media_resource_video_ids(p_user_id, p_resource_kind, p_resource_id);
  if v_ids is null then raise exception 'Media resource unavailable.' using errcode = '42501'; end if;
  if not public.private_media_app_session_is_live(p_user_id, p_session_id) then
    raise exception 'Media session unavailable.' using errcode = '42501';
  end if;
  v_now := clock_timestamp();
  v_expiry := least(p_jwt_expires_at, v_now + interval '5 minutes');
  if v_expiry <= v_now then raise exception 'Media credential expired.' using errcode = '42501'; end if;
  insert into public.private_media_grants(token_hash,user_id,session_id,resource_kind,resource_id,asset_kinds,expires_at)
    values(p_token_hash,p_user_id,p_session_id,p_resource_kind,p_resource_id,p_asset_kinds,v_expiry);
  return query select p_resource_kind, p_resource_id, v_expiry;
end;
$$;

create function public.authorize_private_media_grant(
  p_token_hash text, p_resource_kind text, p_resource_id uuid, p_asset_kind text
)
returns table(user_id uuid, session_id uuid, resource_kind text, resource_id uuid, expires_at timestamptz, video_ids uuid[])
language plpgsql volatile security invoker set search_path = ''
as $$
declare v_grant public.private_media_grants%rowtype; v_ids uuid[];
begin
  if p_token_hash is null or p_token_hash !~ '^[0-9a-f]{64}$' then return; end if;
  select g.* into v_grant from public.private_media_grants g where g.token_hash = p_token_hash;
  if not found then return; end if;
  perform o.user_id from public.private_media_owners o where o.user_id = v_grant.user_id for update;
  -- Re-read after the mutex; logout may have committed while we waited.
  select g.* into v_grant from public.private_media_grants g where g.token_hash = p_token_hash;
  if not found or v_grant.revoked_at is not null or v_grant.expires_at <= clock_timestamp()
     or p_resource_kind is distinct from v_grant.resource_kind or p_resource_id is distinct from v_grant.resource_id
     or p_asset_kind is null or not p_asset_kind = any(v_grant.asset_kinds)
     or not public.private_media_app_session_is_live(v_grant.user_id, v_grant.session_id) then return; end if;
  v_ids := public.private_media_resource_video_ids(v_grant.user_id, v_grant.resource_kind, v_grant.resource_id);
  if v_ids is null or v_grant.expires_at <= clock_timestamp()
     or not public.private_media_app_session_is_live(v_grant.user_id, v_grant.session_id) then return; end if;
  return query select v_grant.user_id, v_grant.session_id, v_grant.resource_kind,
    v_grant.resource_id, v_grant.expires_at, v_ids;
end;
$$;

create function public.revoke_private_media_session(p_user_id uuid, p_session_id uuid, p_scope text)
returns boolean language plpgsql volatile security invoker set search_path = ''
as $$
declare v_now timestamptz;
begin
  if p_scope is null or p_scope not in ('global', 'local', 'others') then
    raise exception 'Invalid media logout scope.' using errcode = '22023';
  end if;
  if p_user_id is null or p_session_id is null then return false; end if;
  insert into public.private_media_owners(user_id) values(p_user_id) on conflict do nothing;
  perform o.user_id from public.private_media_owners o where o.user_id = p_user_id for update;
  if not public.private_media_app_session_is_live(p_user_id, p_session_id) then return false; end if;
  v_now := clock_timestamp();
  if p_scope = 'local' then
    insert into public.private_media_session_revocations(user_id,session_id,revoked_at)
      values(p_user_id,p_session_id,v_now) on conflict do nothing;
  else
    insert into public.private_media_logout_events(user_id,cutoff,exempt_session_id)
      values(p_user_id,v_now,case when p_scope = 'others' then p_session_id else null end);
  end if;
  update public.private_media_grants g set revoked_at = coalesce(g.revoked_at,v_now)
    where g.user_id = p_user_id and (p_scope = 'global' or
      (p_scope = 'local' and g.session_id = p_session_id) or
      (p_scope = 'others' and g.session_id <> p_session_id));
  return true;
end;
$$;

revoke all on function public.private_media_app_session_is_live(uuid,uuid),
  public.private_media_resource_video_ids(uuid,text,uuid),
  public.issue_private_media_grant(uuid,uuid,text,text,uuid,text[],timestamptz),
  public.authorize_private_media_grant(text,text,uuid,text),
  public.revoke_private_media_session(uuid,uuid,text) from public, anon, authenticated;
grant execute on function public.private_media_app_session_is_live(uuid,uuid),
  public.private_media_resource_video_ids(uuid,text,uuid),
  public.issue_private_media_grant(uuid,uuid,text,text,uuid,text[],timestamptz),
  public.authorize_private_media_grant(text,text,uuid,text),
  public.revoke_private_media_session(uuid,uuid,text) to service_role;

commit;
