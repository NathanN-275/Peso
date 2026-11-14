begin;
set local lock_timeout='2s';
lock table public.profiles in share row exclusive mode nowait;

-- A random revision identifies every profile generation, including same-value
-- edits. No caller can restore an old revision to re-authorize a stale picture.
alter table public.profiles add column profile_revision uuid not null default pg_catalog.gen_random_uuid()
  check(profile_revision<>'00000000-0000-0000-0000-000000000000'::uuid);
create function public.rotate_profile_revision()
returns trigger language plpgsql security invoker set search_path=''
as $$ begin new.profile_revision:=pg_catalog.gen_random_uuid(); return new; end; $$;
revoke all on function public.rotate_profile_revision() from public,anon;
grant execute on function public.rotate_profile_revision() to authenticated,service_role;
create trigger rotate_profile_revision before insert or update on public.profiles
for each row execute function public.rotate_profile_revision();
grant select,insert,update on public.profiles to service_role;

-- Owner/profile work has its own retained ledger, without artificial video IDs
-- or cascading metadata/Auth/session FKs. Capacity remains shared with lift media.
create table public.private_media_avatar_writes (
  attempt_id uuid primary key check(attempt_id<>'00000000-0000-0000-0000-000000000000'::uuid),
  user_id uuid not null check(user_id<>'00000000-0000-0000-0000-000000000000'::uuid),
  session_id uuid not null check(session_id<>'00000000-0000-0000-0000-000000000000'::uuid),
  provider text not null default 'supabase' check(provider='supabase'),
  bucket text not null default 'profile-avatars' check(bucket='profile-avatars'),
  storage_path text not null unique,
  content_type text not null default 'image/jpeg' check(content_type='image/jpeg'),
  size_bytes bigint not null check(size_bytes between 1 and 524288),
  content_sha256 text not null check(content_sha256 ~ '^[0-9a-f]{64}$'),
  profile_revision uuid check(profile_revision<>'00000000-0000-0000-0000-000000000000'::uuid),
  previous_avatar_path text check(previous_avatar_path is null or pg_catalog.length(previous_avatar_path) between 1 and 1024),
  max_user_bytes bigint not null check(max_user_bytes>0),
  max_global_bytes bigint not null check(max_global_bytes>0),
  state text not null default 'dispatching' check(state in ('dispatching','succeeded')),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  observed_at timestamptz,
  published_at timestamptz,
  published_username text,
  published_display_name text,
  check(storage_path=user_id::text||'/avatar-'||attempt_id::text||'.jpg'),
  check(profile_revision is not null or previous_avatar_path is null),
  check((state='dispatching' and observed_at is null) or
    (state='succeeded' and observed_at is not null and pg_catalog.isfinite(observed_at) and observed_at>=created_at)),
  check((published_at is null and published_username is null and published_display_name is null) or
    (state='succeeded' and published_at is not null and pg_catalog.isfinite(published_at) and published_at>=observed_at)),
  check(published_username is null or published_username ~ '^[A-Za-z0-9_]{3,30}$'),
  check(published_display_name is null or pg_catalog.char_length(published_display_name)<=80)
);
create index private_media_avatar_writes_owner_idx on public.private_media_avatar_writes(user_id);
alter table public.private_media_avatar_writes enable row level security;
revoke all on public.private_media_avatar_writes from public,anon,authenticated,service_role;
grant select on public.private_media_avatar_writes to service_role;
grant insert(attempt_id,user_id,session_id,storage_path,size_bytes,content_sha256,profile_revision,previous_avatar_path,max_user_bytes,max_global_bytes)
  on public.private_media_avatar_writes to service_role;
grant update(state,observed_at,published_at,published_username,published_display_name)
  on public.private_media_avatar_writes to service_role;

create function public.lock_private_media_profile(p_user_id uuid,p_session_id uuid)
returns jsonb language plpgsql security invoker set search_path=''
as $$ declare v_profile public.profiles%rowtype; begin
  perform public.assert_active_private_media_owner(p_user_id);
  if not public.private_media_app_session_is_live(p_user_id,p_session_id) then
    raise exception 'Profile session is unavailable.' using errcode='42501'; end if;
  select p.* into v_profile from public.profiles p where p.id=p_user_id for update nowait;
  if not found then return null; end if;
  return pg_catalog.to_jsonb(v_profile);
end; $$;

create function public.assert_private_media_avatar_write(p_write public.private_media_avatar_writes)
returns void language plpgsql security invoker set search_path=''
as $$ declare v_profile jsonb; begin
  v_profile:=public.lock_private_media_profile(p_write.user_id,p_write.session_id);
  if p_write.profile_revision is distinct from (v_profile->>'profile_revision')::uuid
     or p_write.previous_avatar_path is distinct from v_profile->>'avatar_path' then
    raise exception 'The profile changed before avatar publication.' using errcode='55000'; end if;
end; $$;

create function public.guard_private_media_avatar_write()
returns trigger language plpgsql security invoker set search_path=''
as $$ declare v_capacity public.private_media_generated_writes%rowtype; begin
  if tg_op='DELETE' then raise exception 'Avatar write evidence must be retained.' using errcode='55000'; end if;
  if tg_op='INSERT' then
    if new.state is distinct from 'dispatching' or new.observed_at is not null or new.published_at is not null
       or new.published_username is not null or new.published_display_name is not null
       or not pg_catalog.isfinite(new.created_at) or new.created_at>pg_catalog.clock_timestamp() then
      raise exception 'Avatar writes must begin pending.' using errcode='55000'; end if;
    perform public.assert_private_media_avatar_write(new);
    if not exists(select 1 from public.upload_admission_control c where c.id=1 and c.enabled) then
      raise exception 'New media uploads are paused.' using errcode='P0002'; end if;
    v_capacity.user_id:=new.user_id;v_capacity.size_bytes:=new.size_bytes;
    v_capacity.max_user_bytes:=new.max_user_bytes;v_capacity.max_global_bytes:=new.max_global_bytes;
    perform public.assert_private_media_generated_capacity(v_capacity);
  else
    if (pg_catalog.to_jsonb(new)-array['state','observed_at','published_at','published_username','published_display_name'])
      is distinct from (pg_catalog.to_jsonb(old)-array['state','observed_at','published_at','published_username','published_display_name']) then
      raise exception 'Avatar write identity is immutable.' using errcode='55000'; end if;
    if not ((new.state=old.state and new.observed_at is not distinct from old.observed_at)
      or (old.state='dispatching' and new.state='succeeded' and new.observed_at is not null
        and pg_catalog.isfinite(new.observed_at) and new.observed_at>=new.created_at
        and new.observed_at<=pg_catalog.clock_timestamp())) then
      raise exception 'Avatar outcome cannot clear or reopen.' using errcode='55000'; end if;
    if new.published_at is distinct from old.published_at
       or new.published_username is distinct from old.published_username
       or new.published_display_name is distinct from old.published_display_name then
      if old.published_at is not null or old.state is distinct from 'succeeded' or new.state is distinct from old.state
         or new.observed_at is distinct from old.observed_at or new.published_at is null
         or not pg_catalog.isfinite(new.published_at) or new.published_at<new.observed_at
         or new.published_at>pg_catalog.clock_timestamp() then
        raise exception 'Avatar publication cannot clear, rebind or combine outcomes.' using errcode='55000'; end if;
      perform public.assert_private_media_avatar_write(new);
    end if;
  end if;
  return new;
end; $$;
revoke all on function public.guard_private_media_avatar_write() from public,anon,authenticated;
grant execute on function public.guard_private_media_avatar_write() to service_role;
create trigger guard_private_media_avatar_write before insert or update or delete on public.private_media_avatar_writes
for each row execute function public.guard_private_media_avatar_write();

create function public.admit_private_media_avatar_write(
  p_attempt_id uuid,p_user_id uuid,p_session_id uuid,p_profile_revision uuid,p_size_bytes bigint,p_content_sha256 text,
  p_max_user_bytes bigint,p_max_global_bytes bigint
)
returns jsonb language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$ declare v_profile jsonb;v_write public.private_media_avatar_writes%rowtype; begin
  v_profile:=public.lock_private_media_profile(p_user_id,p_session_id);
  if p_profile_revision is distinct from (v_profile->>'profile_revision')::uuid then
    raise exception 'The profile changed before avatar upload.' using errcode='55000'; end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('peso:upload-capacity',0));
  insert into public.private_media_avatar_writes as a
    (attempt_id,user_id,session_id,storage_path,size_bytes,content_sha256,profile_revision,previous_avatar_path,max_user_bytes,max_global_bytes)
    values(p_attempt_id,p_user_id,p_session_id,p_user_id::text||'/avatar-'||p_attempt_id::text||'.jpg',
      p_size_bytes,p_content_sha256,p_profile_revision,v_profile->>'avatar_path',p_max_user_bytes,p_max_global_bytes)
    returning a.* into v_write;
  return pg_catalog.to_jsonb(v_write);
end; $$;

create function public.observe_private_media_avatar_write_success(
  p_attempt_id uuid,p_user_id uuid,p_session_id uuid,p_bucket text,p_storage_path text,p_content_type text,p_size_bytes bigint,p_content_sha256 text
)
returns boolean language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$ declare v_write public.private_media_avatar_writes%rowtype; begin
  select a.* into v_write from public.private_media_avatar_writes a where a.attempt_id=p_attempt_id for update;
  if not found or v_write.user_id is distinct from p_user_id or v_write.session_id is distinct from p_session_id
     or v_write.bucket is distinct from p_bucket or v_write.storage_path is distinct from p_storage_path
     or v_write.content_type is distinct from p_content_type or v_write.size_bytes is distinct from p_size_bytes
     or v_write.content_sha256 is distinct from p_content_sha256 then return false; end if;
  if v_write.state='dispatching' then
    update public.private_media_avatar_writes a set state='succeeded',observed_at=pg_catalog.clock_timestamp()
      where a.attempt_id=p_attempt_id;
  end if;
  return true;
end; $$;

create function public.fence_profile_avatar_publication()
returns trigger language plpgsql security invoker set search_path=''
as $$ declare v_write public.private_media_avatar_writes%rowtype; begin
  if new.avatar_path is null then return new; end if;
  if tg_op='UPDATE' and new.avatar_path is not distinct from old.avatar_path then return new; end if;
  if current_user='authenticated' then
    raise exception 'Avatar publication requires its backend write attempt.' using errcode='55000'; end if;
  select a.* into v_write from public.private_media_avatar_writes a
    where a.user_id=new.id and a.storage_path=new.avatar_path and a.state='succeeded' and a.published_at is not null;
  if not found then raise exception 'Avatar publication requires an observed attempt.' using errcode='55000'; end if;
  perform public.assert_private_media_avatar_write(v_write);
  if new.username is distinct from v_write.published_username or new.display_name is distinct from v_write.published_display_name then
    raise exception 'Avatar profile fields do not match publication.' using errcode='55000'; end if;
  return new;
end; $$;
revoke all on function public.fence_profile_avatar_publication() from public,anon;
grant execute on function public.fence_profile_avatar_publication() to authenticated,service_role;
create trigger fence_profile_avatar_publication before insert or update on public.profiles
for each row execute function public.fence_profile_avatar_publication();

create function public.save_private_media_profile(p_user_id uuid,p_session_id uuid,p_profile_revision uuid,p_username text,p_display_name text)
returns jsonb language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$ declare v_current jsonb;v_profile public.profiles%rowtype; begin
  v_current:=public.lock_private_media_profile(p_user_id,p_session_id);
  if p_profile_revision is distinct from (v_current->>'profile_revision')::uuid then
    raise exception 'The profile changed before saving.' using errcode='55000'; end if;
  if v_current is null then
    insert into public.profiles as p(id,username,display_name) values(p_user_id,p_username,p_display_name) returning p.* into v_profile;
  else
    update public.profiles p set username=p_username,display_name=p_display_name where p.id=p_user_id returning p.* into v_profile;
  end if;
  return pg_catalog.to_jsonb(v_profile);
end; $$;

create function public.publish_private_media_avatar(p_attempt_id uuid,p_user_id uuid,p_session_id uuid,p_username text,p_display_name text)
returns jsonb language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$ declare v_current jsonb;v_profile public.profiles%rowtype;v_write public.private_media_avatar_writes%rowtype; begin
  v_current:=public.lock_private_media_profile(p_user_id,p_session_id);
  select a.* into v_write from public.private_media_avatar_writes a where a.attempt_id=p_attempt_id for update nowait;
  if not found or v_write.user_id is distinct from p_user_id or v_write.session_id is distinct from p_session_id
     or v_write.state is distinct from 'succeeded' then
    raise exception 'Avatar upload observation is unavailable.' using errcode='55000'; end if;
  if v_write.published_at is not null then
    if v_current is null or v_current->>'avatar_path' is distinct from v_write.storage_path
       or v_write.published_username is distinct from p_username or v_write.published_display_name is distinct from p_display_name then
      raise exception 'Avatar publication cannot be rebound or repeated after replacement.' using errcode='55000'; end if;
    return v_current;
  end if;
  perform public.assert_private_media_avatar_write(v_write);
  update public.private_media_avatar_writes a set published_at=pg_catalog.clock_timestamp(),
    published_username=p_username,published_display_name=p_display_name where a.attempt_id=p_attempt_id;
  if v_current is null then
    insert into public.profiles as p(id,username,display_name,avatar_path)
      values(p_user_id,p_username,p_display_name,v_write.storage_path) returning p.* into v_profile;
  else
    update public.profiles p set username=p_username,display_name=p_display_name,avatar_path=v_write.storage_path
      where p.id=p_user_id returning p.* into v_profile;
  end if;
  return pg_catalog.to_jsonb(v_profile);
end; $$;

create function public.private_media_avatar_write_pending(p_user_id uuid)
returns boolean language sql stable security invoker set search_path=''
as $$ select exists(select 1 from public.private_media_avatar_writes a where a.user_id=p_user_id); $$;

-- Retire direct client avatar writes in the same release as the replacement
-- producer. These restrictive policies cannot authorize or be OR-bypassed.
create policy avatar_backend_insert_only on storage.objects as restrictive
  for insert to authenticated with check(bucket_id<>'profile-avatars');
create policy avatar_backend_update_only on storage.objects as restrictive
  for update to authenticated using(bucket_id<>'profile-avatars') with check(bucket_id<>'profile-avatars');
create policy avatar_backend_delete_only on storage.objects as restrictive
  for delete to authenticated using(bucket_id<>'profile-avatars');


create or replace function public.assert_private_media_generated_capacity(p_write public.private_media_generated_writes)
returns void language plpgsql security invoker set search_path=''
as $$
declare v_user_bytes numeric; v_global_bytes numeric;
begin
  if p_write.max_user_bytes is null or p_write.max_user_bytes<=0
     or p_write.max_global_bytes is null or p_write.max_global_bytes<=0 then
    raise exception 'Configured generated-write capacity limits are required.' using errcode='22023';
  end if;
  if not pg_catalog.pg_try_advisory_xact_lock(pg_catalog.hashtextextended('peso:upload-capacity',0)) then
    raise exception 'Storage capacity admission is busy.' using errcode='55P03';
  end if;
  select coalesce(sum(coalesce(r.actual_bytes,r.requested_bytes)),0),
    coalesce(sum(coalesce(r.actual_bytes,r.requested_bytes)) filter(where r.user_id=p_write.user_id),0)
    into v_global_bytes,v_user_bytes from public.upload_reservations r where r.cleanup_confirmed_at is null;
  select v_global_bytes+coalesce(sum(a.size_bytes),0),
    v_user_bytes+coalesce(sum(a.size_bytes) filter(where a.user_id=p_write.user_id),0)
    into v_global_bytes,v_user_bytes from public.private_media_generated_writes a;
  select v_global_bytes+coalesce(sum(a.size_bytes),0),
    v_user_bytes+coalesce(sum(a.size_bytes) filter(where a.user_id=p_write.user_id),0)
    into v_global_bytes,v_user_bytes from public.private_media_avatar_writes a;
  if v_global_bytes+p_write.size_bytes>p_write.max_global_bytes
     or v_user_bytes+p_write.size_bytes>p_write.max_user_bytes then
    raise exception 'Storage capacity is full.' using errcode='P0001';
  end if;
end;
$$;

create or replace function public.reserve_video_upload(
  p_reservation_id uuid,
  p_user_id uuid,
  p_blob_path text,
  p_file_name text,
  p_content_type text,
  p_requested_bytes bigint,
  p_expires_at timestamptz,
  p_source_type text,
  p_exercise_type text,
  p_view_type text,
  p_client_duration_ms integer,
  p_tracking_setup jsonb,
  p_max_user_active integer,
  p_max_user_bytes bigint,
  p_max_global_active integer,
  p_max_global_bytes bigint,
  p_max_user_hourly integer
)
returns setof public.upload_reservations
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_user_count bigint;
  v_user_bytes bigint;
  v_global_count bigint;
  v_global_bytes bigint;
begin
  perform public.lock_active_private_media_owner(p_user_id, true);
  if p_requested_bytes <= 0 or p_expires_at is null or not pg_catalog.isfinite(p_expires_at) or p_expires_at <= pg_catalog.clock_timestamp()
    or p_expires_at > pg_catalog.clock_timestamp() + interval '15 minutes'
    or least(p_max_user_active, p_max_global_active, p_max_user_bytes, p_max_global_bytes, p_max_user_hourly) <= 0 then
    raise exception 'Invalid reservation limits.' using errcode = '22023';
  end if;

  -- One transaction lock serializes both user and global admission across API replicas.
  -- Expired but not-yet-deleted blobs still consume bytes until cleanup confirms deletion.
  perform pg_advisory_xact_lock(hashtextextended('peso:upload-capacity', 0));
  if p_expires_at <= pg_catalog.clock_timestamp() then
    raise exception 'Reservation expired while awaiting admission.' using errcode='22023';
  end if;
  if not exists (select 1 from public.upload_admission_control where id = 1 and enabled) then
    raise exception 'Upload admission is disabled.' using errcode = 'P0002';
  end if;
  select
    count(*) filter (where state = 'verified' or (state in ('issued', 'uploaded') and expires_at > pg_catalog.clock_timestamp())),
    coalesce(sum(coalesce(actual_bytes, requested_bytes)) filter (where cleanup_confirmed_at is null), 0),
    count(*) filter (where user_id = p_user_id and (state = 'verified' or (state in ('issued', 'uploaded') and expires_at > pg_catalog.clock_timestamp()))),
    coalesce(sum(coalesce(actual_bytes, requested_bytes)) filter (where user_id = p_user_id and cleanup_confirmed_at is null), 0)
  into v_global_count, v_global_bytes, v_user_count, v_user_bytes
  from public.upload_reservations;
  -- All generated attempts remain charged until a supported settlement exists.
  select v_global_bytes+coalesce(sum(a.size_bytes),0),
    v_user_bytes+coalesce(sum(a.size_bytes) filter(where a.user_id=p_user_id),0)
    into v_global_bytes,v_user_bytes from public.private_media_generated_writes a;

  select v_global_bytes+coalesce(sum(a.size_bytes),0),
    v_user_bytes+coalesce(sum(a.size_bytes) filter(where a.user_id=p_user_id),0)
    into v_global_bytes,v_user_bytes from public.private_media_avatar_writes a;

  if v_user_count >= p_max_user_active or v_user_bytes + p_requested_bytes > p_max_user_bytes
    or v_global_count >= p_max_global_active or v_global_bytes + p_requested_bytes > p_max_global_bytes
    or (select count(*) from public.upload_reservations where user_id = p_user_id and created_at > pg_catalog.clock_timestamp() - interval '1 hour') >= p_max_user_hourly then
    raise exception 'Upload capacity is full.' using errcode = 'P0001';
  end if;

  return query insert into public.upload_reservations (
    id, user_id, blob_path, file_name, content_type, requested_bytes, expires_at,
    source_type, exercise_type, view_type, client_duration_ms, tracking_setup
  ) values (
    p_reservation_id, p_user_id, p_blob_path, p_file_name, p_content_type,
    p_requested_bytes, p_expires_at, p_source_type, p_exercise_type,
    p_view_type, p_client_duration_ms, p_tracking_setup
  ) returning *;
end;
$$;

create function public.read_private_media_profile(p_user_id uuid,p_session_id uuid)
returns jsonb language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$ begin return public.lock_private_media_profile(p_user_id,p_session_id); end; $$;

revoke all on function public.lock_private_media_profile(uuid,uuid) from public,anon,authenticated;
grant execute on function public.lock_private_media_profile(uuid,uuid) to service_role;

revoke all on function public.assert_private_media_avatar_write(public.private_media_avatar_writes) from public,anon,authenticated;
grant execute on function public.assert_private_media_avatar_write(public.private_media_avatar_writes) to service_role;

revoke all on function public.admit_private_media_avatar_write(uuid,uuid,uuid,uuid,bigint,text,bigint,bigint) from public,anon,authenticated;
grant execute on function public.admit_private_media_avatar_write(uuid,uuid,uuid,uuid,bigint,text,bigint,bigint) to service_role;

revoke all on function public.observe_private_media_avatar_write_success(uuid,uuid,uuid,text,text,text,bigint,text) from public,anon,authenticated;
grant execute on function public.observe_private_media_avatar_write_success(uuid,uuid,uuid,text,text,text,bigint,text) to service_role;

revoke all on function public.save_private_media_profile(uuid,uuid,uuid,text,text) from public,anon,authenticated;
grant execute on function public.save_private_media_profile(uuid,uuid,uuid,text,text) to service_role;

revoke all on function public.publish_private_media_avatar(uuid,uuid,uuid,text,text) from public,anon,authenticated;
grant execute on function public.publish_private_media_avatar(uuid,uuid,uuid,text,text) to service_role;

revoke all on function public.private_media_avatar_write_pending(uuid) from public,anon,authenticated;
grant execute on function public.private_media_avatar_write_pending(uuid) to service_role;

revoke all on function public.read_private_media_profile(uuid,uuid) from public,anon,authenticated;
grant execute on function public.read_private_media_profile(uuid,uuid) to service_role;

commit;
