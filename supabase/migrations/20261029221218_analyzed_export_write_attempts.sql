begin;
set local lock_timeout='2s';
lock table public.videos,public.analysis_results,public.private_media_generated_writes in share row exclusive mode nowait;

alter table public.private_media_generated_writes
  add column analysis_id uuid,
  add column analysis_model_version text,
  add column analysis_snapshot_hash text,
  add column variant text,
  add column published_at timestamptz,
  add column cache_expires_at timestamptz;
alter table public.private_media_generated_writes drop constraint private_media_generated_writes_purpose_check;
-- Identify the original compound purpose/lease constraint without guessing its generated name.
do $$ declare v_name text; begin
  select c.conname into strict v_name from pg_catalog.pg_constraint c
    where c.conrelid='public.private_media_generated_writes'::regclass and c.contype='c'
      and pg_catalog.pg_get_constraintdef(c.oid) like '%purpose%'
      and pg_catalog.pg_get_constraintdef(c.oid) like '%job_id%';
  execute pg_catalog.format('alter table public.private_media_generated_writes drop constraint %I',v_name);
end $$;
alter table public.private_media_generated_writes
  add constraint generated_purpose_check check(purpose in ('thumbnail','playback','thumbnail_backfill','analyzed_export')),
  add constraint generated_lease_check check(
    (purpose in ('thumbnail_backfill','analyzed_export') and job_id is null and worker_id is null and attempt_count is null)
    or (purpose in ('thumbnail','playback') and job_id is not null and worker_id is not null
      and pg_catalog.btrim(worker_id)<>'' and attempt_count is not null and attempt_count>=1)),
  add constraint generated_export_snapshot_check check(
    (purpose='analyzed_export' and analysis_id is not null and analysis_id<>'00000000-0000-0000-0000-000000000000'::uuid
      and analysis_model_version is not null and pg_catalog.btrim(analysis_model_version)<>''
      and analysis_snapshot_hash is not null and analysis_snapshot_hash ~ '^[0-9a-f]{64}$'
      and variant is not null and variant in ('pose','barbell','pose-barbell') and content_type='video/mp4')
    or (purpose<>'analyzed_export' and analysis_id is null and analysis_model_version is null
      and analysis_snapshot_hash is null and variant is null and published_at is null and cache_expires_at is null)),
  add constraint generated_export_publication_check check(
    (published_at is null and cache_expires_at is null)
    or (purpose='analyzed_export' and state='succeeded' and published_at is not null
      and cache_expires_at is not null and pg_catalog.isfinite(published_at)
      and pg_catalog.isfinite(cache_expires_at) and published_at>=created_at and cache_expires_at>published_at));
grant insert(analysis_id,analysis_model_version,analysis_snapshot_hash,variant),update(published_at,cache_expires_at)
  on public.private_media_generated_writes to service_role;

-- Caller already holds owner/video authority for waiting RPCs; triggers fail fast.
create function public.lock_private_media_export_resource(p_user_id uuid,p_video_id uuid)
returns jsonb language plpgsql security invoker set search_path=''
as $$
declare v_video public.videos%rowtype; v_analysis public.analysis_results%rowtype; v_source text;
  v_space_chars constant text :=
    U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680'
    || U&'\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000';
begin
  perform public.assert_active_private_media_owner(p_user_id);
  select v.* into v_video from public.videos v where v.id=p_video_id for update nowait;
  if not found or v_video.user_id is distinct from p_user_id or v_video.discarded_at is not null
     or v_video.storage_state='pruned' or v_video.status is distinct from 'completed'
     or not(coalesce(v_video.save_state='saved',false) or coalesce(v_video.is_saved,false))
     or (v_video.expires_at is not null and (not pg_catalog.isfinite(v_video.expires_at)
        or v_video.expires_at<=pg_catalog.clock_timestamp()))
     or exists(select 1 from public.video_deletion_outbox o where o.video_id=p_video_id)
     or exists(select 1 from public.analysis_jobs j where j.video_id=p_video_id
        and j.status in ('queued','processing','retry_wait')) then
    raise exception 'The current Saved Lift is unavailable for export.' using errcode='55000';
  end if;
  v_source:=coalesce(v_video.playback_path,v_video.storage_path);
  if v_source is null or pg_catalog.left(v_source,pg_catalog.length(p_user_id::text)+1)<>p_user_id::text||'/'
     or v_source<>pg_catalog.btrim(v_source,v_space_chars) or pg_catalog.right(v_source,1)='/'
     or pg_catalog.strpos(v_source,'//')>0 or pg_catalog.strpos(v_source,pg_catalog.chr(92))>0
     or pg_catalog.strpos(v_source,'://')>0 or v_source ~ '[[:cntrl:]]' or v_source ~ '(^|/)\.{1,2}(/|$)' then
    raise exception 'Export source path is unavailable.' using errcode='55000';
  end if;
  select r.* into v_analysis from public.analysis_results r where r.video_id=p_video_id
    order by r.created_at desc,r.id desc limit 1 for share nowait;
  if not found or v_analysis.model_version is null or pg_catalog.btrim(v_analysis.model_version)=''
     or pg_catalog.jsonb_typeof(v_analysis.result_json) is distinct from 'object'
     or not pg_catalog.isfinite(v_analysis.created_at) then
    raise exception 'The current analysis is unavailable for export.' using errcode='55000';
  end if;
  return pg_catalog.jsonb_build_object('source_path',v_source,'analysis_id',v_analysis.id,
    'analysis_model_version',v_analysis.model_version,'result_json',v_analysis.result_json,
    'analysis_snapshot_hash',pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(v_analysis.result_json::text,'UTF8')),'hex'));
end;
$$;
revoke all on function public.lock_private_media_export_resource(uuid,uuid) from public,anon,authenticated;
grant execute on function public.lock_private_media_export_resource(uuid,uuid) to service_role;

create function public.assert_private_media_export_write(p_write public.private_media_generated_writes)
returns void language plpgsql security invoker set search_path=''
as $$
declare v_current jsonb; v_expected text;
begin
  v_current:=public.lock_private_media_export_resource(p_write.user_id,p_write.video_id);
  v_expected:=p_write.user_id::text||'/exports/'||p_write.video_id::text||'-'||p_write.analysis_id::text
    ||'-'||p_write.variant||'-'||p_write.attempt_id::text||'-h264-v1.mp4';
  if p_write.purpose is distinct from 'analyzed_export' or p_write.content_type is distinct from 'video/mp4'
     or p_write.storage_path is distinct from v_expected or p_write.source_path is distinct from (v_current->>'source_path')
     or p_write.analysis_id::text is distinct from (v_current->>'analysis_id')
     or p_write.analysis_model_version is distinct from (v_current->>'analysis_model_version')
     or p_write.analysis_snapshot_hash is distinct from (v_current->>'analysis_snapshot_hash')
     or p_write.job_id is not null or p_write.worker_id is not null or p_write.attempt_count is not null then
    raise exception 'Export write does not match the current source and analysis.' using errcode='55000';
  end if;
end;
$$;
revoke all on function public.assert_private_media_export_write(public.private_media_generated_writes) from public,anon,authenticated;
grant execute on function public.assert_private_media_export_write(public.private_media_generated_writes) to service_role;

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
revoke all on function public.assert_private_media_generated_write(public.private_media_generated_writes) from public,anon,authenticated;
grant execute on function public.assert_private_media_generated_write(public.private_media_generated_writes) to service_role;

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
      perform public.assert_private_media_export_write(new);
    end if;
  end if;
  return new;
end;
$$;
revoke all on function public.guard_private_media_generated_write() from public,anon,authenticated;
grant execute on function public.guard_private_media_generated_write() to service_role;

create function public.admit_private_media_export_write(
  p_attempt_id uuid,p_user_id uuid,p_video_id uuid,p_bucket text,p_storage_path text,p_source_path text,
  p_analysis_id uuid,p_analysis_model_version text,p_analysis_result jsonb,p_variant text,p_size_bytes bigint,
  p_max_user_bytes bigint,p_max_global_bytes bigint
)
returns table(attempt_id uuid,user_id uuid,video_id uuid,purpose text,bucket text,storage_path text,source_path text,content_type text,size_bytes bigint,job_id uuid,worker_id text,attempt_count integer,analysis_id uuid,analysis_model_version text,analysis_snapshot_hash text,variant text,state text,published_at timestamptz,cache_expires_at timestamptz)
language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$
declare v_current jsonb;
begin
  perform public.lock_active_private_media_owner(p_user_id,false);
  perform v.id from public.videos v where v.id=p_video_id for update;
  v_current:=public.lock_private_media_export_resource(p_user_id,p_video_id);
  if p_analysis_id::text is distinct from (v_current->>'analysis_id')
     or p_analysis_model_version is distinct from (v_current->>'analysis_model_version')
     or p_analysis_result is distinct from (v_current->'result_json')
     or p_source_path is distinct from (v_current->>'source_path') then
    raise exception 'The rendered analysis snapshot is no longer current.' using errcode='55000';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('peso:upload-capacity',0));
  return query insert into public.private_media_generated_writes as a
    (attempt_id,user_id,video_id,purpose,bucket,storage_path,source_path,content_type,size_bytes,
     analysis_id,analysis_model_version,analysis_snapshot_hash,variant,max_user_bytes,max_global_bytes)
    values(p_attempt_id,p_user_id,p_video_id,'analyzed_export',p_bucket,p_storage_path,p_source_path,'video/mp4',p_size_bytes,
      p_analysis_id,p_analysis_model_version,v_current->>'analysis_snapshot_hash',p_variant,p_max_user_bytes,p_max_global_bytes)
    returning a.attempt_id,a.user_id,a.video_id,a.purpose,a.bucket,a.storage_path,a.source_path,a.content_type,a.size_bytes,a.job_id,a.worker_id,a.attempt_count,a.analysis_id,a.analysis_model_version,a.analysis_snapshot_hash,a.variant,a.state,a.published_at,a.cache_expires_at;
end;
$$;
revoke all on function public.admit_private_media_export_write(uuid,uuid,uuid,text,text,text,uuid,text,jsonb,text,bigint,bigint,bigint) from public,anon,authenticated;
grant execute on function public.admit_private_media_export_write(uuid,uuid,uuid,text,text,text,uuid,text,jsonb,text,bigint,bigint,bigint) to service_role;

create function public.publish_private_media_export(p_attempt_id uuid,p_user_id uuid,p_cache_ttl_seconds integer)
returns table(attempt_id uuid,user_id uuid,video_id uuid,purpose text,bucket text,storage_path text,source_path text,content_type text,size_bytes bigint,job_id uuid,worker_id text,attempt_count integer,analysis_id uuid,analysis_model_version text,analysis_snapshot_hash text,variant text,state text,published_at timestamptz,cache_expires_at timestamptz)
language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$
declare v_video_id uuid; v_a public.private_media_generated_writes%rowtype; v_now timestamptz;
begin
  if p_cache_ttl_seconds is null or p_cache_ttl_seconds<=0 then
    raise exception 'A positive configured cache lifetime is required.' using errcode='22023';
  end if;
  select a.video_id into v_video_id from public.private_media_generated_writes a
    where a.attempt_id=p_attempt_id and a.user_id=p_user_id;
  if not found then return; end if;
  perform public.lock_active_private_media_owner(p_user_id,false);
  perform v.id from public.videos v where v.id=v_video_id for update;
  select a.* into v_a from public.private_media_generated_writes a where a.attempt_id=p_attempt_id for update nowait;
  if not found or v_a.user_id is distinct from p_user_id or v_a.purpose is distinct from 'analyzed_export'
     or v_a.state is distinct from 'succeeded' then
    raise exception 'Export upload observation is unavailable.' using errcode='55000';
  end if;
  perform public.assert_private_media_export_write(v_a);
  if v_a.published_at is null then
    v_now:=pg_catalog.clock_timestamp();
    update public.private_media_generated_writes a set published_at=v_now,
      cache_expires_at=v_a.created_at+pg_catalog.make_interval(secs=>p_cache_ttl_seconds) where a.attempt_id=p_attempt_id;
  end if;
  return query select a.attempt_id,a.user_id,a.video_id,a.purpose,a.bucket,a.storage_path,a.source_path,a.content_type,a.size_bytes,a.job_id,a.worker_id,a.attempt_count,a.analysis_id,a.analysis_model_version,a.analysis_snapshot_hash,a.variant,a.state,a.published_at,a.cache_expires_at from public.private_media_generated_writes a where a.attempt_id=p_attempt_id;
end;
$$;
revoke all on function public.publish_private_media_export(uuid,uuid,integer) from public,anon,authenticated;
grant execute on function public.publish_private_media_export(uuid,uuid,integer) to service_role;

-- Resolve current publication; a result UUID alone never identifies its contents.
create function public.read_private_media_export(p_user_id uuid,p_video_id uuid,p_variant text,p_bucket text,p_analysis_id uuid default null)
returns table(attempt_id uuid,user_id uuid,video_id uuid,purpose text,bucket text,storage_path text,source_path text,content_type text,size_bytes bigint,job_id uuid,worker_id text,attempt_count integer,analysis_id uuid,analysis_model_version text,analysis_snapshot_hash text,variant text,state text,published_at timestamptz,cache_expires_at timestamptz)
language plpgsql security invoker set search_path='' set lock_timeout='2s'
as $$
declare v_current jsonb;
begin
  perform public.lock_active_private_media_owner(p_user_id,false);
  perform v.id from public.videos v where v.id=p_video_id for update;
  v_current:=public.lock_private_media_export_resource(p_user_id,p_video_id);
  if p_variant is null or p_variant not in ('pose','barbell','pose-barbell')
     or (p_analysis_id is not null and p_analysis_id::text is distinct from (v_current->>'analysis_id')) then
    raise exception 'The requested current export is unavailable.' using errcode='55000';
  end if;
  return query select a.attempt_id,a.user_id,a.video_id,a.purpose,a.bucket,a.storage_path,a.source_path,a.content_type,a.size_bytes,a.job_id,a.worker_id,a.attempt_count,a.analysis_id,a.analysis_model_version,a.analysis_snapshot_hash,a.variant,a.state,a.published_at,a.cache_expires_at from public.private_media_generated_writes a
    where a.user_id=p_user_id and a.video_id=p_video_id and a.purpose='analyzed_export'
      and a.variant=p_variant and a.bucket=p_bucket and a.state='succeeded'
      and a.analysis_id::text=v_current->>'analysis_id'
      and a.analysis_model_version=v_current->>'analysis_model_version'
      and a.analysis_snapshot_hash=v_current->>'analysis_snapshot_hash'
      and a.source_path=v_current->>'source_path' and a.published_at is not null
      and a.cache_expires_at>pg_catalog.clock_timestamp()
    order by a.published_at desc,a.attempt_id desc limit 1;
end;
$$;
revoke all on function public.read_private_media_export(uuid,uuid,text,text,uuid) from public,anon,authenticated;
grant execute on function public.read_private_media_export(uuid,uuid,text,text,uuid) to service_role;

commit;
