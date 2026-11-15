begin;

-- A child writer must never wait on an owner-first deletion transaction.
-- Missing/deleting and busy owners are different outcomes: busy work is retried.
create function public.private_media_owner_work_state(p_user_id uuid)
returns text language plpgsql security invoker set search_path=''
as $$
declare v_at timestamptz;
begin
  if p_user_id is null or p_user_id='00000000-0000-0000-0000-000000000000'::uuid then
    return 'unavailable';
  end if;
  begin
    select o.deleting_at into v_at from public.private_media_owners o
      where o.user_id=p_user_id for update nowait;
    if not found or v_at is not null then return 'unavailable'; end if;
  exception when lock_not_available then
    return 'busy';
  end;
  return 'active';
end;
$$;
revoke all on function public.private_media_owner_work_state(uuid) from public,anon,authenticated;
grant execute on function public.private_media_owner_work_state(uuid) to service_role;

-- Direct child writes share-lock the current video without waiting, then lock
-- its owner. They cannot publish into a revoked, expired or outboxed resource.
create function public.assert_private_media_video_work(p_video_id uuid)
returns void language plpgsql security invoker set search_path=''
as $$
declare v_video public.videos%rowtype;
begin
  select v.* into v_video from public.videos v where v.id=p_video_id for share nowait;
  if not found then raise exception 'Analysis video is unavailable.' using errcode='23503'; end if;
  perform public.assert_active_private_media_owner(v_video.user_id);
  if v_video.discarded_at is not null or v_video.storage_state='pruned'
     or (v_video.expires_at is not null and (not pg_catalog.isfinite(v_video.expires_at)
         or v_video.expires_at<=pg_catalog.clock_timestamp()))
     or exists(select 1 from public.video_deletion_outbox o where o.video_id=v_video.id) then
    raise exception 'Analysis video is unavailable.' using errcode='55000';
  end if;
end;
$$;
revoke all on function public.assert_private_media_video_work(uuid) from public,anon,authenticated;
grant execute on function public.assert_private_media_video_work(uuid) to service_role;

create function public.fence_owner_analysis_job()
returns trigger language plpgsql security invoker set search_path=''
as $$
begin
  if tg_op='UPDATE' then
    if new.id is distinct from old.id or new.video_id is distinct from old.video_id then
      raise exception 'Analysis job identity cannot change.' using errcode='55000';
    end if;
    -- Cancellation cannot carry a new attempt, retry schedule or identity.
    if (pg_catalog.to_jsonb(new)-array['status','stage','stage_started_at','stage_timestamps','last_heartbeat_at','lease_owner','lease_expires_at','failure_class','completed_at','updated_at'])
       = (pg_catalog.to_jsonb(old)-array['status','stage','stage_started_at','stage_timestamps','last_heartbeat_at','lease_owner','lease_expires_at','failure_class','completed_at','updated_at'])
       and new.status='cancelled' and new.stage='failed'
       and new.lease_owner is null and new.lease_expires_at is null
       and new.completed_at is not null and pg_catalog.isfinite(new.completed_at) then
      return new;
    end if;
  end if;
  perform public.assert_private_media_video_work(new.video_id);
  return new;
end;
$$;
revoke all on function public.fence_owner_analysis_job() from public,anon,authenticated;
grant execute on function public.fence_owner_analysis_job() to service_role;
create trigger fence_owner_analysis_job before insert or update on public.analysis_jobs
for each row execute function public.fence_owner_analysis_job();

create function public.fence_owner_analysis_result()
returns trigger language plpgsql security invoker set search_path=''
as $$
begin
  if tg_op='UPDATE' and (new.id is distinct from old.id or new.video_id is distinct from old.video_id
      or new.model_version is distinct from old.model_version) then
    raise exception 'Analysis result identity cannot change.' using errcode='55000';
  end if;
  perform public.assert_private_media_video_work(new.video_id);
  return new;
end;
$$;
revoke all on function public.fence_owner_analysis_result() from public,anon,authenticated;
grant execute on function public.fence_owner_analysis_result() to service_role;
create trigger fence_owner_analysis_result before insert or update on public.analysis_results
for each row execute function public.fence_owner_analysis_result();

create or replace function public.enqueue_video_analysis_job(
  p_video_id uuid,
  p_allow_completed boolean default false,
  p_max_user_jobs integer default 3,
  p_max_global_jobs integer default 20
)
returns table (id uuid, video_id uuid, status text, attempt_count integer)
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_job public.analysis_jobs%rowtype;
  v_video public.videos%rowtype;
begin
  -- One lock order across all submissions protects queue counts across users.
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('peso:analysis-admission', 0));
  select * into v_video from public.videos where videos.id = p_video_id for update;
  if not found then
    raise exception 'Video not found.' using errcode = 'P0001';
  end if;
  perform public.assert_active_private_media_owner(v_video.user_id);
  -- The same video lock serializes revocation and admission. Check before job
  -- reuse too: an old active row is not authority to revive revoked media.
  if v_video.discarded_at is not null or v_video.storage_state = 'pruned'
     or (v_video.expires_at is not null and
         (not pg_catalog.isfinite(v_video.expires_at) or v_video.expires_at <= pg_catalog.clock_timestamp()))
     or exists (select 1 from public.video_deletion_outbox o where o.video_id = p_video_id) then
    raise exception 'Video cannot be queued from this state.' using errcode = 'P0001';
  end if;
  select * into v_job from public.analysis_jobs
  where analysis_jobs.video_id = p_video_id and analysis_jobs.status in ('queued', 'processing', 'retry_wait')
  order by analysis_jobs.created_at desc limit 1 for update;
  -- A job lock can wait while wall-clock expiry advances. Transaction-start
  -- now() must not let a previously started request outlive its media deadline.
  if (v_video.expires_at is not null and
      (not pg_catalog.isfinite(v_video.expires_at) or v_video.expires_at <= pg_catalog.clock_timestamp()))
     or exists (select 1 from public.video_deletion_outbox o where o.video_id = p_video_id) then
    raise exception 'Video cannot be queued from this state.' using errcode = 'P0001';
  end if;
  if v_job.id is not null then
    return query select v_job.id, v_job.video_id, v_job.status, v_job.attempt_count;
    return;
  end if;
  if v_video.upload_reservation_id is null or not exists (
    select 1 from public.upload_reservations r
    where r.id = v_video.upload_reservation_id and r.user_id = v_video.user_id
      and r.video_id = v_video.id and r.state in ('verified', 'consumed')
      and r.blob_deleted_at is null
  ) then
    raise exception 'Only verified uploads can be queued.' using errcode = 'P0001';
  end if;
  if v_video.status not in ('uploaded', 'failed')
    and not (p_allow_completed and v_video.status = 'completed') then
    raise exception 'Video cannot be queued from this state.' using errcode = 'P0001';
  end if;
  if (select pg_catalog.count(*) from public.analysis_jobs j join public.videos v on v.id = j.video_id
      where v.user_id = v_video.user_id and j.status in ('queued', 'processing', 'retry_wait')) >= p_max_user_jobs
    or (select pg_catalog.count(*) from public.analysis_jobs where analysis_jobs.status in ('queued', 'processing', 'retry_wait')) >= p_max_global_jobs then
    raise exception 'Analysis queue capacity is full.' using errcode = 'P0001';
  end if;
  insert into public.analysis_jobs (video_id) values (p_video_id) returning * into v_job;
  update public.videos set status = 'queued' where videos.id = p_video_id;
  update public.upload_reservations set state = 'consumed', consumed_at = coalesce(consumed_at, pg_catalog.now())
  where upload_reservations.id = v_video.upload_reservation_id;
  return query select v_job.id, v_job.video_id, v_job.status, v_job.attempt_count;
end;
$$;
revoke all on function public.enqueue_video_analysis_job(uuid,boolean,integer,integer) from public,anon,authenticated;
grant execute on function public.enqueue_video_analysis_job(uuid,boolean,integer,integer) to service_role;

create or replace function public.lock_video_analysis_attempt(
  p_video_id uuid, p_job_id uuid, p_worker_id text, p_attempt_count integer
)
returns public.videos
language plpgsql security invoker set search_path = '' set lock_timeout='2s'
as $$
declare
  v_video public.videos%rowtype;
  v_job public.analysis_jobs%rowtype;
  v_owner uuid;
  v_deleting_at timestamptz;
begin
  if p_video_id is null or p_job_id is null or p_worker_id is null
     or pg_catalog.btrim(p_worker_id) = '' or p_attempt_count is null or p_attempt_count < 1 then
    return null;
  end if;
  -- Read the binding without a child lock, then serialize with deletion first.
  select v.user_id into v_owner from public.videos v where v.id=p_video_id;
  if not found or v_owner is null then return null; end if;
  select o.deleting_at into v_deleting_at from public.private_media_owners o
    where o.user_id=v_owner for update;
  if not found or v_deleting_at is not null then return null; end if;
  select * into v_video from public.videos v where v.id=p_video_id for update;
  if not found or v_video.user_id is distinct from v_owner then return null; end if;
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

create or replace function public.claim_video_analysis_job(p_worker_id text,p_lease_seconds integer default 3600)
returns table(id uuid,video_id uuid,status text,attempt_count integer)
language plpgsql security invoker set search_path=''
as $$
declare
  v_candidate public.analysis_jobs%rowtype;
  v_job public.analysis_jobs%rowtype;
  v_video public.videos%rowtype;
  v_owner_state text;
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
    v_owner_state:=public.private_media_owner_work_state(v_video.user_id);
    if v_owner_state='busy' then continue; end if;
    if v_owner_state='unavailable' or v_video.discarded_at is not null or v_video.storage_state='pruned'
       or (v_video.expires_at is not null and (not pg_catalog.isfinite(v_video.expires_at)
           or v_video.expires_at<=pg_catalog.clock_timestamp()))
       or exists(select 1 from public.video_deletion_outbox o where o.video_id=v_video.id) then
      -- Leaving an unusable queued job active would pin both quota and retention.
      update public.analysis_jobs j set status='cancelled',stage='failed',
        stage_started_at=pg_catalog.clock_timestamp(),
        stage_timestamps=j.stage_timestamps||pg_catalog.jsonb_build_object('failed',pg_catalog.clock_timestamp()),
        lease_owner=null,lease_expires_at=null,completed_at=pg_catalog.clock_timestamp(),
        failure_class=case when v_owner_state='unavailable' then 'owner_unavailable' else 'video_revoked' end,last_heartbeat_at=pg_catalog.clock_timestamp()
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
  v_owner_state text;
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
    v_owner_state:=public.private_media_owner_work_state(v_video.user_id);
    if v_owner_state='busy' then continue; end if;
    if v_owner_state='unavailable' or v_video.discarded_at is not null or v_video.storage_state='pruned'
       or (v_video.expires_at is not null and (not pg_catalog.isfinite(v_video.expires_at)
           or v_video.expires_at<=pg_catalog.clock_timestamp()))
       or exists(select 1 from public.video_deletion_outbox o where o.video_id=v_video.id) then
      update public.analysis_jobs j set status='cancelled',stage='failed',
        stage_started_at=pg_catalog.clock_timestamp(),
        stage_timestamps=j.stage_timestamps||pg_catalog.jsonb_build_object('failed',pg_catalog.clock_timestamp()),
        lease_owner=null,lease_expires_at=null,completed_at=pg_catalog.clock_timestamp(),
        failure_class=case when v_owner_state='unavailable' then 'owner_unavailable' else 'video_revoked' end,last_heartbeat_at=pg_catalog.clock_timestamp()
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

-- Keep the existing cleanup RPC compatible with the exact cancel-only guard.
create or replace function public.cancel_video_analysis_jobs(p_video_id uuid)
returns integer language plpgsql security invoker set search_path=''
as $$
declare v_count integer;
begin
  update public.analysis_jobs j set status='cancelled',stage='failed',
    stage_started_at=pg_catalog.clock_timestamp(),
    stage_timestamps=j.stage_timestamps||pg_catalog.jsonb_build_object('failed',pg_catalog.clock_timestamp()),
    lease_owner=null,lease_expires_at=null,completed_at=pg_catalog.clock_timestamp(),
    last_heartbeat_at=pg_catalog.clock_timestamp(),failure_class='video_cancelled'
    where j.video_id=p_video_id and j.status in ('queued','processing','retry_wait');
  get diagnostics v_count=row_count;
  return v_count;
end;
$$;
revoke all on function public.cancel_video_analysis_jobs(uuid) from public,anon,authenticated;
grant execute on function public.cancel_video_analysis_jobs(uuid) to service_role;

commit;
