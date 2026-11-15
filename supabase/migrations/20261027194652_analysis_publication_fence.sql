-- One video lock serializes publication, revocation and queue state changes.
create function public.lock_video_analysis_attempt(
  p_video_id uuid, p_job_id uuid, p_worker_id text, p_attempt_count integer
)
returns public.videos
language plpgsql security invoker set search_path = ''
as $$
declare
  v_video public.videos%rowtype;
  v_job public.analysis_jobs%rowtype;
begin
  if p_video_id is null or p_job_id is null or p_worker_id is null
     or pg_catalog.btrim(p_worker_id) = '' or p_attempt_count is null or p_attempt_count < 1 then
    return null;
  end if;
  select * into v_video from public.videos v where v.id = p_video_id for update;
  if not found then return null; end if;
  -- Never wait for a child row while holding its video: older queue functions
  -- may already hold a child row and be waiting for this video.
  select * into v_job from public.analysis_jobs j where j.id = p_job_id for update nowait;
  if not found or v_job.video_id is distinct from p_video_id
     or v_job.status is distinct from 'processing'
     or v_job.lease_owner is distinct from p_worker_id
     or v_job.attempt_count is distinct from p_attempt_count
     or v_job.lease_expires_at is null or not pg_catalog.isfinite(v_job.lease_expires_at)
     or v_job.lease_expires_at <= pg_catalog.clock_timestamp()
     or v_video.discarded_at is not null or v_video.storage_state = 'pruned'
     or (v_video.expires_at is not null and (not pg_catalog.isfinite(v_video.expires_at)
         or v_video.expires_at <= pg_catalog.clock_timestamp()))
     or exists (select 1 from public.video_deletion_outbox o where o.video_id = p_video_id) then
    return null;
  end if;
  return v_video;
end;
$$;
revoke all on function public.lock_video_analysis_attempt(uuid,uuid,text,integer) from public,anon,authenticated;
grant execute on function public.lock_video_analysis_attempt(uuid,uuid,text,integer) to service_role;

create function public.publish_video_analysis(
  p_video_id uuid, p_job_id uuid, p_worker_id text, p_attempt_count integer,
  p_fields jsonb, p_model_version text default null, p_result_json jsonb default null
)
returns jsonb
language plpgsql security invoker set search_path = '' set lock_timeout = '2s'
as $$
declare
  v_video public.videos%rowtype;
  v_next public.videos%rowtype;
  v_result public.analysis_results%rowtype;
  v_key text;
  v_value jsonb;
  v_path text;
  v_space_chars constant text :=
    U&'\0009\000A\000B\000C\000D\001C\001D\001E\001F\0020\0085\00A0\1680'
    || U&'\2000\2001\2002\2003\2004\2005\2006\2007\2008\2009\200A\2028\2029\202F\205F\3000';
begin
  if p_fields is null or pg_catalog.jsonb_typeof(p_fields) <> 'object'
     or (p_model_version is null) <> (p_result_json is null)
     or (p_model_version is not null and (pg_catalog.btrim(p_model_version) = ''
         or pg_catalog.jsonb_typeof(p_result_json) <> 'object')) then
    raise exception 'Invalid analysis publication.' using errcode = '22023';
  end if;
  for v_key, v_value in select * from pg_catalog.jsonb_each(p_fields) loop
    if v_key not in ('status','fps','duration_ms','thumbnail_path','playback_path',
        'original_storage_path','storage_optimized_at','storage_optimization_error') then
      raise exception 'Unsupported analysis field.' using errcode = '22023';
    end if;
    if (v_key = 'status' and (pg_catalog.jsonb_typeof(v_value) <> 'string'
         or v_value #>> '{}' not in ('processing','completed','failed')))
       or (v_key in ('fps','duration_ms') and pg_catalog.jsonb_typeof(v_value) <> 'number')
       or (v_key not in ('status','fps','duration_ms')
           and pg_catalog.jsonb_typeof(v_value) not in ('string','null')) then
      raise exception 'Invalid analysis field value.' using errcode = '22023';
    end if;
  end loop;
  v_video := public.lock_video_analysis_attempt(p_video_id,p_job_id,p_worker_id,p_attempt_count);
  if v_video.id is null then return null; end if;
  v_next := pg_catalog.jsonb_populate_record(v_video,p_fields);
  if (p_fields ? 'fps' and (v_next.fps <= 0 or v_next.fps::text in ('NaN','Infinity','-Infinity')))
     or (p_fields ? 'duration_ms' and v_next.duration_ms <= 0)
     or (v_next.storage_optimized_at is not null and not pg_catalog.isfinite(v_next.storage_optimized_at)) then
    raise exception 'Invalid analysis metadata.' using errcode = '22023';
  end if;
  for v_path in select path from pg_catalog.unnest(array[
    case when p_fields ? 'thumbnail_path' then v_next.thumbnail_path end,
    case when p_fields ? 'playback_path' then v_next.playback_path end,
    case when p_fields ? 'original_storage_path' then v_next.original_storage_path end
  ]) as selected(path) where path is not null loop
    if v_path = '' or v_path <> pg_catalog.btrim(v_path,v_space_chars)
       or pg_catalog.left(v_path,pg_catalog.length(v_video.user_id::text)+1) <> v_video.user_id::text || '/'
       or pg_catalog.right(v_path,1) = '/' or pg_catalog.strpos(v_path,'//') > 0
       or pg_catalog.strpos(v_path,pg_catalog.chr(92)) > 0 or pg_catalog.strpos(v_path,'://') > 0
       or v_path ~ '[[:cntrl:]]' or v_path ~ '(^|/)\.{1,2}(/|$)' then
      raise exception 'Unsafe analysis asset path.' using errcode = '22023';
    end if;
  end loop;
  if p_model_version is not null then
    -- Do not wait for another child writer that may request our video lock.
    perform r.id from public.analysis_results r where r.video_id = p_video_id
      and r.model_version = p_model_version for update nowait;
    insert into public.analysis_results(video_id,model_version,result_json)
      values(p_video_id,p_model_version,p_result_json)
      on conflict(video_id,model_version) do update set result_json = excluded.result_json
      returning * into v_result;
  end if;
  if (select j.lease_expires_at from public.analysis_jobs j where j.id=p_job_id) <= pg_catalog.clock_timestamp()
     or (v_video.expires_at is not null and v_video.expires_at<=pg_catalog.clock_timestamp()) then
    raise exception 'Analysis publication expired.' using errcode='55000';
  end if;
  update public.videos v set status=v_next.status,fps=v_next.fps,duration_ms=v_next.duration_ms,
    thumbnail_path=v_next.thumbnail_path,playback_path=v_next.playback_path,
    original_storage_path=v_next.original_storage_path,storage_optimized_at=v_next.storage_optimized_at,
    storage_optimization_error=v_next.storage_optimization_error
    where v.id=p_video_id returning * into v_video;
  return pg_catalog.jsonb_build_object('video',pg_catalog.to_jsonb(v_video),'analysis',pg_catalog.to_jsonb(v_result));
end;
$$;
revoke all on function public.publish_video_analysis(uuid,uuid,text,integer,jsonb,text,jsonb) from public,anon,authenticated;
grant execute on function public.publish_video_analysis(uuid,uuid,text,integer,jsonb,text,jsonb) to service_role;

-- Old workers must fail closed during cutover instead of mutating a later attempt.
revoke all on function public.renew_video_analysis_job_lease(uuid,text,integer) from public,anon,authenticated,service_role;
revoke all on function public.complete_video_analysis_job(uuid,text) from public,anon,authenticated,service_role;
revoke all on function public.report_video_analysis_job_progress(uuid,text,text) from public,anon,authenticated,service_role;
revoke all on function public.record_video_analysis_job_failure(uuid,text,text,text,boolean) from public,anon,authenticated,service_role;
revoke all on function public.fail_video_analysis_job(uuid,text,text) from public,anon,authenticated,service_role;

create function public.renew_video_analysis_job_lease(p_job_id uuid,p_worker_id text,p_attempt_count integer,p_lease_seconds integer default 3600)
returns boolean language plpgsql security invoker set search_path=''
as $$
declare
  v_video_id uuid;
  v_video public.videos%rowtype;
begin
  select j.video_id into v_video_id from public.analysis_jobs j where j.id=p_job_id;
  v_video:=public.lock_video_analysis_attempt(v_video_id,p_job_id,p_worker_id,p_attempt_count);
  if v_video.id is null then return false; end if;
  if p_lease_seconds is null then return false; end if;
  update public.analysis_jobs j set lease_expires_at=pg_catalog.clock_timestamp()
    + pg_catalog.make_interval(secs=>least(greatest(p_lease_seconds,60),21600)),
    last_heartbeat_at=pg_catalog.clock_timestamp() where j.id=p_job_id;
  return true;
end;
$$;
revoke all on function public.renew_video_analysis_job_lease(uuid,text,integer,integer) from public,anon,authenticated;
grant execute on function public.renew_video_analysis_job_lease(uuid,text,integer,integer) to service_role;

create function public.report_video_analysis_job_progress(p_job_id uuid,p_worker_id text,p_attempt_count integer,p_stage text)
returns boolean language plpgsql security invoker set search_path=''
as $$
declare
  v_video_id uuid;
  v_video public.videos%rowtype;
begin
  select j.video_id into v_video_id from public.analysis_jobs j where j.id=p_job_id;
  v_video:=public.lock_video_analysis_attempt(v_video_id,p_job_id,p_worker_id,p_attempt_count);
  if v_video.id is null then return false; end if;
  if p_stage is null or p_stage not in ('downloading','pose','barbell_tracking','saving') then
    raise exception 'Invalid analysis stage.' using errcode='22023';
  end if;
  update public.analysis_jobs j set stage=p_stage,stage_started_at=pg_catalog.clock_timestamp(),
    stage_timestamps=j.stage_timestamps || pg_catalog.jsonb_build_object(p_stage,pg_catalog.clock_timestamp()),
    last_heartbeat_at=pg_catalog.clock_timestamp() where j.id=p_job_id;
  return true;
end;
$$;
revoke all on function public.report_video_analysis_job_progress(uuid,text,integer,text) from public,anon,authenticated;
grant execute on function public.report_video_analysis_job_progress(uuid,text,integer,text) to service_role;

create function public.complete_video_analysis_job(p_job_id uuid,p_worker_id text,p_attempt_count integer)
returns boolean language plpgsql security invoker set search_path=''
as $$
declare
  v_video_id uuid;
  v_video public.videos%rowtype;
begin
  select j.video_id into v_video_id from public.analysis_jobs j where j.id=p_job_id;
  v_video:=public.lock_video_analysis_attempt(v_video_id,p_job_id,p_worker_id,p_attempt_count);
  if v_video.id is null then return false; end if;
  update public.analysis_jobs j set status='completed',stage='ready',
    stage_started_at=pg_catalog.clock_timestamp(),
    stage_timestamps=j.stage_timestamps || pg_catalog.jsonb_build_object('ready',pg_catalog.clock_timestamp()),
    last_heartbeat_at=pg_catalog.clock_timestamp(),lease_owner=null,lease_expires_at=null,
    completed_at=pg_catalog.clock_timestamp() where j.id=p_job_id;
  update public.videos v set status='completed' where v.id=v_video.id;
  return true;
end;
$$;
revoke all on function public.complete_video_analysis_job(uuid,text,integer) from public,anon,authenticated;
grant execute on function public.complete_video_analysis_job(uuid,text,integer) to service_role;

create function public.record_video_analysis_job_failure(p_job_id uuid,p_worker_id text,p_attempt_count integer,p_error text,p_failure_class text,p_retryable boolean)
returns text language plpgsql security invoker set search_path=''
as $$
declare
  v_video_id uuid;
  v_video public.videos%rowtype;
  v_job public.analysis_jobs%rowtype;
  v_status text;
begin
  select j.video_id into v_video_id from public.analysis_jobs j where j.id=p_job_id;
  v_video:=public.lock_video_analysis_attempt(v_video_id,p_job_id,p_worker_id,p_attempt_count);
  if v_video.id is null then return null; end if;
  if p_retryable is null then return null; end if;
  select * into v_job from public.analysis_jobs j where j.id=p_job_id;
  if not p_retryable or v_job.attempt_count>=v_job.max_attempts then
    v_status:='failed';
  else v_status:='retry_wait'; end if;
  update public.analysis_jobs j set status=v_status,
    stage=case when v_status='failed' then 'failed' else 'queued' end,
    stage_started_at=pg_catalog.clock_timestamp(),
    stage_timestamps=j.stage_timestamps || pg_catalog.jsonb_build_object(
      case when v_status='failed' then 'failed' else 'queued' end,pg_catalog.clock_timestamp()),
    available_at=case when v_status='retry_wait' then pg_catalog.clock_timestamp()
      +pg_catalog.make_interval(secs=>least(300,greatest(5,pg_catalog.power(2,least(v_job.attempt_count,8))::integer)))
      else j.available_at end,
    last_heartbeat_at=pg_catalog.clock_timestamp(),lease_owner=null,lease_expires_at=null,
    last_error=pg_catalog.left(coalesce(p_error,'Unknown analysis failure.'),2000),
    failure_class=nullif(pg_catalog.left(coalesce(p_failure_class,'unknown'),120),''),
    completed_at=case when v_status='failed' then pg_catalog.clock_timestamp() else j.completed_at end
    where j.id=p_job_id;
  update public.videos v set status=case when v_status='failed' then 'failed' else 'queued' end
    where v.id=v_video.id;
  return v_status;
end;
$$;
revoke all on function public.record_video_analysis_job_failure(uuid,text,integer,text,text,boolean) from public,anon,authenticated;
grant execute on function public.record_video_analysis_job_failure(uuid,text,integer,text,text,boolean) to service_role;

create or replace function public.claim_video_analysis_job(p_worker_id text,p_lease_seconds integer default 3600)
returns table(id uuid,video_id uuid,status text,attempt_count integer)
language plpgsql security invoker set search_path=''
as $$
declare
  v_candidate public.analysis_jobs%rowtype;
  v_job public.analysis_jobs%rowtype;
  v_video public.videos%rowtype;
begin
  if p_worker_id is null or pg_catalog.btrim(p_worker_id)='' or p_lease_seconds is null then
    raise exception 'Worker ID and lease duration are required.' using errcode='22023';
  end if;
  for v_candidate in select j.* from public.analysis_jobs j
    where j.job_type='video_analysis' and j.status in ('queued','retry_wait')
      order by j.available_at,j.created_at,j.id
  loop
    select * into v_video from public.videos v where v.id=v_candidate.video_id for update skip locked;
    if not found then continue; end if;
    select * into v_job from public.analysis_jobs j where j.id=v_candidate.id for update skip locked;
    if not found or v_job.video_id is distinct from v_video.id or v_job.job_type<>'video_analysis'
       or v_job.status not in ('queued','retry_wait') then continue; end if;
    if v_video.discarded_at is not null or v_video.storage_state='pruned'
       or (v_video.expires_at is not null and (not pg_catalog.isfinite(v_video.expires_at)
           or v_video.expires_at<=pg_catalog.clock_timestamp()))
       or exists(select 1 from public.video_deletion_outbox o where o.video_id=v_video.id) then
      -- Leaving an unusable queued job active would pin both quota and retention.
      update public.analysis_jobs j set status='cancelled',stage='failed',
        stage_started_at=pg_catalog.clock_timestamp(),
        stage_timestamps=j.stage_timestamps||pg_catalog.jsonb_build_object('failed',pg_catalog.clock_timestamp()),
        lease_owner=null,lease_expires_at=null,completed_at=pg_catalog.clock_timestamp(),
        failure_class='video_revoked',last_heartbeat_at=pg_catalog.clock_timestamp()
        where j.id=v_job.id;
      continue;
    end if;
    if v_job.available_at>pg_catalog.clock_timestamp() then continue; end if;
    update public.analysis_jobs j set status='processing',stage='downloading',
      stage_started_at=pg_catalog.clock_timestamp(),
      stage_timestamps=j.stage_timestamps||pg_catalog.jsonb_build_object('downloading',pg_catalog.clock_timestamp()),
      attempt_count=j.attempt_count+1,lease_owner=pg_catalog.btrim(p_worker_id),
      lease_expires_at=pg_catalog.clock_timestamp()+pg_catalog.make_interval(secs=>least(greatest(p_lease_seconds,60),21600)),
      last_heartbeat_at=pg_catalog.clock_timestamp(),last_error=null,failure_class=null
      where j.id=v_job.id returning * into v_job;
    update public.videos v set status='processing' where v.id=v_video.id;
    return query select v_job.id,v_job.video_id,v_job.status,v_job.attempt_count;
    return;
  end loop;
end;
$$;
revoke all on function public.claim_video_analysis_job(text,integer) from public,anon,authenticated;
grant execute on function public.claim_video_analysis_job(text,integer) to service_role;

create or replace function public.recover_expired_video_analysis_jobs()
returns table(retried_count integer,failed_count integer)
language plpgsql security invoker set search_path=''
as $$
declare
  v_candidate public.analysis_jobs%rowtype;
  v_job public.analysis_jobs%rowtype;
  v_video public.videos%rowtype;
  v_status text;
  v_retry integer:=0;
  v_failed integer:=0;
begin
  for v_candidate in select j.* from public.analysis_jobs j where j.status='processing'
    and (j.lease_expires_at is null or not pg_catalog.isfinite(j.lease_expires_at)
      or j.lease_expires_at<=pg_catalog.clock_timestamp()) order by j.video_id,j.id
  loop
    select * into v_video from public.videos v where v.id=v_candidate.video_id for update skip locked;
    if not found then continue; end if;
    select * into v_job from public.analysis_jobs j where j.id=v_candidate.id for update skip locked;
    if not found or v_job.video_id is distinct from v_video.id or v_job.status<>'processing'
       or (v_job.lease_expires_at is not null and pg_catalog.isfinite(v_job.lease_expires_at)
           and v_job.lease_expires_at>pg_catalog.clock_timestamp()) then continue; end if;
    if v_video.discarded_at is not null or v_video.storage_state='pruned'
       or (v_video.expires_at is not null and (not pg_catalog.isfinite(v_video.expires_at)
           or v_video.expires_at<=pg_catalog.clock_timestamp()))
       or exists(select 1 from public.video_deletion_outbox o where o.video_id=v_video.id) then
      update public.analysis_jobs j set status='cancelled',stage='failed',
        stage_started_at=pg_catalog.clock_timestamp(),
        stage_timestamps=j.stage_timestamps||pg_catalog.jsonb_build_object('failed',pg_catalog.clock_timestamp()),
        lease_owner=null,lease_expires_at=null,completed_at=pg_catalog.clock_timestamp(),
        failure_class='video_revoked',last_heartbeat_at=pg_catalog.clock_timestamp()
        where j.id=v_job.id;
      continue;
    end if;
    if v_job.attempt_count>=v_job.max_attempts then
      v_status:='failed';v_failed:=v_failed+1;
    else v_status:='retry_wait';v_retry:=v_retry+1;end if;
    update public.analysis_jobs j set status=v_status,
      stage=case when v_status='failed' then 'failed' else 'queued' end,
      stage_started_at=pg_catalog.clock_timestamp(),
      stage_timestamps=j.stage_timestamps||pg_catalog.jsonb_build_object(
        case when v_status='failed' then 'failed' else 'queued' end,pg_catalog.clock_timestamp()),
      available_at=case when v_status='retry_wait' then pg_catalog.clock_timestamp()
        +pg_catalog.make_interval(secs=>least(300,greatest(5,pg_catalog.power(2,least(v_job.attempt_count,8))::integer)))
        else j.available_at end,
      lease_owner=null,lease_expires_at=null,last_error='Worker lease expired before analysis completed.',
      failure_class='worker_lease_expired',last_heartbeat_at=pg_catalog.clock_timestamp(),
      completed_at=case when v_status='failed' then pg_catalog.clock_timestamp() else j.completed_at end
      where j.id=v_job.id;
    update public.videos v set status=case when v_status='failed' then 'failed' else 'queued' end
      where v.id=v_video.id;
  end loop;
  return query select v_retry,v_failed;
end;
$$;
revoke all on function public.recover_expired_video_analysis_jobs() from public,anon,authenticated;
grant execute on function public.recover_expired_video_analysis_jobs() to service_role;
