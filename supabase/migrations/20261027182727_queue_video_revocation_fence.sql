-- Requires the retention outbox; leave revoked/expired sources outside queue admission.
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
revoke execute on function public.enqueue_video_analysis_job(uuid, boolean, integer, integer) from public, anon, authenticated;
grant execute on function public.enqueue_video_analysis_job(uuid, boolean, integer, integer) to service_role;
