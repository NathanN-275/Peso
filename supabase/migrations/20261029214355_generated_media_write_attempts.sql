begin;
set local lock_timeout='2s';

-- Install admission and publication together after old writers have quiesced.
lock table public.videos,public.video_deletion_outbox,public.analysis_jobs in share row exclusive mode nowait;
create table public.private_media_generated_writes (
  attempt_id uuid primary key check(attempt_id<>'00000000-0000-0000-0000-000000000000'::uuid),
  user_id uuid not null check(user_id<>'00000000-0000-0000-0000-000000000000'::uuid),
  video_id uuid not null check(video_id<>'00000000-0000-0000-0000-000000000000'::uuid),
  purpose text not null check(purpose in ('thumbnail','playback','thumbnail_backfill')),
  provider text not null default 'supabase' check(provider='supabase'),
  bucket text not null check(bucket ~ '^[a-z0-9][a-z0-9._-]{0,99}$'),
  storage_path text not null check(pg_catalog.length(storage_path) between 1 and 1024),
  source_path text not null check(pg_catalog.length(source_path) between 1 and 1024),
  content_type text not null check(content_type in ('image/jpeg','video/mp4')),
  size_bytes bigint not null check(size_bytes>0),
  max_user_bytes bigint not null check(max_user_bytes>0),
  max_global_bytes bigint not null check(max_global_bytes>0),
  job_id uuid check(job_id<>'00000000-0000-0000-0000-000000000000'::uuid),
  worker_id text,
  attempt_count integer,
  state text not null default 'dispatching' check(state in ('dispatching','succeeded')),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  observed_at timestamptz,
  unique(bucket,storage_path),
  check((purpose='thumbnail_backfill' and job_id is null and worker_id is null and attempt_count is null)
     or (purpose in ('thumbnail','playback') and job_id is not null and worker_id is not null
       and pg_catalog.btrim(worker_id)<>'' and attempt_count is not null and attempt_count>=1)),
  check((state='dispatching' and observed_at is null) or
     (state='succeeded' and observed_at is not null and pg_catalog.isfinite(observed_at) and observed_at>=created_at))
);
create index private_media_generated_writes_owner_idx on public.private_media_generated_writes(user_id);
create index private_media_generated_writes_video_idx on public.private_media_generated_writes(video_id);
alter table public.private_media_generated_writes enable row level security;
revoke all on public.private_media_generated_writes from public,anon,authenticated,service_role;
grant select on public.private_media_generated_writes to service_role;
grant insert(attempt_id,user_id,video_id,purpose,bucket,storage_path,source_path,content_type,size_bytes,job_id,worker_id,attempt_count,max_user_bytes,max_global_bytes)
  on public.private_media_generated_writes to service_role;
grant update(state,observed_at) on public.private_media_generated_writes to service_role;

-- Direct INSERT/publication already owns a child row: every acquired lock here
-- is nonwaiting. The RPC acquires owner/video authority before its INSERT.
create function public.assert_private_media_generated_write(p_write public.private_media_generated_writes)
returns void language plpgsql security invoker set search_path=''
as $$
declare
  v_video public.videos%rowtype;
  v_job public.analysis_jobs%rowtype;
  v_expected text;
  v_space_chars constant text :=
    U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680'
    || U&'\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000';
begin
  if p_write.attempt_id is null or p_write.attempt_id='00000000-0000-0000-0000-000000000000'::uuid
     or p_write.video_id is null or p_write.video_id='00000000-0000-0000-0000-000000000000'::uuid
     or p_write.purpose is null or p_write.purpose not in ('thumbnail','playback','thumbnail_backfill')
     or p_write.size_bytes is null or p_write.size_bytes<=0 then
    raise exception 'A typed generated-write identity and positive size are required.' using errcode='22023';
  end if;
  v_expected:=case when p_write.purpose='playback'
    then p_write.user_id::text||'/playback/'||p_write.video_id::text||'-'||p_write.attempt_id::text||'-h264-720p-v1.mp4'
    else p_write.user_id::text||'/thumbnails/'||p_write.video_id::text||'-'||p_write.attempt_id::text||'-thumb-v3.jpg' end;
  if p_write.storage_path is distinct from v_expected
     or p_write.content_type is distinct from (case when p_write.purpose='playback' then 'video/mp4' else 'image/jpeg' end)
     or p_write.source_path is null or p_write.source_path=''
     or p_write.source_path<>pg_catalog.btrim(p_write.source_path,v_space_chars)
     or pg_catalog.left(p_write.source_path,pg_catalog.length(p_write.user_id::text)+1)<>p_write.user_id::text||'/'
     or pg_catalog.right(p_write.source_path,1)='/' or pg_catalog.strpos(p_write.source_path,'//')>0
     or pg_catalog.strpos(p_write.source_path,pg_catalog.chr(92))>0 or pg_catalog.strpos(p_write.source_path,'://')>0
     or p_write.source_path ~ '[[:cntrl:]]' or p_write.source_path ~ '(^|/)\.{1,2}(/|$)' then
    raise exception 'Generated-write paths or content type do not match the attempt.' using errcode='22023';
  end if;
  perform public.assert_active_private_media_owner(p_write.user_id);
  select v.* into v_video from public.videos v where v.id=p_write.video_id for update nowait;
  if not found or v_video.user_id is distinct from p_write.user_id
     or v_video.storage_path is distinct from p_write.source_path
     or v_video.discarded_at is not null or v_video.storage_state='pruned'
     or (v_video.expires_at is not null and (not pg_catalog.isfinite(v_video.expires_at)
         or v_video.expires_at<=pg_catalog.clock_timestamp()))
     or exists(select 1 from public.video_deletion_outbox o where o.video_id=p_write.video_id) then
    raise exception 'Generated-write video is unavailable.' using errcode='55000';
  end if;
  if p_write.purpose='thumbnail_backfill' then
    if p_write.job_id is not null or p_write.worker_id is not null or p_write.attempt_count is not null
       or v_video.status is distinct from 'completed'
       or not (coalesce(v_video.save_state='saved',false) or coalesce(v_video.is_saved,false))
       or exists(select 1 from public.analysis_jobs j where j.video_id=p_write.video_id
          and j.status in ('queued','processing','retry_wait')) then
      raise exception 'Saved thumbnail backfill is unavailable.' using errcode='55000';
    end if;
  else
    if p_write.job_id is null or p_write.worker_id is null or pg_catalog.btrim(p_write.worker_id)=''
       or p_write.attempt_count is null or p_write.attempt_count<1 then
      raise exception 'An exact current analysis attempt is required.' using errcode='55000';
    end if;
    select j.* into v_job from public.analysis_jobs j where j.id=p_write.job_id for update nowait;
    if not found or v_job.video_id is distinct from p_write.video_id or v_job.status is distinct from 'processing'
       or v_job.lease_owner is distinct from p_write.worker_id or v_job.attempt_count is distinct from p_write.attempt_count
       or v_job.lease_expires_at is null or not pg_catalog.isfinite(v_job.lease_expires_at)
       or v_job.lease_expires_at<=pg_catalog.clock_timestamp() then
      raise exception 'The analysis attempt is no longer current.' using errcode='55000';
    end if;
  end if;
end;
$$;
revoke all on function public.assert_private_media_generated_write(public.private_media_generated_writes) from public,anon,authenticated;
grant execute on function public.assert_private_media_generated_write(public.private_media_generated_writes) to service_role;

-- Share the source-reservation capacity lock; neither observation settles bytes.
create function public.assert_private_media_generated_capacity(p_write public.private_media_generated_writes)
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
  if v_global_bytes+p_write.size_bytes>p_write.max_global_bytes
     or v_user_bytes+p_write.size_bytes>p_write.max_user_bytes then
    raise exception 'Storage capacity is full.' using errcode='P0001';
  end if;
end;
$$;
revoke all on function public.assert_private_media_generated_capacity(public.private_media_generated_writes) from public,anon,authenticated;
grant execute on function public.assert_private_media_generated_capacity(public.private_media_generated_writes) to service_role;

create function public.guard_private_media_generated_write()
returns trigger language plpgsql security invoker set search_path=''
as $$
begin
  if tg_op='DELETE' then
    raise exception 'Generated-write evidence must be retained.' using errcode='55000';
  elsif tg_op='INSERT' then
    if new.state is distinct from 'dispatching' or new.observed_at is not null
       or not pg_catalog.isfinite(new.created_at) then
      raise exception 'A generated write must begin pending.' using errcode='55000';
    end if;
    perform public.assert_private_media_generated_write(new);
    perform public.assert_private_media_generated_capacity(new);
  else
    if (pg_catalog.to_jsonb(new)-array['state','observed_at'])
       is distinct from (pg_catalog.to_jsonb(old)-array['state','observed_at']) then
      raise exception 'Generated-write identity is immutable.' using errcode='55000';
    end if;
    if not ((new.state=old.state and new.observed_at is not distinct from old.observed_at)
       or (old.state='dispatching' and new.state='succeeded' and new.observed_at is not null
           and pg_catalog.isfinite(new.observed_at) and new.observed_at>=new.created_at
           and new.observed_at<=pg_catalog.clock_timestamp())) then
      raise exception 'A generated write cannot clear or reopen its observed outcome.' using errcode='55000';
    end if;
  end if;
  return new;
end;
$$;
revoke all on function public.guard_private_media_generated_write() from public,anon,authenticated;
grant execute on function public.guard_private_media_generated_write() to service_role;
create trigger guard_private_media_generated_write before insert or update or delete on public.private_media_generated_writes
for each row execute function public.guard_private_media_generated_write();

create function public.admit_private_media_generated_write(
  p_attempt_id uuid,p_user_id uuid,p_video_id uuid,p_purpose text,p_bucket text,p_storage_path text,p_source_path text,
  p_content_type text,p_size_bytes bigint,p_job_id uuid,p_worker_id text,p_attempt_count integer,
  p_max_user_bytes bigint,p_max_global_bytes bigint
)
returns table(attempt_id uuid,user_id uuid,video_id uuid,purpose text,bucket text,storage_path text,source_path text,
  content_type text,size_bytes bigint,job_id uuid,worker_id text,attempt_count integer,state text)
language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$
declare v_video public.videos%rowtype;
begin
  if p_purpose='thumbnail_backfill' then
    perform public.lock_active_private_media_owner(p_user_id,false);
    select v.* into v_video from public.videos v where v.id=p_video_id for update;
  else
    v_video:=public.lock_video_analysis_attempt(p_video_id,p_job_id,p_worker_id,p_attempt_count);
  end if;
  if v_video.id is null or v_video.user_id is distinct from p_user_id then
    raise exception 'Generated-write authority is unavailable.' using errcode='55000';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('peso:upload-capacity',0));
  return query insert into public.private_media_generated_writes as a
    (attempt_id,user_id,video_id,purpose,bucket,storage_path,source_path,content_type,size_bytes,job_id,worker_id,attempt_count,max_user_bytes,max_global_bytes)
    values(p_attempt_id,p_user_id,p_video_id,p_purpose,p_bucket,p_storage_path,p_source_path,p_content_type,p_size_bytes,p_job_id,p_worker_id,p_attempt_count,p_max_user_bytes,p_max_global_bytes)
    returning a.attempt_id,a.user_id,a.video_id,a.purpose,a.bucket,a.storage_path,a.source_path,
      a.content_type,a.size_bytes,a.job_id,a.worker_id,a.attempt_count,a.state;
end;
$$;
revoke all on function public.admit_private_media_generated_write(uuid,uuid,uuid,text,text,text,text,text,bigint,uuid,text,integer,bigint,bigint) from public,anon,authenticated;
grant execute on function public.admit_private_media_generated_write(uuid,uuid,uuid,text,text,text,text,text,bigint,uuid,text,integer,bigint,bigint) to service_role;

create function public.observe_private_media_generated_write_success(
  p_attempt_id uuid,p_user_id uuid,p_video_id uuid,p_purpose text,p_bucket text,p_storage_path text,p_source_path text,
  p_content_type text,p_size_bytes bigint,p_job_id uuid,p_worker_id text,p_attempt_count integer
)
returns boolean language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$
declare v_a public.private_media_generated_writes%rowtype;
begin
  select a.* into v_a from public.private_media_generated_writes a where a.attempt_id=p_attempt_id for update;
  if not found or v_a.user_id is distinct from p_user_id or v_a.video_id is distinct from p_video_id
     or v_a.purpose is distinct from p_purpose or v_a.bucket is distinct from p_bucket
     or v_a.storage_path is distinct from p_storage_path or v_a.source_path is distinct from p_source_path
     or v_a.content_type is distinct from p_content_type or v_a.size_bytes is distinct from p_size_bytes
     or v_a.job_id is distinct from p_job_id or v_a.worker_id is distinct from p_worker_id
     or v_a.attempt_count is distinct from p_attempt_count then
    return false;
  end if;
  if v_a.state='dispatching' then
    update public.private_media_generated_writes a set state='succeeded',observed_at=pg_catalog.clock_timestamp()
      where a.attempt_id=p_attempt_id;
  end if;
  return true;
end;
$$;
revoke all on function public.observe_private_media_generated_write_success(uuid,uuid,uuid,text,text,text,text,text,bigint,uuid,text,integer) from public,anon,authenticated;
grant execute on function public.observe_private_media_generated_write_success(uuid,uuid,uuid,text,text,text,text,text,bigint,uuid,text,integer) to service_role;

-- A path is publishable only by the generation that created and observed it.
-- Unchanged or cleared paths remain usable for revocation and cleanup.
create function public.fence_generated_media_publication()
returns trigger language plpgsql security invoker set search_path=''
as $$
declare v_field text; v_path text; v_a public.private_media_generated_writes%rowtype;
begin
  foreach v_field in array array['thumbnail_path','playback_path'] loop
    v_path:=pg_catalog.to_jsonb(new)->>v_field;
    if v_path is null then continue; end if;
    if tg_op='UPDATE' and v_path is not distinct from (pg_catalog.to_jsonb(old)->>v_field) then continue; end if;
    select a.* into v_a from public.private_media_generated_writes a where a.user_id=new.user_id
      and a.video_id=new.id and a.storage_path=v_path and a.state='succeeded'
      and ((v_field='thumbnail_path' and a.purpose in ('thumbnail','thumbnail_backfill'))
        or (v_field='playback_path' and a.purpose='playback'));
    if not found or new.storage_path is distinct from v_a.source_path
       or new.discarded_at is not null or new.storage_state='pruned'
       or (new.expires_at is not null and (not pg_catalog.isfinite(new.expires_at)
           or new.expires_at<=pg_catalog.clock_timestamp()))
       or (v_a.purpose='thumbnail_backfill' and (new.status is distinct from 'completed'
           or not (coalesce(new.save_state='saved',false) or coalesce(new.is_saved,false)))) then
      raise exception 'Generated media needs a successful current write attempt.' using errcode='55000';
    end if;
    perform public.assert_private_media_generated_write(v_a);
  end loop;
  return new;
end;
$$;
revoke all on function public.fence_generated_media_publication() from public,anon,authenticated;
grant execute on function public.fence_generated_media_publication() to service_role;
create trigger fence_generated_media_publication before insert or update on public.videos
for each row execute function public.fence_generated_media_publication();

-- Both source and generated API observations remain unsettled. Existing video,
-- outbox and Saved receipt guards call this predicate, even after metadata loss.
create or replace function public.private_media_source_write_pending(p_video_id uuid,p_user_id uuid,p_storage_paths text[])
returns boolean language sql stable security invoker set search_path=''
as $$
  select exists(select 1 from public.private_media_write_attempts a where a.user_id=p_user_id
    and (a.video_id=p_video_id or a.storage_path=any(p_storage_paths)
      or exists(select 1 from public.upload_reservations r where r.id=a.reservation_id and r.video_id=p_video_id)))
    or exists(select 1 from public.private_media_generated_writes a where a.user_id=p_user_id
      and (a.video_id=p_video_id or a.storage_path=any(p_storage_paths)));
$$;
revoke all on function public.private_media_source_write_pending(uuid,uuid,text[]) from public,anon,authenticated;
grant execute on function public.private_media_source_write_pending(uuid,uuid,text[]) to service_role;

create or replace function public.revoke_video_media(
  p_user_id uuid,
  p_video_ids uuid[],
  p_delete_metadata boolean default false
)
returns setof public.video_deletion_outbox
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_ids uuid[];
  v_id uuid;
  v_path text;
  v_storage_paths text[];
  v_archive_paths text[];
  v_outbox public.video_deletion_outbox%rowtype;
  v_now timestamptz := pg_catalog.clock_timestamp();
  -- Match Python str.strip at the existing storage-path validation boundary.
  v_space_chars constant text :=
    U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680'
    || U&'\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000';
begin
  if p_user_id is null or p_video_ids is null or p_delete_metadata is null
     or coalesce(pg_catalog.array_ndims(p_video_ids), 0) <> 1
     or pg_catalog.cardinality(p_video_ids) not between 1 and 50
     or pg_catalog.array_position(p_video_ids, null) is not null
     or (select count(distinct id) from pg_catalog.unnest(p_video_ids) as selected(id))
        <> pg_catalog.cardinality(p_video_ids) then
    raise exception 'A distinct selection of 1 to 50 videos and an owner are required.'
      using errcode = '22023';
  end if;
  select pg_catalog.array_agg(id order by id) into v_ids
    from pg_catalog.unnest(p_video_ids) as selected(id);

  -- Queue completion/claim locks job then video. Never wait for a job while
  -- holding video locks: a busy job aborts this transaction for a safe retry.
  perform v.id from public.videos v
    where v.id = any(v_ids) order by v.id for update;
  perform j.id from public.analysis_jobs j
    where j.video_id = any(v_ids) and j.status in ('queued', 'processing', 'retry_wait')
    order by j.id for update nowait;
  -- Archive membership has no video FK. Freeze inserts/path changes while
  -- snapshots are validated; fail fast rather than wait on an archive writer.
  lock table public.saved_lift_export_jobs in share row exclusive mode nowait;
  perform e.id from public.saved_lift_export_jobs e
    where e.user_id = p_user_id and e.video_ids && v_ids
    order by e.id for update nowait;
  perform o.video_id from public.video_deletion_outbox o
    where o.video_id = any(v_ids) order by o.video_id for update;

  -- An owned outbox row permits retries after metadata has already disappeared.
  if exists (
    select 1 from pg_catalog.unnest(v_ids) as selected(id)
    left join public.videos v on v.id = selected.id
    left join public.video_deletion_outbox o on o.video_id = selected.id
    where (v.id is null and o.video_id is null)
       or (v.id is not null and v.user_id is distinct from p_user_id)
       or (o.video_id is not null and o.user_id is distinct from p_user_id)
  ) then
    raise exception 'The complete video selection is unavailable to this owner.'
      using errcode = '42501';
  end if;

  -- Validate the entire selection and all retained snapshots before any write.
  for v_path in
    select p.path from public.videos v
      cross join lateral pg_catalog.unnest(array[
        v.storage_path, v.original_storage_path, v.playback_path, v.thumbnail_path
      ]) as p(path)
      where v.id = any(v_ids) and p.path is not null
    union all
    select a.storage_path from public.private_media_generated_writes a
      where a.user_id=p_user_id and a.video_id=any(v_ids)
    union all
    select p.path from public.video_deletion_outbox o
      cross join lateral pg_catalog.unnest(o.storage_paths || o.archive_paths) as p(path)
      where o.video_id = any(v_ids)
    union all
    select e.archive_path from public.saved_lift_export_jobs e
      where e.user_id = p_user_id and e.video_ids && v_ids and e.archive_path is not null
  loop
    if v_path is null or v_path = '' or v_path <> pg_catalog.btrim(v_path, v_space_chars)
       or pg_catalog.left(v_path, pg_catalog.length(p_user_id::text) + 1) <> p_user_id::text || '/'
       or pg_catalog.right(v_path, 1) = '/' or pg_catalog.strpos(v_path, '//') > 0
       or pg_catalog.strpos(v_path, pg_catalog.chr(92)) > 0
       or pg_catalog.strpos(v_path, '://') > 0 or v_path ~ '[[:cntrl:]]'
       or v_path ~ '(^|/)\.{1,2}(/|$)' then
      raise exception 'Unsafe video cleanup path.' using errcode = '22023';
    end if;
  end loop;
  if exists (
    select 1 from public.video_deletion_outbox o
    cross join lateral pg_catalog.unnest(o.export_prefixes) as p(prefix)
    where o.video_id = any(v_ids)
      and p.prefix is distinct from p_user_id::text || '/exports/' || o.video_id::text || '-'
  ) then
    raise exception 'Unsafe video export cleanup prefix.' using errcode = '22023';
  end if;

  foreach v_id in array v_ids loop
    select coalesce(pg_catalog.array_agg(distinct paths.path order by paths.path), '{}'::text[])
      into v_storage_paths from (
        select p.path from public.videos v
          cross join lateral pg_catalog.unnest(array[
            v.storage_path,v.original_storage_path,v.playback_path,v.thumbnail_path
          ]) as p(path) where v.id=v_id and p.path is not null
        union all
        -- Include every admitted key, including an upload never published.
        select a.storage_path from public.private_media_generated_writes a
          where a.user_id=p_user_id and a.video_id=v_id
      ) as paths;
    select coalesce(pg_catalog.array_agg(distinct paths.path order by paths.path), '{}'::text[])
      into v_archive_paths from (
        select e.archive_path as path from public.saved_lift_export_jobs e
          where e.user_id = p_user_id and v_id = any(e.video_ids) and e.archive_path is not null
        union all
        -- Include the deterministic late-upload name even for queued jobs.
        select p_user_id::text || '/' || e.id::text || '.zip'
          from public.saved_lift_export_jobs e
          where e.user_id = p_user_id and v_id = any(e.video_ids)
      ) as paths;

    insert into public.video_deletion_outbox as existing
      (video_id, user_id, storage_paths, archive_paths, export_prefixes, delete_metadata)
    values (v_id, p_user_id, v_storage_paths, v_archive_paths,
      array[p_user_id::text || '/exports/' || v_id::text || '-'], p_delete_metadata)
    on conflict (video_id) do update set
      storage_paths = array(select distinct p.path from pg_catalog.unnest(
        existing.storage_paths || excluded.storage_paths) as p(path) order by p.path),
      archive_paths = array(select distinct p.path from pg_catalog.unnest(
        existing.archive_paths || excluded.archive_paths) as p(path) order by p.path),
      export_prefixes = array(select distinct p.prefix from pg_catalog.unnest(
        existing.export_prefixes || excluded.export_prefixes) as p(prefix) order by p.prefix),
      delete_metadata = existing.delete_metadata or excluded.delete_metadata
    where existing.user_id = excluded.user_id
    returning existing.* into v_outbox;
    if not found then
      raise exception 'Video cleanup ownership changed.' using errcode = '42501';
    end if;
  end loop;

  update public.videos v
    set discarded_at = coalesce(v.discarded_at, v_now), is_saved = false,
        save_state = 'pending', expires_at = null
    where v.id = any(v_ids) and v.user_id = p_user_id;
  update public.analysis_jobs j
    set status = 'cancelled', stage = 'failed', stage_started_at = v_now,
        stage_timestamps = j.stage_timestamps || pg_catalog.jsonb_build_object('failed', v_now),
        last_heartbeat_at = v_now, lease_owner = null, lease_expires_at = null,
        failure_class = 'video_revoked', completed_at = v_now
    where j.video_id = any(v_ids) and j.status in ('queued', 'processing', 'retry_wait');
  update public.saved_lift_export_jobs e
    set status = 'expired', archive_path = null, failure_code = 'video_revoked',
        expires_at = least(coalesce(e.expires_at, v_now), v_now)
    where e.user_id = p_user_id and e.video_ids && v_ids;

  return query select o.* from public.video_deletion_outbox o
    where o.video_id = any(v_ids) and o.user_id = p_user_id order by o.video_id;
end;
$$;
revoke all on function public.revoke_video_media(uuid, uuid[], boolean) from public, anon, authenticated;
grant execute on function public.revoke_video_media(uuid, uuid[], boolean) to service_role;

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


create or replace function public.claim_expired_video_deletion(p_video_id uuid)
returns setof public.video_deletion_outbox
language plpgsql security invoker set search_path = ''
as $$
declare
  v_video public.videos%rowtype;
  v_paths text[];
begin
  -- Saving updates this same row. Whichever transaction locks first wins;
  -- a completed save is rechecked before any record or object is removed.
  select * into v_video from public.videos where id = p_video_id for update;
  if not found then return; end if;
  if v_video.save_state is distinct from 'pending' or v_video.expires_at is null
     or v_video.expires_at > now() then return; end if;
  if coalesce((to_jsonb(v_video)->>'is_saved')::boolean, false) then return; end if;
  -- Queue recovery, not retention, owns stale/retry work. Never interrupt an
  -- accepted job based on the video's updated_at timestamp.
  if exists (select 1 from public.analysis_jobs where video_id = p_video_id
             and status in ('queued', 'processing', 'retry_wait')) then return; end if;
  select pg_catalog.array_agg(distinct path) into v_paths from (
    select path from pg_catalog.unnest(array[
      v_video.storage_path,pg_catalog.to_jsonb(v_video)->>'original_storage_path',
      pg_catalog.to_jsonb(v_video)->>'playback_path',pg_catalog.to_jsonb(v_video)->>'thumbnail_path'
    ]) path where path is not null and path<>''
    union all
    select a.storage_path from public.private_media_generated_writes a
      where a.video_id=v_video.id and a.user_id=v_video.user_id
  ) paths;
  if v_paths is null or exists (
    select 1 from unnest(v_paths) path
    where path not like v_video.user_id::text || '/%'
       or path like '%/../%' or path like '%/./%'
  ) then raise exception 'Unsafe retention storage path'; end if;
  insert into public.video_deletion_outbox(video_id, user_id, storage_paths)
    values (v_video.id, v_video.user_id, v_paths);
  -- The established analysis_results and analysis_jobs FKs cascade. Explicit
  -- result deletion also supports older installations without that cascade.
  delete from public.analysis_results where video_id = p_video_id;
  delete from public.videos where id = p_video_id;
  return query select * from public.video_deletion_outbox where video_id = p_video_id;
end;
$$;
revoke execute on function public.claim_expired_video_deletion(uuid) from public, anon, authenticated;
grant execute on function public.claim_expired_video_deletion(uuid) to service_role;

commit;
