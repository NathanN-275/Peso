begin;

-- Keep every historical grant for exact-path logout cleanup; avatar revisions
-- are profile generations and are never interpreted as video identifiers.
alter table public.private_media_grants drop constraint private_media_grants_resource_kind_check;
alter table public.private_media_grants add constraint private_media_grants_resource_kind_check
  check(resource_kind in ('video','archive','avatar'));

create function public.private_media_current_avatar(
  p_user_id uuid,p_session_id uuid,p_resource_id uuid,p_report_legacy boolean default false
)
returns public.private_media_avatar_writes
language plpgsql volatile security invoker set search_path='' set lock_timeout='2s'
as $$
declare v_profile public.profiles%rowtype;v_write public.private_media_avatar_writes%rowtype;
begin
  if p_user_id is null or p_session_id is null or p_resource_id is null or p_report_legacy is null
     or p_user_id='00000000-0000-0000-0000-000000000000'::uuid
     or p_session_id='00000000-0000-0000-0000-000000000000'::uuid
     or p_resource_id='00000000-0000-0000-0000-000000000000'::uuid then
    raise exception 'Invalid avatar request.' using errcode='22023'; end if;
  perform public.lock_active_private_media_owner(p_user_id,false);
  if not public.private_media_app_session_is_live(p_user_id,p_session_id) then
    raise exception 'Avatar session unavailable.' using errcode='42501'; end if;
  select p.* into v_profile from public.profiles p where p.id=p_user_id for share;
  if not found or v_profile.profile_revision is distinct from p_resource_id
     or v_profile.avatar_path is null then
    raise exception 'Avatar unavailable.' using errcode='42501'; end if;
  -- Legacy classification is only about this live owner's current safe pointer.
  -- It is not permission to serve old bytes or fabricate retained provenance.
  if pg_catalog.length(v_profile.avatar_path) not between 1 and 1024
     or pg_catalog.split_part(v_profile.avatar_path,'/',1)<>p_user_id::text
     or pg_catalog.strpos(v_profile.avatar_path,'/')=0
     or v_profile.avatar_path ~ '[[:cntrl:]]'
     or pg_catalog.strpos(v_profile.avatar_path,pg_catalog.chr(92))>0
     or exists(select 1 from pg_catalog.unnest(pg_catalog.string_to_array(v_profile.avatar_path,'/')) x
               where x in ('','.','..')) then
    raise exception 'Avatar unavailable.' using errcode='42501'; end if;
  select a.* into v_write from public.private_media_avatar_writes a where a.storage_path=v_profile.avatar_path;
  if not found then
    if not public.private_media_app_session_is_live(p_user_id,p_session_id) then
      raise exception 'Avatar session unavailable.' using errcode='42501'; end if;
    if p_report_legacy then
      raise exception 'Avatar reupload required.' using errcode='P0002'; end if;
    raise exception 'Avatar unavailable.' using errcode='42501';
  end if;
  if v_write.user_id is distinct from p_user_id or v_write.provider is distinct from 'supabase'
     or v_write.bucket is distinct from 'profile-avatars' or v_write.content_type is distinct from 'image/jpeg'
     or v_write.state is distinct from 'succeeded' or v_write.attempt_id is null
     or v_write.attempt_id='00000000-0000-0000-0000-000000000000'::uuid
     or v_write.storage_path is distinct from p_user_id::text||'/avatar-'||v_write.attempt_id::text||'.jpg'
     or v_write.size_bytes is null or v_write.size_bytes not between 1 and 524288
     or v_write.content_sha256 is null or v_write.content_sha256 !~ '^[0-9a-f]{64}$'
     or v_write.published_at is null or not pg_catalog.isfinite(v_write.published_at)
     or v_write.observed_at is null or not pg_catalog.isfinite(v_write.observed_at)
     or v_write.published_at<v_write.observed_at or v_write.published_at>pg_catalog.clock_timestamp()
     or not public.private_media_app_session_is_live(p_user_id,p_session_id) then
    raise exception 'Avatar unavailable.' using errcode='42501'; end if;
  return v_write;
end;
$$;
revoke all on function public.private_media_current_avatar(uuid,uuid,uuid,boolean) from public,anon,authenticated;
grant execute on function public.private_media_current_avatar(uuid,uuid,uuid,boolean) to service_role;

create function public.issue_private_media_avatar_grant(
  p_user_id uuid,p_session_id uuid,p_token_hash text,p_resource_id uuid,p_jwt_expires_at timestamptz
)
returns table(resource_kind text,resource_id uuid,expires_at timestamptz)
language plpgsql volatile security invoker set search_path='' set lock_timeout='2s'
as $$
declare v_write public.private_media_avatar_writes%rowtype;v_now timestamptz;v_expiry timestamptz;
begin
  if p_token_hash is null or p_token_hash !~ '^[0-9a-f]{64}$'
     or p_jwt_expires_at is null or not pg_catalog.isfinite(p_jwt_expires_at) then
    raise exception 'Invalid avatar grant request.' using errcode='22023'; end if;
  if p_jwt_expires_at<=pg_catalog.clock_timestamp() then
    raise exception 'Avatar credential expired.' using errcode='42501'; end if;
  begin
    v_write:=public.private_media_current_avatar(p_user_id,p_session_id,p_resource_id,true);
  exception when no_data_found then
    -- A profile/owner lock may have outlived the captured JWT even for legacy.
    if p_jwt_expires_at<=pg_catalog.clock_timestamp() then
      raise exception 'Avatar credential expired.' using errcode='42501'; end if;
    raise;
  end;
  v_now:=pg_catalog.clock_timestamp();v_expiry:=least(p_jwt_expires_at,v_now+interval '5 minutes');
  if v_expiry<=v_now or not public.private_media_app_session_is_live(p_user_id,p_session_id) then
    raise exception 'Avatar credential expired.' using errcode='42501'; end if;
  insert into public.private_media_grants(token_hash,user_id,session_id,resource_kind,resource_id,asset_kinds,expires_at)
    values(p_token_hash,p_user_id,p_session_id,'avatar',p_resource_id,array['avatar'],v_expiry);
  return query select 'avatar'::text,p_resource_id,v_expiry;
end;
$$;
revoke all on function public.issue_private_media_avatar_grant(uuid,uuid,text,uuid,timestamptz) from public,anon,authenticated;
grant execute on function public.issue_private_media_avatar_grant(uuid,uuid,text,uuid,timestamptz) to service_role;

create function public.authorize_private_media_avatar_grant(p_token_hash text,p_resource_id uuid)
returns table(user_id uuid,session_id uuid,resource_kind text,resource_id uuid,expires_at timestamptz,
  attempt_id uuid,provider text,bucket text,storage_path text,content_type text,size_bytes bigint,
  content_sha256 text,published_at timestamptz)
language plpgsql volatile security invoker set search_path='' set lock_timeout='2s'
as $$
declare v_grant public.private_media_grants%rowtype;v_write public.private_media_avatar_writes%rowtype;
begin
  if p_token_hash is null or p_token_hash !~ '^[0-9a-f]{64}$' or p_resource_id is null
     or p_resource_id='00000000-0000-0000-0000-000000000000'::uuid then return; end if;
  select g.* into v_grant from public.private_media_grants g where g.token_hash=p_token_hash;
  if not found then return; end if;
  -- Acquire the same owner-first mutex as publication/logout, then re-read grant.
  begin
    perform public.lock_active_private_media_owner(v_grant.user_id,false);
  exception when object_not_in_prerequisite_state then return;
  end;
  select g.* into v_grant from public.private_media_grants g where g.token_hash=p_token_hash;
  if not found or v_grant.revoked_at is not null or not pg_catalog.isfinite(v_grant.expires_at)
     or v_grant.expires_at<=pg_catalog.clock_timestamp()
     or v_grant.resource_kind is distinct from 'avatar' or v_grant.resource_id is distinct from p_resource_id
     or v_grant.asset_kinds is distinct from array['avatar'] then return; end if;
  begin
    v_write:=public.private_media_current_avatar(v_grant.user_id,v_grant.session_id,p_resource_id,false);
  exception when insufficient_privilege or object_not_in_prerequisite_state then return;
  end;
  if v_grant.expires_at<=pg_catalog.clock_timestamp()
     or not public.private_media_app_session_is_live(v_grant.user_id,v_grant.session_id) then return; end if;
  return query select v_grant.user_id,v_grant.session_id,'avatar'::text,v_grant.resource_id,v_grant.expires_at,
    v_write.attempt_id,v_write.provider,v_write.bucket,v_write.storage_path,v_write.content_type,
    v_write.size_bytes,v_write.content_sha256,v_write.published_at;
end;
$$;
revoke all on function public.authorize_private_media_avatar_grant(text,uuid) from public,anon,authenticated;
grant execute on function public.authorize_private_media_avatar_grant(text,uuid) to service_role;

create or replace function public.private_media_session_cookie_paths(
  p_user_id uuid,p_session_id uuid,p_after_kind text,p_after_id uuid
)
returns table(resource_kind text,resource_id uuid)
language plpgsql volatile security invoker set search_path=''
as $$
begin
  if p_user_id is null or p_user_id='00000000-0000-0000-0000-000000000000'::uuid
     or p_session_id='00000000-0000-0000-0000-000000000000'::uuid
     or (p_after_kind is null)<>(p_after_id is null)
     or (p_after_kind is not null and p_after_kind not in ('archive','avatar','video'))
     or p_after_id='00000000-0000-0000-0000-000000000000'::uuid then
    raise exception 'Invalid media cookie inventory request.' using errcode='22023'; end if;
  perform o.user_id from public.private_media_owners o where o.user_id=p_user_id for share;
  return query select distinct g.resource_kind,g.resource_id from public.private_media_grants g
    where g.user_id=p_user_id and (p_session_id is null or g.session_id=p_session_id)
      and (p_after_kind is null or (g.resource_kind,g.resource_id)>(p_after_kind,p_after_id))
    order by g.resource_kind,g.resource_id limit 33;
end;
$$;
revoke all on function public.private_media_session_cookie_paths(uuid,uuid,text,uuid) from public,anon,authenticated;
grant execute on function public.private_media_session_cookie_paths(uuid,uuid,text,uuid) to service_role;

-- Deny new SDK reads/signing only for avatars. This does not revoke already
-- issued bearer URLs; preserved legacy objects require separate retirement.
create policy avatar_backend_select_only on storage.objects as restrictive
for select to authenticated using(bucket_id<>'profile-avatars');

commit;
