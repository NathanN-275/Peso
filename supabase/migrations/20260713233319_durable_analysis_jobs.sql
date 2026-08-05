create table if not exists public.analysis_jobs (
  id uuid primary key default gen_random_uuid(),
  video_id uuid not null references public.videos (id) on delete cascade,
  job_type text not null default 'video_analysis'
    check (job_type = 'video_analysis'),
  status text not null default 'queued'
    check (status in ('queued', 'processing', 'retry_wait', 'completed', 'failed', 'cancelled')),
  attempt_count integer not null default 0 check (attempt_count >= 0),
  max_attempts integer not null default 3 check (max_attempts > 0),
  available_at timestamptz not null default timezone('utc', now()),
  lease_owner text,
  lease_expires_at timestamptz,
  last_error text,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  completed_at timestamptz,
  check (
    (status = 'processing' and lease_owner is not null and lease_expires_at is not null)
    or (status <> 'processing' and lease_owner is null and lease_expires_at is null)
  )
);

create unique index if not exists analysis_jobs_one_active_video_idx
  on public.analysis_jobs (video_id, job_type)
  where status in ('queued', 'processing', 'retry_wait');

create index if not exists analysis_jobs_available_idx
  on public.analysis_jobs (available_at, created_at)
  where status in ('queued', 'retry_wait');

create index if not exists analysis_jobs_expired_lease_idx
  on public.analysis_jobs (lease_expires_at)
  where status = 'processing';

-- Recover work that was queued by the previous in-process task runner before
-- this migration was applied. Deploy the worker after draining old API tasks.
insert into public.analysis_jobs (video_id, status)
select videos.id, 'queued'
from public.videos
where videos.status in ('queued', 'processing')
  and videos.discarded_at is null
on conflict do nothing;

drop trigger if exists set_analysis_jobs_updated_at on public.analysis_jobs;
create trigger set_analysis_jobs_updated_at
before update on public.analysis_jobs
for each row
execute function public.set_updated_at();

alter table public.analysis_jobs enable row level security;

-- Analysis jobs are backend-only. The service-role client invokes the RPCs below;
-- anonymous and user JWT clients cannot read or mutate queued work directly.
revoke all on table public.analysis_jobs from anon, authenticated;

create or replace function public.enqueue_video_analysis_job(
  p_video_id uuid,
  p_allow_completed boolean default false
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
declare
  v_job public.analysis_jobs%rowtype;
  v_video_status text;
begin
  -- The advisory lock serializes requests for one video across API instances.
  perform pg_advisory_xact_lock(hashtextextended('video_analysis:' || p_video_id::text, 0));

  select videos.status
  into v_video_status
  from public.videos
  where videos.id = p_video_id
  for update;

  if not found then
    raise exception 'Video % was not found.', p_video_id using errcode = 'P0001';
  end if;

  select *
  into v_job
  from public.analysis_jobs
  where analysis_jobs.video_id = p_video_id
    and analysis_jobs.job_type = 'video_analysis'
    and analysis_jobs.status in ('queued', 'processing', 'retry_wait')
  order by analysis_jobs.created_at desc
  limit 1
  for update;

  if found then
    return query select v_job.id, v_job.video_id, v_job.status, v_job.attempt_count;
    return;
  end if;

  if v_video_status not in ('uploaded', 'failed', 'queued')
    and not (p_allow_completed and v_video_status = 'completed') then
    raise exception 'Video % cannot be queued from status %.', p_video_id, v_video_status
      using errcode = 'P0001';
  end if;

  insert into public.analysis_jobs (video_id)
  values (p_video_id)
  returning * into v_job;

  update public.videos
  set status = 'queued'
  where videos.id = p_video_id;

  return query select v_job.id, v_job.video_id, v_job.status, v_job.attempt_count;
end;
$$;

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
        attempt_count = analysis_jobs.attempt_count + 1,
        lease_owner = trim(p_worker_id),
        lease_expires_at = timezone('utc', now())
          + make_interval(secs => least(greatest(p_lease_seconds, 60), 21600)),
        last_error = null
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
    + make_interval(secs => least(greatest(p_lease_seconds, 60), 21600))
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

create or replace function public.fail_video_analysis_job(
  p_job_id uuid,
  p_worker_id text,
  p_error text
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

  if v_job.attempt_count >= v_job.max_attempts then
    update public.analysis_jobs
    set status = 'failed',
        lease_owner = null,
        lease_expires_at = null,
        last_error = left(coalesce(p_error, 'Unknown analysis failure.'), 2000),
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
      available_at = timezone('utc', now()) + make_interval(secs => v_retry_delay_seconds),
      lease_owner = null,
      lease_expires_at = null,
      last_error = left(coalesce(p_error, 'Unknown analysis failure.'), 2000)
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
      set status = 'failed',
          lease_owner = null,
          lease_expires_at = null,
          last_error = 'Worker lease expired before analysis completed.',
          completed_at = timezone('utc', now())
      where analysis_jobs.id = v_job.id;

      update public.videos
      set status = 'failed'
      where videos.id = v_job.video_id
        and videos.discarded_at is null;

      v_failed_count := v_failed_count + 1;
    else
      v_retry_delay_seconds := least(300, greatest(5, power(2, least(v_job.attempt_count, 8))::integer));

      update public.analysis_jobs
      set status = 'retry_wait',
          available_at = timezone('utc', now()) + make_interval(secs => v_retry_delay_seconds),
          lease_owner = null,
          lease_expires_at = null,
          last_error = 'Worker lease expired before analysis completed.'
      where analysis_jobs.id = v_job.id;

      update public.videos
      set status = 'queued'
      where videos.id = v_job.video_id
        and videos.discarded_at is null;

      v_retried_count := v_retried_count + 1;
    end if;
  end loop;

  return query select v_retried_count, v_failed_count;
end;
$$;

create or replace function public.cancel_video_analysis_jobs(p_video_id uuid)
returns integer
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_cancelled_count integer;
begin
  update public.analysis_jobs
  set status = 'cancelled',
      lease_owner = null,
      lease_expires_at = null,
      completed_at = timezone('utc', now())
  where analysis_jobs.video_id = p_video_id
    and analysis_jobs.status in ('queued', 'processing', 'retry_wait');

  get diagnostics v_cancelled_count = row_count;
  return v_cancelled_count;
end;
$$;

revoke execute on function public.enqueue_video_analysis_job(uuid, boolean) from public, anon, authenticated;
revoke execute on function public.claim_video_analysis_job(text, integer) from public, anon, authenticated;
revoke execute on function public.renew_video_analysis_job_lease(uuid, text, integer) from public, anon, authenticated;
revoke execute on function public.complete_video_analysis_job(uuid, text) from public, anon, authenticated;
revoke execute on function public.fail_video_analysis_job(uuid, text, text) from public, anon, authenticated;
revoke execute on function public.recover_expired_video_analysis_jobs() from public, anon, authenticated;
revoke execute on function public.cancel_video_analysis_jobs(uuid) from public, anon, authenticated;

grant execute on function public.enqueue_video_analysis_job(uuid, boolean) to service_role;
grant execute on function public.claim_video_analysis_job(text, integer) to service_role;
grant execute on function public.renew_video_analysis_job_lease(uuid, text, integer) to service_role;
grant execute on function public.complete_video_analysis_job(uuid, text) to service_role;
grant execute on function public.fail_video_analysis_job(uuid, text, text) to service_role;
grant execute on function public.recover_expired_video_analysis_jobs() to service_role;
grant execute on function public.cancel_video_analysis_jobs(uuid) to service_role;
