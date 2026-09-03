alter table public.analysis_jobs
  add column if not exists stage text not null default 'queued',
  add column if not exists stage_started_at timestamptz not null default timezone('utc', now()),
  add column if not exists stage_timestamps jsonb not null default '{}'::jsonb,
  add column if not exists last_heartbeat_at timestamptz,
  add column if not exists failure_class text;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'analysis_jobs_stage_check'
      and conrelid = 'public.analysis_jobs'::regclass
  ) then
    alter table public.analysis_jobs
      add constraint analysis_jobs_stage_check
      check (stage in ('queued', 'downloading', 'pose', 'barbell_tracking', 'saving', 'ready', 'failed'));
  end if;
end;
$$;

update public.analysis_jobs
set stage = case
      when status = 'completed' then 'ready'
      when status in ('failed', 'cancelled') then 'failed'
      when status = 'processing' then 'downloading'
      else 'queued'
    end,
    stage_started_at = coalesce(updated_at, created_at),
    stage_timestamps = jsonb_build_object(
      case
        when status = 'completed' then 'ready'
        when status in ('failed', 'cancelled') then 'failed'
        when status = 'processing' then 'downloading'
        else 'queued'
      end,
      coalesce(updated_at, created_at)
    )
where stage_timestamps = '{}'::jsonb;

create or replace function public.initialize_analysis_job_observability()
returns trigger
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
  new.stage_started_at := coalesce(new.stage_started_at, new.created_at, timezone('utc', now()));
  if new.stage_timestamps = '{}'::jsonb then
    new.stage_timestamps := jsonb_build_object(new.stage, new.stage_started_at);
  end if;
  return new;
end;
$$;

drop trigger if exists initialize_analysis_job_observability on public.analysis_jobs;
create trigger initialize_analysis_job_observability
before insert on public.analysis_jobs
for each row
execute function public.initialize_analysis_job_observability();

create or replace function public.claim_video_analysis_job(
  p_worker_id text,
  p_lease_seconds integer default 3600
)
returns table (
  id uuid,
  video_id uuid,
  status text,
  attempt_count integer
)
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
  if length(trim(p_worker_id)) = 0 then
    raise exception 'Worker ID is required.' using errcode = 'P0001';
  end if;

  return query
  with candidate as (
    select analysis_jobs.id
    from public.analysis_jobs
    join public.videos on videos.id = analysis_jobs.video_id
    where analysis_jobs.job_type = 'video_analysis'
      and analysis_jobs.status in ('queued', 'retry_wait')
      and analysis_jobs.available_at <= timezone('utc', now())
      and videos.discarded_at is null
    order by analysis_jobs.available_at, analysis_jobs.created_at
    for update of analysis_jobs skip locked
    limit 1
  ),
  claimed as (
    update public.analysis_jobs
    set status = 'processing',
        stage = 'downloading',
        stage_started_at = timezone('utc', now()),
        stage_timestamps = analysis_jobs.stage_timestamps
          || jsonb_build_object('downloading', timezone('utc', now())),
        attempt_count = analysis_jobs.attempt_count + 1,
        lease_owner = trim(p_worker_id),
        lease_expires_at = timezone('utc', now())
          + make_interval(secs => least(greatest(p_lease_seconds, 60), 21600)),
        last_heartbeat_at = timezone('utc', now()),
        last_error = null,
        failure_class = null
    from candidate
    where analysis_jobs.id = candidate.id
    returning analysis_jobs.id, analysis_jobs.video_id, analysis_jobs.status, analysis_jobs.attempt_count
  ),
  mark_video_processing as (
    update public.videos
    set status = 'processing'
    from claimed
    where videos.id = claimed.video_id
  )
  select claimed.id, claimed.video_id, claimed.status, claimed.attempt_count
  from claimed;
end;
$$;

create or replace function public.report_video_analysis_job_progress(
  p_job_id uuid,
  p_worker_id text,
  p_stage text
)
returns boolean
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
  if p_stage not in ('downloading', 'pose', 'barbell_tracking', 'saving') then
    raise exception 'Invalid analysis stage %.', p_stage using errcode = 'P0001';
  end if;

  update public.analysis_jobs
  set stage = p_stage,
      stage_started_at = timezone('utc', now()),
      stage_timestamps = analysis_jobs.stage_timestamps
        || jsonb_build_object(p_stage, timezone('utc', now())),
      last_heartbeat_at = timezone('utc', now())
  where analysis_jobs.id = p_job_id
    and analysis_jobs.status = 'processing'
    and analysis_jobs.lease_owner = trim(p_worker_id)
    and analysis_jobs.lease_expires_at > timezone('utc', now());

  return found;
end;
$$;

create or replace function public.renew_video_analysis_job_lease(
  p_job_id uuid,
  p_worker_id text,
  p_lease_seconds integer default 3600
)
returns boolean
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
  update public.analysis_jobs
  set lease_expires_at = timezone('utc', now())
        + make_interval(secs => least(greatest(p_lease_seconds, 60), 21600)),
      last_heartbeat_at = timezone('utc', now())
  where analysis_jobs.id = p_job_id
    and analysis_jobs.status = 'processing'
    and analysis_jobs.lease_owner = trim(p_worker_id)
    and analysis_jobs.lease_expires_at > timezone('utc', now());

  return found;
end;
$$;

create or replace function public.complete_video_analysis_job(
  p_job_id uuid,
  p_worker_id text
)
returns boolean
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_video_id uuid;
begin
  update public.analysis_jobs
  set status = 'completed',
      stage = 'ready',
      stage_started_at = timezone('utc', now()),
      stage_timestamps = analysis_jobs.stage_timestamps
        || jsonb_build_object('ready', timezone('utc', now())),
      last_heartbeat_at = timezone('utc', now()),
      lease_owner = null,
      lease_expires_at = null,
      completed_at = timezone('utc', now())
  where analysis_jobs.id = p_job_id
    and analysis_jobs.status = 'processing'
    and analysis_jobs.lease_owner = trim(p_worker_id)
  returning analysis_jobs.video_id into v_video_id;

  if not found then
    return false;
  end if;

  update public.videos
  set status = 'completed'
  where videos.id = v_video_id
    and videos.discarded_at is null;

  return true;
end;
$$;

create or replace function public.record_video_analysis_job_failure(
  p_job_id uuid,
  p_worker_id text,
  p_error text,
  p_failure_class text,
  p_retryable boolean
)
returns text
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_job public.analysis_jobs%rowtype;
  v_retry_delay_seconds integer;
begin
  select *
  into v_job
  from public.analysis_jobs
  where analysis_jobs.id = p_job_id
    and analysis_jobs.status = 'processing'
    and analysis_jobs.lease_owner = trim(p_worker_id)
  for update;

  if not found then
    return null;
  end if;

  if not p_retryable or v_job.attempt_count >= v_job.max_attempts then
    update public.analysis_jobs
    set status = 'failed',
        stage = 'failed',
        stage_started_at = timezone('utc', now()),
        stage_timestamps = analysis_jobs.stage_timestamps
          || jsonb_build_object('failed', timezone('utc', now())),
        last_heartbeat_at = timezone('utc', now()),
        lease_owner = null,
        lease_expires_at = null,
        last_error = left(coalesce(p_error, 'Unknown analysis failure.'), 2000),
        failure_class = nullif(left(coalesce(p_failure_class, 'unknown'), 120), ''),
        completed_at = timezone('utc', now())
    where analysis_jobs.id = v_job.id;

    update public.videos
    set status = 'failed'
    where videos.id = v_job.video_id
      and videos.discarded_at is null;

    return 'failed';
  end if;

  v_retry_delay_seconds := least(300, greatest(5, power(2, least(v_job.attempt_count, 8))::integer));
  update public.analysis_jobs
  set status = 'retry_wait',
      stage = 'queued',
      stage_started_at = timezone('utc', now()),
      stage_timestamps = analysis_jobs.stage_timestamps
        || jsonb_build_object('queued', timezone('utc', now())),
      available_at = timezone('utc', now()) + make_interval(secs => v_retry_delay_seconds),
      last_heartbeat_at = timezone('utc', now()),
      lease_owner = null,
      lease_expires_at = null,
      last_error = left(coalesce(p_error, 'Unknown analysis failure.'), 2000),
      failure_class = nullif(left(coalesce(p_failure_class, 'unknown'), 120), '')
  where analysis_jobs.id = v_job.id;

  update public.videos
  set status = 'queued'
  where videos.id = v_job.video_id
    and videos.discarded_at is null;

  return 'retry_wait';
end;
$$;

create or replace function public.recover_expired_video_analysis_jobs()
returns table (retried_count integer, failed_count integer)
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_job public.analysis_jobs%rowtype;
  v_retried_count integer := 0;
  v_failed_count integer := 0;
  v_retry_delay_seconds integer;
begin
  for v_job in
    select *
    from public.analysis_jobs
    where analysis_jobs.status = 'processing'
      and analysis_jobs.lease_expires_at <= timezone('utc', now())
    for update skip locked
  loop
    if v_job.attempt_count >= v_job.max_attempts then
      update public.analysis_jobs
      set status = 'failed', stage = 'failed',
          stage_started_at = timezone('utc', now()),
          stage_timestamps = analysis_jobs.stage_timestamps
            || jsonb_build_object('failed', timezone('utc', now())),
          lease_owner = null, lease_expires_at = null,
          last_error = 'Worker lease expired before analysis completed.',
          failure_class = 'worker_lease_expired',
          completed_at = timezone('utc', now())
      where analysis_jobs.id = v_job.id;
      update public.videos set status = 'failed'
      where videos.id = v_job.video_id and videos.discarded_at is null;
      v_failed_count := v_failed_count + 1;
    else
      v_retry_delay_seconds := least(300, greatest(5, power(2, least(v_job.attempt_count, 8))::integer));
      update public.analysis_jobs
      set status = 'retry_wait', stage = 'queued',
          stage_started_at = timezone('utc', now()),
          stage_timestamps = analysis_jobs.stage_timestamps
            || jsonb_build_object('queued', timezone('utc', now())),
          available_at = timezone('utc', now()) + make_interval(secs => v_retry_delay_seconds),
          lease_owner = null, lease_expires_at = null,
          last_error = 'Worker lease expired before analysis completed.',
          failure_class = 'worker_lease_expired'
      where analysis_jobs.id = v_job.id;
      update public.videos set status = 'queued'
      where videos.id = v_job.video_id and videos.discarded_at is null;
      v_retried_count := v_retried_count + 1;
    end if;
  end loop;
  return query select v_retried_count, v_failed_count;
end;
$$;

revoke execute on function public.initialize_analysis_job_observability() from public, anon, authenticated;
revoke execute on function public.report_video_analysis_job_progress(uuid, text, text) from public, anon, authenticated;
revoke execute on function public.record_video_analysis_job_failure(uuid, text, text, text, boolean) from public, anon, authenticated;
grant execute on function public.report_video_analysis_job_progress(uuid, text, text) to service_role;
grant execute on function public.record_video_analysis_job_failure(uuid, text, text, text, boolean) to service_role;
