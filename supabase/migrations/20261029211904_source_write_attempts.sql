begin;
set local lock_timeout='2s';

-- Neither dispatch intent nor an observed upload response settles backing bytes.
-- Identity survives Auth, reservation and video metadata; no cascading FKs.
create table public.private_media_write_attempts (
  attempt_id uuid primary key check(attempt_id<>'00000000-0000-0000-0000-000000000000'::uuid),
  user_id uuid not null check(user_id<>'00000000-0000-0000-0000-000000000000'::uuid),
  reservation_id uuid not null unique check(reservation_id<>'00000000-0000-0000-0000-000000000000'::uuid),
  provider text not null default 'supabase' check(provider='supabase'),
  bucket text not null check(bucket ~ '^[a-z0-9][a-z0-9._-]{0,99}$'),
  storage_path text not null check(pg_catalog.length(storage_path) between 1 and 1024),
  content_type text not null check(pg_catalog.length(content_type) between 1 and 100),
  size_bytes bigint not null check(size_bytes>0),
  video_id uuid check(video_id<>'00000000-0000-0000-0000-000000000000'::uuid),
  state text not null default 'dispatching' check(state in ('dispatching','succeeded')),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  observed_at timestamptz,
  unique(bucket,storage_path),
  check((state='dispatching' and observed_at is null) or
        (state='succeeded' and observed_at is not null and pg_catalog.isfinite(observed_at) and observed_at>=created_at))
);
create index private_media_write_attempts_owner_idx on public.private_media_write_attempts(user_id);
create index private_media_write_attempts_video_idx on public.private_media_write_attempts(video_id) where video_id is not null;
alter table public.private_media_write_attempts enable row level security;
revoke all on public.private_media_write_attempts from public,anon,authenticated,service_role;
grant select on public.private_media_write_attempts to service_role;
grant insert(attempt_id,user_id,reservation_id,bucket,storage_path,content_type,size_bytes) on public.private_media_write_attempts to service_role;
grant update(video_id,state,observed_at) on public.private_media_write_attempts to service_role;

create function public.guard_private_media_write_attempt()
returns trigger language plpgsql security invoker set search_path=''
as $$
declare v_r public.upload_reservations%rowtype;
begin
  if tg_op='DELETE' then
    raise exception 'External-write evidence must be retained.' using errcode='55000';
  elsif tg_op='INSERT' then
    if new.state<>'dispatching' or new.observed_at is not null or new.video_id is not null
       or not pg_catalog.isfinite(new.created_at) then
      raise exception 'An external write must begin pending.' using errcode='55000';
    end if;
    perform public.assert_active_private_media_owner(new.user_id);
    select r.* into v_r from public.upload_reservations r where r.id=new.reservation_id for update nowait;
    if not found or v_r.user_id is distinct from new.user_id
       or v_r.blob_path is distinct from new.storage_path or v_r.content_type is distinct from new.content_type
       or v_r.state<>'issued' or v_r.video_id is not null
       or v_r.blob_deleted_at is not null or v_r.cleanup_confirmed_at is not null
       or new.size_bytes>v_r.requested_bytes or not pg_catalog.isfinite(v_r.expires_at)
       or v_r.expires_at<=pg_catalog.clock_timestamp()
       or exists(select 1 from public.videos v where v.upload_reservation_id=new.reservation_id
         or v.storage_path=new.storage_path or v.original_storage_path=new.storage_path)
       or exists(select 1 from public.video_deletion_outbox o where new.storage_path=any(o.storage_paths)) then
      raise exception 'Source reservation is unavailable for dispatch.' using errcode='55000';
    end if;
  else
    if (pg_catalog.to_jsonb(new)-array['video_id','state','observed_at'])
       is distinct from (pg_catalog.to_jsonb(old)-array['video_id','state','observed_at']) then
      raise exception 'External-write identity is immutable.' using errcode='55000';
    end if;
    if new.video_id is distinct from old.video_id then
      if old.video_id is not null or new.video_id is null or new.state is distinct from old.state
         or new.observed_at is distinct from old.observed_at
         or not exists(select 1 from public.videos v where v.id=new.video_id
           and v.user_id=new.user_id and v.upload_reservation_id=new.reservation_id
           and v.storage_path=new.storage_path) then
        raise exception 'Source video association is immutable and must match publication.' using errcode='55000';
      end if;
    elsif not ((new.state=old.state and new.observed_at is not distinct from old.observed_at)
         or (old.state='dispatching' and new.state='succeeded' and new.observed_at is not null
             and pg_catalog.isfinite(new.observed_at) and new.observed_at>=new.created_at
             and new.observed_at<=pg_catalog.clock_timestamp())) then
      raise exception 'An external write cannot clear or reopen its observed outcome.' using errcode='55000';
    end if;
  end if;
  return new;
end;
$$;
revoke all on function public.guard_private_media_write_attempt() from public,anon,authenticated;
grant execute on function public.guard_private_media_write_attempt() to service_role;
create trigger guard_private_media_write_attempt before insert or update or delete on public.private_media_write_attempts
for each row execute function public.guard_private_media_write_attempt();

-- No ON CONFLICT/replay: a lost admission response never authorizes dispatch.
create function public.admit_private_media_source_write(
  p_attempt_id uuid,p_user_id uuid,p_reservation_id uuid,p_bucket text,p_storage_path text,p_content_type text,p_size_bytes bigint
)
returns table(attempt_id uuid,user_id uuid,reservation_id uuid,bucket text,storage_path text,content_type text,size_bytes bigint,state text)
language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$
begin
  perform public.lock_active_private_media_owner(p_user_id,false);
  perform r.id from public.upload_reservations r where r.id=p_reservation_id for update;
  return query insert into public.private_media_write_attempts as a
    (attempt_id,user_id,reservation_id,bucket,storage_path,content_type,size_bytes)
    values(p_attempt_id,p_user_id,p_reservation_id,p_bucket,p_storage_path,p_content_type,p_size_bytes)
    returning a.attempt_id,a.user_id,a.reservation_id,a.bucket,a.storage_path,a.content_type,a.size_bytes,a.state;
end;
$$;
revoke all on function public.admit_private_media_source_write(uuid,uuid,uuid,text,text,text,bigint) from public,anon,authenticated;
grant execute on function public.admit_private_media_source_write(uuid,uuid,uuid,text,text,text,bigint) to service_role;

-- Observations must remain writable after deletion begins or metadata is gone.
create function public.observe_private_media_source_write_success(
  p_attempt_id uuid,p_user_id uuid,p_reservation_id uuid,p_bucket text,p_storage_path text,p_content_type text,p_size_bytes bigint
)
returns boolean language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$
declare v_a public.private_media_write_attempts%rowtype;
begin
  select a.* into v_a from public.private_media_write_attempts a where a.attempt_id=p_attempt_id for update;
  if not found or v_a.user_id is distinct from p_user_id or v_a.reservation_id is distinct from p_reservation_id
     or v_a.bucket is distinct from p_bucket or v_a.storage_path is distinct from p_storage_path
     or v_a.content_type is distinct from p_content_type or v_a.size_bytes is distinct from p_size_bytes then
    return false;
  end if;
  if v_a.state='dispatching' then
    update public.private_media_write_attempts a set state='succeeded',observed_at=pg_catalog.clock_timestamp()
      where a.attempt_id=p_attempt_id;
  end if;
  return true;
end;
$$;
revoke all on function public.observe_private_media_source_write_success(uuid,uuid,uuid,text,text,text,bigint) from public,anon,authenticated;
grant execute on function public.observe_private_media_source_write_success(uuid,uuid,uuid,text,text,text,bigint) to service_role;

-- Persist the source-to-video relation before mutable/FK metadata can disappear.
create function public.bind_private_media_source_video()
returns trigger language plpgsql security invoker set search_path=''
as $$
begin
  if new.upload_reservation_id is null then return new; end if;
  if tg_op='UPDATE' and new.upload_reservation_id is not distinct from old.upload_reservation_id then return new; end if;
  update public.private_media_write_attempts a set video_id=new.id
    where a.reservation_id=new.upload_reservation_id;
  return new;
end;
$$;
revoke all on function public.bind_private_media_source_video() from public,anon,authenticated;
grant execute on function public.bind_private_media_source_video() to service_role;
create trigger bind_private_media_source_video after insert or update of upload_reservation_id on public.videos
for each row execute function public.bind_private_media_source_video();

create function public.private_media_source_write_pending(p_video_id uuid,p_user_id uuid,p_storage_paths text[])
returns boolean language sql stable security invoker set search_path=''
as $$
  select exists(select 1 from public.private_media_write_attempts a where a.user_id=p_user_id
    and (a.video_id=p_video_id or a.storage_path=any(p_storage_paths)
      or exists(select 1 from public.upload_reservations r where r.id=a.reservation_id and r.video_id=p_video_id)));
$$;
revoke all on function public.private_media_source_write_pending(uuid,uuid,text[]) from public,anon,authenticated;
grant execute on function public.private_media_source_write_pending(uuid,uuid,text[]) to service_role;

-- Ordinary Storage DELETE acknowledgement cannot free an unsettled source's quota.
create function public.fence_source_reservation_cleanup()
returns trigger language plpgsql security invoker set search_path=''
as $$
begin
  if (tg_op='DELETE' or new.cleanup_confirmed_at is not null)
     and exists(select 1 from public.private_media_write_attempts a
       where a.reservation_id=old.id or a.storage_path=old.blob_path) then
    raise exception 'Source write settlement is still pending.' using errcode='55000';
  end if;
  if tg_op='DELETE' then return old; end if;
  return new;
end;
$$;
revoke all on function public.fence_source_reservation_cleanup() from public,anon,authenticated;
grant execute on function public.fence_source_reservation_cleanup() to service_role;
create trigger fence_source_reservation_cleanup before update or delete on public.upload_reservations
for each row execute function public.fence_source_reservation_cleanup();

create function public.fence_source_deletion_completion()
returns trigger language plpgsql security invoker set search_path=''
as $$
begin
  if tg_table_name='video_deletion_outbox' then
    if public.private_media_source_write_pending(old.video_id,old.user_id,old.storage_paths) then
      raise exception 'Source write settlement is still pending.' using errcode='55000';
    end if;
    return old;
  end if;
  if new.completed_at is not null and public.private_media_source_write_pending(new.video_id,new.user_id,'{}'::text[]) then
    raise exception 'Source write settlement is still pending.' using errcode='55000';
  end if;
  return new;
end;
$$;
revoke all on function public.fence_source_deletion_completion() from public,anon,authenticated;
grant execute on function public.fence_source_deletion_completion() to service_role;
create trigger fence_source_outbox_completion before delete on public.video_deletion_outbox
for each row execute function public.fence_source_deletion_completion();
create trigger fence_source_saved_completion before update of completed_at on public.saved_lift_deletion_receipts
for each row execute function public.fence_source_deletion_completion();

create or replace function public.complete_video_media_deletion(
  p_video_id uuid,
  p_user_id uuid,
  p_storage_paths text[],
  p_archive_paths text[],
  p_export_prefixes text[],
  p_delete_metadata boolean
)
returns boolean
language plpgsql
security invoker
set search_path = ''
set lock_timeout = '2s'
as $$
declare
  v_video public.videos%rowtype;
  v_task public.video_deletion_outbox%rowtype;
begin
  if p_video_id is null or p_user_id is null or p_storage_paths is null
     or p_archive_paths is null or p_export_prefixes is null
     or p_delete_metadata is null then
    raise exception 'The complete cleanup snapshot is required.' using errcode = '22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('peso:saved-delete:' || p_video_id::text, 58271));
  -- Revocation locks videos before outbox rows. Keep the same order here.
  select * into v_video from public.videos v where v.id = p_video_id for update;
  if found and (v_video.user_id is distinct from p_user_id
      or v_video.discarded_at is null or coalesce(v_video.is_saved, false)
      or v_video.save_state is distinct from 'pending') then
    return false;
  end if;
  perform r.video_id from public.saved_lift_deletion_receipts r
    where r.video_id = p_video_id for update;
  if exists (select 1 from public.saved_lift_deletion_receipts r where r.video_id = p_video_id
      and (r.user_id is distinct from p_user_id or not p_delete_metadata)) then
    return false;
  end if;
  select * into v_task from public.video_deletion_outbox o
    where o.video_id = p_video_id for update;
  if not found or v_task.user_id is distinct from p_user_id
     or v_task.storage_paths is distinct from p_storage_paths
     or v_task.archive_paths is distinct from p_archive_paths
     or v_task.export_prefixes is distinct from p_export_prefixes
     or v_task.delete_metadata is distinct from p_delete_metadata then
    return false;
  end if;
  if public.private_media_source_write_pending(p_video_id,p_user_id,p_storage_paths) then
    return false;
  end if;
  if exists (select 1 from public.analysis_jobs j where j.video_id = p_video_id
             and j.status in ('queued', 'processing', 'retry_wait')) then
    return false;
  end if;

  if p_delete_metadata then
    -- Do not wait on a child writer that might next request our video lock.
    perform j.id from public.analysis_jobs j where j.video_id = p_video_id
      order by j.id for update nowait;
    perform r.id from public.analysis_results r where r.video_id = p_video_id
      order by r.id for update nowait;
    perform r.id from public.upload_reservations r where r.video_id = p_video_id
      order by r.id for update nowait;
    delete from public.analysis_results r where r.video_id = p_video_id;
    delete from public.videos v where v.id = p_video_id and v.user_id = p_user_id;
  end if;
  delete from public.video_deletion_outbox o where o.video_id = p_video_id;
  if p_delete_metadata then
    update public.saved_lift_deletion_receipts r set completed_at = pg_catalog.clock_timestamp()
      where r.video_id = p_video_id and r.user_id = p_user_id and r.completed_at is null;
  end if;
  return true;
end;
$$;
revoke all on function public.complete_video_media_deletion(uuid, uuid, text[], text[], text[], boolean)
  from public, anon, authenticated;
grant execute on function public.complete_video_media_deletion(uuid, uuid, text[], text[], text[], boolean)
  to service_role;

commit;
