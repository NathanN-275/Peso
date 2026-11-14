begin;
set local lock_timeout='2s';
lock table public.videos,public.analysis_results,public.saved_lift_export_jobs,
  public.private_media_generated_writes in share row exclusive mode nowait;

alter table public.private_media_generated_writes
  alter column video_id drop not null,
  alter column source_path drop not null,
  add column archive_job_id uuid,
  add column archive_attempt_count integer,
  add column archive_started_at timestamptz,
  add column video_ids uuid[],
  add column member_snapshots jsonb,
  add column content_sha256 text;
alter table public.private_media_generated_writes
  drop constraint generated_purpose_check,
  drop constraint generated_lease_check,
  drop constraint generated_export_snapshot_check,
  drop constraint generated_export_publication_check,
  drop constraint private_media_generated_writes_content_type_check;
alter table public.private_media_generated_writes
  add constraint generated_purpose_check check(purpose in ('thumbnail','playback','thumbnail_backfill','analyzed_export','archive')),
  add constraint generated_lease_check check(
    (purpose in ('thumbnail_backfill','analyzed_export','archive') and job_id is null and worker_id is null and attempt_count is null)
    or (purpose in ('thumbnail','playback') and job_id is not null and worker_id is not null
      and pg_catalog.btrim(worker_id)<>'' and attempt_count is not null and attempt_count>=1)),
  add constraint generated_export_snapshot_check check(
    (purpose='analyzed_export' and analysis_id is not null and analysis_id<>'00000000-0000-0000-0000-000000000000'::uuid
      and analysis_model_version is not null and pg_catalog.btrim(analysis_model_version)<>''
      and analysis_snapshot_hash is not null and analysis_snapshot_hash ~ '^[0-9a-f]{64}$'
      and variant is not null and variant in ('pose','barbell','pose-barbell') and content_type='video/mp4')
    or (purpose<>'analyzed_export' and analysis_id is null and analysis_model_version is null
      and analysis_snapshot_hash is null and variant is null)),
  add constraint generated_export_publication_check check(
    (published_at is null and cache_expires_at is null)
    or (purpose in ('analyzed_export','archive') and state='succeeded' and published_at is not null
      and cache_expires_at is not null and pg_catalog.isfinite(published_at)
      and pg_catalog.isfinite(cache_expires_at) and published_at>=created_at and cache_expires_at>published_at)),
  add constraint generated_archive_identity_check check(
    (purpose='archive' and video_id is null and source_path is null and content_type='application/zip'
      and archive_job_id is not null and archive_job_id<>'00000000-0000-0000-0000-000000000000'::uuid
      and archive_attempt_count is not null and archive_attempt_count>=1
      and archive_started_at is not null and pg_catalog.isfinite(archive_started_at)
      and video_ids is not null and pg_catalog.array_ndims(video_ids)=1
      and pg_catalog.cardinality(video_ids) between 1 and 50
      and pg_catalog.array_position(video_ids,null) is null
      and member_snapshots is not null and pg_catalog.jsonb_typeof(member_snapshots)='array'
      and content_sha256 is not null and content_sha256 ~ '^[0-9a-f]{64}$')
    or (purpose<>'archive' and video_id is not null and source_path is not null
      and archive_job_id is null and archive_attempt_count is null and archive_started_at is null
      and video_ids is null and member_snapshots is null and content_sha256 is null)),
  add constraint generated_content_type_check check(content_type in ('image/jpeg','video/mp4','application/zip'));
create unique index private_media_generated_writes_archive_generation_idx on public.private_media_generated_writes(archive_job_id,archive_attempt_count,archive_started_at) where purpose='archive';
create index private_media_generated_writes_archive_job_idx on public.private_media_generated_writes(archive_job_id) where purpose='archive';
create index private_media_generated_writes_selection_idx on public.private_media_generated_writes using gin(video_ids) where purpose='archive';
grant insert(archive_job_id,archive_attempt_count,archive_started_at,video_ids,member_snapshots,content_sha256)
  on public.private_media_generated_writes to service_role;

-- Compact plan: hold all member rows before the child archive row. A trigger
-- already owns its child; every additional resource lock is nonwaiting.
create function public.plan_private_media_archive(p_user_id uuid,p_archive_job_id uuid)
returns jsonb language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$
declare v_job public.saved_lift_export_jobs%rowtype; v_ids uuid[]; v_id uuid; v_current jsonb;
  v_members jsonb:='[]'; v_result jsonb; v_pose boolean; v_barbell boolean; v_variant text;
  v_exercise text; v_extension text; v_index integer:=0;
begin
  perform public.assert_active_private_media_owner(p_user_id);
  select e.video_ids into v_ids from public.saved_lift_export_jobs e
    where e.id=p_archive_job_id and e.user_id=p_user_id;
  if not found then raise exception 'Archive job is unavailable.' using errcode='55000'; end if;
  perform v.id from public.videos v where v.id=any(v_ids) order by v.id for update nowait;
  select e.* into v_job from public.saved_lift_export_jobs e where e.id=p_archive_job_id for update nowait;
  if not found or v_job.user_id is distinct from p_user_id or v_job.video_ids is distinct from v_ids
     or v_job.status is distinct from 'processing' or v_job.attempts<1
     or v_job.started_at is null or not pg_catalog.isfinite(v_job.started_at)
     or v_job.started_at>pg_catalog.clock_timestamp()
     or coalesce(pg_catalog.array_ndims(v_ids),0)<>1 or pg_catalog.cardinality(v_ids) not between 1 and 50
     or pg_catalog.array_position(v_ids,null) is not null
     or (select count(distinct id) from pg_catalog.unnest(v_ids) selected(id))<>pg_catalog.cardinality(v_ids) then
    raise exception 'Archive generation is unavailable.' using errcode='55000';
  end if;
  foreach v_id in array v_ids loop
    v_current:=public.lock_private_media_export_resource(p_user_id,v_id);
    v_result:=v_current->'result_json';
    v_pose:=case when pg_catalog.jsonb_typeof(v_result->'poseFrames')='array'
      then pg_catalog.jsonb_array_length(v_result->'poseFrames')>0 else false end;
    v_barbell:=case when v_result#>'{barbellPath,available}'='true'::jsonb
      and pg_catalog.jsonb_typeof(v_result#>'{barbellPath,points}')='array'
      then pg_catalog.jsonb_array_length(v_result#>'{barbellPath,points}')>=2 else false end;
    v_variant:=case when v_pose and v_barbell then 'pose-barbell' when v_pose then 'pose'
      when v_barbell then 'barbell' else 'clean' end;
    select pg_catalog.btrim(pg_catalog.regexp_replace(pg_catalog.lower(
      coalesce(pg_catalog.to_jsonb(v)->>'exercise_type','saved-lift')),'[^a-z0-9]+','-','g'),'-')
      into v_exercise from public.videos v where v.id=v_id;
    v_exercise:=coalesce(nullif(v_exercise,''),'saved-lift');
    v_extension:=case when v_variant<>'clean' then 'mp4'
      else pg_catalog.lower(pg_catalog.substring(v_current->>'source_path','\.([^.\/]+)$')) end;
    if v_extension is null or v_extension not in ('mp4','mov','m4v','webm') then
      raise exception 'Archive source format is unavailable.' using errcode='55000';
    end if;
    v_index:=v_index+1;
    v_members:=v_members||pg_catalog.jsonb_build_array(
      (v_current-'result_json')||pg_catalog.jsonb_build_object('video_id',v_id,'variant',v_variant,
        'entry_name',pg_catalog.lpad(v_index::text,2,'0')||'-'||v_exercise||'-'||v_id::text||'.'||v_extension));
  end loop;
  if exists(select 1 from public.videos v where v.id=any(v_ids) and v.expires_at is not null
    and v.expires_at<=pg_catalog.clock_timestamp()) then
    raise exception 'Archive member expired while planning.' using errcode='55000'; end if;
  return pg_catalog.jsonb_build_object('user_id',p_user_id,'archive_job_id',p_archive_job_id,
    'archive_attempt_count',v_job.attempts,'archive_started_at',v_job.started_at,'video_ids',v_ids,
    'member_snapshots',v_members);
end;
$$;

create function public.assert_private_media_archive_write(p_write public.private_media_generated_writes)
returns void language plpgsql security invoker set search_path=''
as $$
declare v_plan jsonb; v_expected jsonb; v_member jsonb; v_index integer:=0; v_size bigint;
begin
  v_plan:=public.plan_private_media_archive(p_write.user_id,p_write.archive_job_id);
  if p_write.purpose is distinct from 'archive' or p_write.bucket is distinct from 'saved-lift-exports'
     or p_write.content_type is distinct from 'application/zip'
     or p_write.storage_path is distinct from p_write.user_id::text||'/'||p_write.archive_job_id::text||'-'||p_write.attempt_id::text||'.zip'
     or p_write.archive_attempt_count is distinct from (v_plan->>'archive_attempt_count')::integer
     or p_write.archive_started_at is distinct from (v_plan->>'archive_started_at')::timestamptz
     or pg_catalog.to_jsonb(p_write.video_ids) is distinct from v_plan->'video_ids'
     or pg_catalog.jsonb_typeof(p_write.member_snapshots) is distinct from 'array'
     or pg_catalog.jsonb_array_length(p_write.member_snapshots)<>pg_catalog.cardinality(p_write.video_ids) then
    raise exception 'Archive write does not match its generation and selection.' using errcode='55000';
  end if;
  for v_member in select x from pg_catalog.jsonb_array_elements(p_write.member_snapshots) x loop
    v_expected:=v_plan->'member_snapshots'->v_index;
    if pg_catalog.jsonb_typeof(v_member) is distinct from 'object'
       or (v_member-array['artifact_bucket','artifact_path','artifact_size_bytes','artifact_sha256']) is distinct from v_expected
       or pg_catalog.jsonb_typeof(v_member->'artifact_bucket') is distinct from 'string'
       or (v_member->>'artifact_bucket') !~ '^[a-z0-9][a-z0-9._-]{0,99}$'
       or pg_catalog.jsonb_typeof(v_member->'artifact_path') is distinct from 'string'
       or pg_catalog.jsonb_typeof(v_member->'artifact_size_bytes') is distinct from 'number'
       or (v_member->>'artifact_size_bytes') !~ '^[1-9][0-9]*$'
       or pg_catalog.jsonb_typeof(v_member->'artifact_sha256') is distinct from 'string'
       or (v_member->>'artifact_sha256') !~ '^[0-9a-f]{64}$' then
      raise exception 'Archive member snapshot is malformed or stale.' using errcode='55000';
    end if;
    v_size:=(v_member->>'artifact_size_bytes')::bigint;
    if v_expected->>'variant'='clean' then
      if v_member->>'artifact_path' is distinct from v_expected->>'source_path' then
        raise exception 'Clean archive member source changed.' using errcode='55000';
      end if;
    elsif not exists(select 1 from public.private_media_generated_writes a
      where a.purpose='analyzed_export' and a.user_id=p_write.user_id and a.bucket=v_member->>'artifact_bucket'
        and a.video_id=(v_expected->>'video_id')::uuid
        and a.storage_path=v_member->>'artifact_path' and a.state='succeeded' and a.published_at is not null
        and a.source_path=v_expected->>'source_path' and a.analysis_id=(v_expected->>'analysis_id')::uuid
        and a.analysis_model_version=v_expected->>'analysis_model_version'
        and a.analysis_snapshot_hash=v_expected->>'analysis_snapshot_hash' and a.variant=v_expected->>'variant'
        and a.size_bytes=v_size) then
      raise exception 'Archive member needs its observed published export generation.' using errcode='55000';
    end if;
    v_index:=v_index+1;
  end loop;
end;
$$;

create function public.private_media_archive_receipt(p_write public.private_media_generated_writes)
returns jsonb language sql security invoker set search_path=''
as $$ select pg_catalog.jsonb_build_object(
  'attempt_id',p_write.attempt_id,'user_id',p_write.user_id,'purpose',p_write.purpose,
  'bucket',p_write.bucket,'storage_path',p_write.storage_path,'content_type',p_write.content_type,
  'size_bytes',p_write.size_bytes,'archive_job_id',p_write.archive_job_id,
  'archive_attempt_count',p_write.archive_attempt_count,'archive_started_at',p_write.archive_started_at,
  'video_ids',p_write.video_ids,'member_snapshots',p_write.member_snapshots,'content_sha256',p_write.content_sha256,
  'state',p_write.state,'created_at',p_write.created_at,'published_at',p_write.published_at,'cache_expires_at',p_write.cache_expires_at
); $$;

create function public.admit_private_media_archive_write(
  p_attempt_id uuid,p_user_id uuid,p_archive_job_id uuid,p_archive_attempt_count integer,p_archive_started_at timestamptz,
  p_video_ids uuid[],p_member_snapshots jsonb,p_bucket text,p_storage_path text,p_size_bytes bigint,p_content_sha256 text,
  p_max_user_bytes bigint,p_max_global_bytes bigint
)
returns jsonb language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$ declare v_write public.private_media_generated_writes%rowtype; begin
  perform public.plan_private_media_archive(p_user_id,p_archive_job_id);
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('peso:upload-capacity',0));
  insert into public.private_media_generated_writes as a
    (attempt_id,user_id,purpose,bucket,storage_path,content_type,size_bytes,
     archive_job_id,archive_attempt_count,archive_started_at,video_ids,member_snapshots,content_sha256,max_user_bytes,max_global_bytes)
    values(p_attempt_id,p_user_id,'archive',p_bucket,p_storage_path,'application/zip',p_size_bytes,
      p_archive_job_id,p_archive_attempt_count,p_archive_started_at,p_video_ids,p_member_snapshots,p_content_sha256,p_max_user_bytes,p_max_global_bytes)
    returning a.* into v_write;
  return public.private_media_archive_receipt(v_write);
end; $$;

create function public.publish_private_media_archive(p_attempt_id uuid,p_user_id uuid,p_cache_ttl_seconds integer)
returns jsonb language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$
declare v_job uuid; v_write public.private_media_generated_writes%rowtype; v_now timestamptz;
begin
  if p_cache_ttl_seconds is null or p_cache_ttl_seconds<=0 then
    raise exception 'A positive configured cache lifetime is required.' using errcode='22023'; end if;
  select a.archive_job_id into v_job from public.private_media_generated_writes a
    where a.attempt_id=p_attempt_id and a.user_id=p_user_id and a.purpose='archive';
  if not found then raise exception 'Archive write is unavailable.' using errcode='55000'; end if;
  -- An idempotent replay cannot extend the original lifetime. It still locks
  -- all selected member rows, owner and job through the resource/grant boundary.
  select a.* into v_write from public.private_media_generated_writes a where a.attempt_id=p_attempt_id;
  if v_write.published_at is not null then
    perform public.assert_active_private_media_owner(p_user_id);
    if public.private_media_resource_video_ids(p_user_id,'archive',v_job) is null then
      raise exception 'Archive resource is unavailable.' using errcode='55000'; end if;
    if not exists(select 1 from public.saved_lift_export_jobs e where e.id=v_job and e.user_id=p_user_id
      and e.status='completed' and e.archive_path=v_write.storage_path
      and e.completed_at=v_write.published_at and e.expires_at=v_write.cache_expires_at) then
      raise exception 'Archive publication is unavailable.' using errcode='55000'; end if;
    return public.private_media_archive_receipt(v_write);
  end if;
  perform public.plan_private_media_archive(p_user_id,v_job);
  select a.* into v_write from public.private_media_generated_writes a where a.attempt_id=p_attempt_id for update nowait;
  if v_write.user_id is distinct from p_user_id or v_write.purpose is distinct from 'archive'
     or v_write.state is distinct from 'succeeded' or v_write.published_at is not null then
    raise exception 'Archive upload observation is unavailable.' using errcode='55000'; end if;
  perform public.assert_private_media_archive_write(v_write);
  v_now:=pg_catalog.clock_timestamp();
  update public.private_media_generated_writes a set published_at=v_now,
    cache_expires_at=v_write.created_at+pg_catalog.make_interval(secs=>p_cache_ttl_seconds)
    where a.attempt_id=p_attempt_id returning a.* into v_write;
  update public.saved_lift_export_jobs e set status='completed',archive_path=v_write.storage_path,
    completed_at=v_write.published_at,expires_at=v_write.cache_expires_at,failure_code=null
    where e.id=v_job and e.user_id=p_user_id and e.status='processing';
  if not found then raise exception 'Archive job is no longer active.' using errcode='55000'; end if;
  return public.private_media_archive_receipt(v_write);
end;
$$;


create or replace function public.assert_private_media_generated_write(p_write public.private_media_generated_writes)
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
  if p_write.purpose='archive' then
    perform public.assert_private_media_archive_write(p_write);
    return;
  end if;
  if p_write.purpose='analyzed_export' then
    perform public.assert_private_media_export_write(p_write);
    return;
  end if;
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

create or replace function public.guard_private_media_generated_write()
returns trigger language plpgsql security invoker set search_path=''
as $$
begin
  if tg_op='DELETE' then
    raise exception 'Generated-write evidence must be retained.' using errcode='55000';
  elsif tg_op='INSERT' then
    if new.state is distinct from 'dispatching' or new.observed_at is not null
       or new.published_at is not null or new.cache_expires_at is not null
       or not pg_catalog.isfinite(new.created_at) then
      raise exception 'A generated write must begin pending.' using errcode='55000';
    end if;
    perform public.assert_private_media_generated_write(new);
    perform public.assert_private_media_generated_capacity(new);
  else
    if (pg_catalog.to_jsonb(new)-array['state','observed_at','published_at','cache_expires_at'])
       is distinct from (pg_catalog.to_jsonb(old)-array['state','observed_at','published_at','cache_expires_at']) then
      raise exception 'Generated-write identity is immutable.' using errcode='55000';
    end if;
    if not ((new.state=old.state and new.observed_at is not distinct from old.observed_at)
       or (old.state='dispatching' and new.state='succeeded' and new.observed_at is not null
           and pg_catalog.isfinite(new.observed_at) and new.observed_at>=new.created_at
           and new.observed_at<=pg_catalog.clock_timestamp())) then
      raise exception 'A generated write cannot clear or reopen its observed outcome.' using errcode='55000';
    end if;
    if new.published_at is distinct from old.published_at or new.cache_expires_at is distinct from old.cache_expires_at then
      if old.published_at is not null or old.cache_expires_at is not null
         or old.state is distinct from 'succeeded' or new.state is distinct from old.state
         or new.observed_at is distinct from old.observed_at or new.published_at is null
         or not pg_catalog.isfinite(new.published_at) or new.published_at<new.created_at
         or new.published_at>pg_catalog.clock_timestamp() or new.cache_expires_at is null
         or not pg_catalog.isfinite(new.cache_expires_at) or new.cache_expires_at<=pg_catalog.clock_timestamp() then
        raise exception 'Export publication cannot clear, extend or combine an outcome.' using errcode='55000';
      end if;
      if new.purpose='archive' then
        perform public.assert_private_media_archive_write(new);
      else
        perform public.assert_private_media_export_write(new);
      end if;
    end if;
  end if;
  return new;
end;
$$;

create or replace function public.fence_saved_lift_export_publication()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
declare v_write public.private_media_generated_writes%rowtype;
begin
  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id or new.user_id is distinct from old.user_id
       or new.video_ids is distinct from old.video_ids then
      raise exception 'Archive identity and selection cannot change.' using errcode = '55000';
    end if;
    if old.status<>'queued' and (new.attempts is distinct from old.attempts or new.started_at is distinct from old.started_at) then
      raise exception 'Archive processing generation cannot change.' using errcode='55000';
    end if;
    if (old.status = 'expired' and new.status <> 'expired')
       or (old.status = 'failed' and new.status not in ('failed', 'expired'))
       or (old.status = 'completed' and new.status in ('queued', 'processing'))
       or (old.status = 'processing' and new.status = 'queued') then
      raise exception 'Archive state cannot be reopened.' using errcode = '55000';
    end if;
    if old.status = 'completed' and new.status = 'failed'
       and new.failure_code is distinct from 'archive_missing' then
      raise exception 'A worker cannot fail a published archive.' using errcode = '55000';
    end if;
    if old.status = 'completed' and new.status = 'completed'
       and (new.archive_path is distinct from old.archive_path
         or new.completed_at is distinct from old.completed_at
         or new.expires_at is distinct from old.expires_at) then
      raise exception 'A completed archive cannot be republished.' using errcode = '55000';
    end if;
  end if;
  if new.status <> 'completed' and new.archive_path is not null then
    raise exception 'An incomplete archive cannot publish a path.' using errcode = '55000';
  end if;
  if tg_op = 'INSERT' or new.status in ('queued', 'processing', 'completed') then
    if new.id is null or new.id = '00000000-0000-0000-0000-000000000000'::uuid
       or new.user_id is null or new.user_id = '00000000-0000-0000-0000-000000000000'::uuid
       or coalesce(pg_catalog.array_ndims(new.video_ids), 0) <> 1
       or pg_catalog.cardinality(new.video_ids) not between 1 and 50
       or pg_catalog.array_position(new.video_ids, null) is not null
       or (select count(distinct id) from pg_catalog.unnest(new.video_ids) selected(id))
          <> pg_catalog.cardinality(new.video_ids) then
      raise exception 'A distinct selection of 1 to 50 videos is required.' using errcode = '22023';
    end if;
    -- A direct UPDATE already holds its archive row. Fail fast on a video lock
    -- rather than wait against revocation's video-before-archive lock order.
    perform v.id from public.videos v where v.id = any(new.video_ids)
      order by v.id for update nowait;
    if exists (
      select 1 from pg_catalog.unnest(new.video_ids) selected(id)
      left join public.videos v on v.id = selected.id
      where v.id is null or v.user_id is distinct from new.user_id
         or v.discarded_at is not null or v.storage_state = 'pruned'
         or not (coalesce(v.save_state = 'saved', false) or coalesce(v.is_saved, false))
         or (v.expires_at is not null and
             (not pg_catalog.isfinite(v.expires_at) or v.expires_at <= pg_catalog.clock_timestamp()))
         or exists (select 1 from public.video_deletion_outbox o where o.video_id = selected.id)
         or not exists (select 1 from public.analysis_results r where r.video_id = selected.id)
    ) then
      raise exception 'The complete archive selection is unavailable.' using errcode = '55000';
    end if;
    if new.status='completed' then
      if new.archive_path is null or new.completed_at is null or not pg_catalog.isfinite(new.completed_at)
         or new.expires_at is null or not pg_catalog.isfinite(new.expires_at)
         or new.expires_at<=pg_catalog.clock_timestamp() then
        raise exception 'A completed archive needs a finite published generation.' using errcode='55000';
      end if;
      if tg_op='INSERT' or old.status is distinct from 'completed' then
        select a.* into v_write from public.private_media_generated_writes a
          where a.purpose='archive' and a.user_id=new.user_id and a.archive_job_id=new.id
            and a.storage_path=new.archive_path and a.state='succeeded'
            and a.published_at=new.completed_at and a.cache_expires_at=new.expires_at
            and a.video_ids=new.video_ids and a.archive_attempt_count=new.attempts
            and a.archive_started_at=new.started_at;
        if not found then
          raise exception 'A completed archive needs its observed published attempt.' using errcode='55000';
        end if;
        perform public.assert_private_media_archive_write(v_write);
      end if;
    end if;
  end if;
  return new;
end;
$$;

create or replace function public.private_media_source_write_pending(p_video_id uuid,p_user_id uuid,p_storage_paths text[])
returns boolean language sql stable security invoker set search_path=''
as $$
  select exists(select 1 from public.private_media_write_attempts a where a.user_id=p_user_id
    and (a.video_id=p_video_id or a.storage_path=any(p_storage_paths)
      or exists(select 1 from public.upload_reservations r where r.id=a.reservation_id and r.video_id=p_video_id)))
    or exists(select 1 from public.private_media_generated_writes a where a.user_id=p_user_id
      and (a.video_id=p_video_id or p_video_id=any(a.video_ids) or a.storage_path=any(p_storage_paths)));
$$;

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
      where a.user_id=p_user_id and (a.video_id=any(v_ids) or a.video_ids && v_ids)
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
          where a.user_id=p_user_id and a.video_id=v_id and a.purpose<>'archive'
      ) as paths;
    select coalesce(pg_catalog.array_agg(distinct paths.path order by paths.path), '{}'::text[])
      into v_archive_paths from (
        select e.archive_path as path from public.saved_lift_export_jobs e
          where e.user_id = p_user_id and v_id = any(e.video_ids) and e.archive_path is not null
        union all
        select a.storage_path from public.private_media_generated_writes a
          where a.user_id=p_user_id and a.purpose='archive' and v_id=any(a.video_ids)
        union all
        -- Keep historical deterministic names for already-issued capabilities.
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

create or replace function public.claim_expired_video_deletion(p_video_id uuid)
returns setof public.video_deletion_outbox
language plpgsql security invoker set search_path = ''
as $$
declare
  v_video public.videos%rowtype;
  v_paths text[];
  v_archives text[];
  v_space_chars constant text :=
    U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680'
    || U&'\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000';
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
      where a.video_id=v_video.id and a.user_id=v_video.user_id and a.purpose<>'archive'
  ) paths;
  if v_paths is null then raise exception 'Missing retention storage paths'; end if;
  select coalesce(pg_catalog.array_agg(distinct path),'{}'::text[]) into v_archives from (
    select a.storage_path as path from public.private_media_generated_writes a
      where a.user_id=v_video.user_id and a.purpose='archive' and v_video.id=any(a.video_ids)
    union all select e.archive_path from public.saved_lift_export_jobs e
      where e.user_id=v_video.user_id and v_video.id=any(e.video_ids) and e.archive_path is not null
    union all select v_video.user_id::text||'/'||e.id::text||'.zip' from public.saved_lift_export_jobs e
      where e.user_id=v_video.user_id and v_video.id=any(e.video_ids)
  ) archive_paths;
  if exists(select 1 from pg_catalog.unnest(v_paths||v_archives) path
    where path='' or path<>pg_catalog.btrim(path,v_space_chars) or pg_catalog.right(path,1)='/' or pg_catalog.left(path,pg_catalog.length(v_video.user_id::text)+1)<>v_video.user_id::text||'/'
      or pg_catalog.strpos(path,'//')>0 or pg_catalog.strpos(path,pg_catalog.chr(92))>0
      or pg_catalog.strpos(path,'://')>0 or path ~ '[[:cntrl:]]' or path ~ '(^|/)\.{1,2}(/|$)') then
    raise exception 'Unsafe retention archive path'; end if;
  insert into public.video_deletion_outbox(video_id, user_id, storage_paths,archive_paths)
    values (v_video.id, v_video.user_id, v_paths,v_archives);
  -- The established analysis_results and analysis_jobs FKs cascade. Explicit
  -- result deletion also supports older installations without that cascade.
  delete from public.analysis_results where video_id = p_video_id;
  delete from public.videos where id = p_video_id;
  return query select * from public.video_deletion_outbox where video_id = p_video_id;
end;
$$;

revoke all on function public.plan_private_media_archive(uuid,uuid) from public,anon,authenticated;
grant execute on function public.plan_private_media_archive(uuid,uuid) to service_role;

revoke all on function public.assert_private_media_archive_write(public.private_media_generated_writes) from public,anon,authenticated;
grant execute on function public.assert_private_media_archive_write(public.private_media_generated_writes) to service_role;

revoke all on function public.private_media_archive_receipt(public.private_media_generated_writes) from public,anon,authenticated;
grant execute on function public.private_media_archive_receipt(public.private_media_generated_writes) to service_role;

revoke all on function public.admit_private_media_archive_write(uuid,uuid,uuid,integer,timestamptz,uuid[],jsonb,text,text,bigint,text,bigint,bigint) from public,anon,authenticated;
grant execute on function public.admit_private_media_archive_write(uuid,uuid,uuid,integer,timestamptz,uuid[],jsonb,text,text,bigint,text,bigint,bigint) to service_role;

revoke all on function public.publish_private_media_archive(uuid,uuid,integer) from public,anon,authenticated;
grant execute on function public.publish_private_media_archive(uuid,uuid,integer) to service_role;

create function public.read_private_media_archive(p_user_id uuid,p_archive_job_id uuid)
returns jsonb language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$
declare v_write public.private_media_generated_writes%rowtype;
begin
  perform public.assert_active_private_media_owner(p_user_id);
  if public.private_media_resource_video_ids(p_user_id,'archive',p_archive_job_id) is null then return null; end if;
  select a.* into v_write from public.private_media_generated_writes a
    join public.saved_lift_export_jobs e on e.id=a.archive_job_id and e.user_id=a.user_id
    where a.purpose='archive' and a.user_id=p_user_id and a.archive_job_id=p_archive_job_id
      and a.state='succeeded' and a.published_at is not null and a.cache_expires_at>pg_catalog.clock_timestamp()
      and e.status='completed' and e.archive_path=a.storage_path and e.completed_at=a.published_at
      and e.expires_at=a.cache_expires_at and e.video_ids=a.video_ids
      and e.attempts=a.archive_attempt_count and e.started_at=a.archive_started_at;
  if not found then return null; end if;
  return public.private_media_archive_receipt(v_write);
end;
$$;
revoke all on function public.read_private_media_archive(uuid,uuid) from public,anon,authenticated;
grant execute on function public.read_private_media_archive(uuid,uuid) to service_role;

commit;
