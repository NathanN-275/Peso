-- Apply in staging first. Old client storage policies are removed by the explicit
-- security cutover script only after the reservation client has been validated.
create table if not exists public.upload_admission_control (
  id integer primary key check (id = 1),
  enabled boolean not null default true,
  disabled_reason text,
  updated_at timestamptz not null default now()
);
insert into public.upload_admission_control (id) values (1) on conflict (id) do nothing;
alter table public.upload_admission_control enable row level security;
revoke all on table public.upload_admission_control from public, anon, authenticated;
grant select, update on table public.upload_admission_control to service_role;

create table if not exists public.upload_reservations (
  id uuid primary key,
  -- Keep a cleanup tombstone after account deletion until every issued SAS has
  -- expired; otherwise a token could recreate an object with no cleanup record.
  user_id uuid references auth.users (id) on delete set null,
  blob_path text not null unique,
  file_name text not null,
  content_type text not null,
  requested_bytes bigint not null check (requested_bytes > 0),
  actual_bytes bigint check (actual_bytes > 0 and actual_bytes <= requested_bytes),
  state text not null default 'issued'
    check (state in ('issued', 'uploaded', 'verified', 'rejected', 'consumed', 'expired')),
  source_type text not null check (source_type in ('camera', 'camera_roll')),
  exercise_type text not null,
  view_type text not null check (view_type in ('side', 'front')),
  client_duration_ms integer,
  tracking_setup jsonb,
  media_metadata jsonb,
  video_id uuid references public.videos (id) on delete set null,
  rejection_reason text,
  expires_at timestamptz not null,
  uploaded_at timestamptz,
  validation_owner uuid,
  validation_expires_at timestamptz,
  verified_at timestamptz,
  consumed_at timestamptz,
  blob_deleted_at timestamptz,
  cleanup_confirmed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (split_part(blob_path, '/', 1) = user_id::text),
  check (split_part(blob_path, '/', 2) = 'source'),
  check (blob_path !~ '(^/|//|\\|/\.\.?(/|$))')
);

create index if not exists upload_reservations_owner_created_idx
  on public.upload_reservations (user_id, created_at);
create index if not exists upload_reservations_cleanup_idx
  on public.upload_reservations (expires_at)
  where cleanup_confirmed_at is null;

alter table public.upload_reservations enable row level security;
revoke all on table public.upload_reservations from public, anon, authenticated;
grant select, insert, update, delete on table public.upload_reservations to service_role;

alter table public.videos
  add column if not exists upload_reservation_id uuid references public.upload_reservations (id),
  add column if not exists media_metadata jsonb;
create unique index if not exists videos_one_upload_reservation_idx
  on public.videos (upload_reservation_id) where upload_reservation_id is not null;

drop trigger if exists set_upload_reservations_updated_at on public.upload_reservations;
create trigger set_upload_reservations_updated_at
before update on public.upload_reservations
for each row execute function public.set_updated_at();

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
  if p_requested_bytes <= 0 or p_expires_at <= now()
    or p_expires_at > now() + interval '15 minutes'
    or least(p_max_user_active, p_max_global_active, p_max_user_bytes, p_max_global_bytes, p_max_user_hourly) <= 0 then
    raise exception 'Invalid reservation limits.' using errcode = '22023';
  end if;

  -- One transaction lock serializes both user and global admission across API replicas.
  -- Expired but not-yet-deleted blobs still consume bytes until cleanup confirms deletion.
  perform pg_advisory_xact_lock(hashtextextended('peso:upload-capacity', 0));
  if not exists (select 1 from public.upload_admission_control where id = 1 and enabled) then
    raise exception 'Upload admission is disabled.' using errcode = 'P0002';
  end if;
  select
    count(*) filter (where state = 'verified' or (state in ('issued', 'uploaded') and expires_at > now())),
    coalesce(sum(coalesce(actual_bytes, requested_bytes)) filter (where cleanup_confirmed_at is null), 0),
    count(*) filter (where user_id = p_user_id and (state = 'verified' or (state in ('issued', 'uploaded') and expires_at > now()))),
    coalesce(sum(coalesce(actual_bytes, requested_bytes)) filter (where user_id = p_user_id and cleanup_confirmed_at is null), 0)
  into v_global_count, v_global_bytes, v_user_count, v_user_bytes
  from public.upload_reservations;

  if v_user_count >= p_max_user_active or v_user_bytes + p_requested_bytes > p_max_user_bytes
    or v_global_count >= p_max_global_active or v_global_bytes + p_requested_bytes > p_max_global_bytes
    or (select count(*) from public.upload_reservations where user_id = p_user_id and created_at > now() - interval '1 hour') >= p_max_user_hourly then
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

create or replace function public.disable_video_upload_admission()
returns void
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended('peso:upload-capacity', 0));
  update public.upload_admission_control
  set enabled = false, disabled_reason = 'student_credit_90_percent', updated_at = now()
  where id = 1;
end;
$$;
revoke execute on function public.disable_video_upload_admission() from public, anon, authenticated;
grant execute on function public.disable_video_upload_admission() to service_role;

create or replace function public.mark_video_upload_received(p_reservation_id uuid, p_user_id uuid, p_validation_owner uuid)
returns setof public.upload_reservations
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended('peso:media-validation', 0));
  if (select count(*) from public.upload_reservations where validation_expires_at > now()) >= 2 then
    raise exception 'Media validation capacity is full.' using errcode = 'P0001';
  end if;
  return query update public.upload_reservations
  set state = 'uploaded', uploaded_at = coalesce(uploaded_at, now()),
      validation_owner = p_validation_owner, validation_expires_at = now() + interval '5 minutes'
  where id = p_reservation_id and user_id = p_user_id
    and state in ('issued', 'uploaded') and expires_at > now()
    and (validation_expires_at is null or validation_expires_at <= now())
  returning *;
end;
$$;

create or replace function public.verify_video_upload(
  p_reservation_id uuid,
  p_user_id uuid,
  p_actual_bytes bigint,
  p_media_metadata jsonb,
  p_video_expires_at timestamptz,
  p_validation_owner uuid
)
returns table (video_id uuid)
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_reservation public.upload_reservations%rowtype;
  v_video_id uuid;
begin
  select * into v_reservation from public.upload_reservations
  where id = p_reservation_id and user_id = p_user_id for update;
  if not found then
    raise exception 'Upload reservation not found.' using errcode = 'P0001';
  end if;
  if v_reservation.state in ('verified', 'consumed') and v_reservation.video_id is not null then
    return query select v_reservation.video_id;
    return;
  end if;
  if v_reservation.state <> 'uploaded' or v_reservation.expires_at <= now()
    or v_reservation.validation_owner is distinct from p_validation_owner
    or v_reservation.validation_expires_at <= now()
    or p_actual_bytes <= 0 or p_actual_bytes > v_reservation.requested_bytes
    or coalesce((p_media_metadata->>'duration_ms')::integer, 0) <= 0
    or coalesce((p_media_metadata->>'frame_count')::integer, 0) <= 0 then
    raise exception 'Upload reservation cannot be verified.' using errcode = 'P0001';
  end if;

  v_video_id := gen_random_uuid();
  insert into public.videos (
    id, user_id, storage_path, source_type, exercise_type, view_type, status,
    duration_ms, fps, save_state, expires_at, original_size_bytes,
    uploaded_size_bytes, was_compressed, storage_state, tracking_setup,
    quality_preflight_required, upload_reservation_id, media_metadata
  ) values (
    v_video_id, p_user_id, v_reservation.blob_path, v_reservation.source_type,
    v_reservation.exercise_type, v_reservation.view_type, 'uploaded',
    (p_media_metadata->>'duration_ms')::integer, (p_media_metadata->>'fps')::numeric,
    'pending', p_video_expires_at, p_actual_bytes, p_actual_bytes, false, 'available',
    v_reservation.tracking_setup,
    v_reservation.view_type = 'side' and v_reservation.exercise_type like '%squat%',
    p_reservation_id, p_media_metadata
  );
  update public.upload_reservations
  set state = 'verified', verified_at = now(), actual_bytes = p_actual_bytes,
      media_metadata = p_media_metadata, video_id = v_video_id,
      validation_owner = null, validation_expires_at = null
  where id = p_reservation_id;
  return query select v_video_id;
end;
$$;

create or replace function public.reject_video_upload(p_reservation_id uuid, p_user_id uuid, p_reason text)
returns void
language sql
security invoker
set search_path = public, pg_temp
as $$
  update public.upload_reservations
  set state = case when expires_at <= now() then 'expired' else 'rejected' end,
      rejection_reason = left(p_reason, 80), validation_owner = null, validation_expires_at = null
  where id = p_reservation_id and user_id = p_user_id and state in ('issued', 'uploaded');
$$;

create or replace function public.expire_video_upload_reservations(p_limit integer default 100)
returns table (reservation_id uuid, blob_path text)
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
  update public.upload_reservations
  set state = 'expired', rejection_reason = 'reservation_expired'
  where state in ('issued', 'uploaded') and expires_at <= now();
  return query select r.id, r.blob_path from public.upload_reservations r
  where r.expires_at <= now() and r.cleanup_confirmed_at is null
    and (r.state in ('expired', 'rejected') or r.blob_deleted_at is not null
      or (r.state in ('verified', 'consumed') and r.video_id is null))
  order by r.expires_at limit least(greatest(p_limit, 1), 1000);
end;
$$;

-- The admission and validation RPCs are backend-only: no user JWT can mint or
-- verify capacity, even if PostgREST exposes their names.
revoke execute on function public.reserve_video_upload(uuid, uuid, text, text, text, bigint, timestamptz, text, text, text, integer, jsonb, integer, bigint, integer, bigint, integer) from public, anon, authenticated;
revoke execute on function public.mark_video_upload_received(uuid, uuid, uuid) from public, anon, authenticated;
revoke execute on function public.verify_video_upload(uuid, uuid, bigint, jsonb, timestamptz, uuid) from public, anon, authenticated;
revoke execute on function public.reject_video_upload(uuid, uuid, text) from public, anon, authenticated;
revoke execute on function public.expire_video_upload_reservations(integer) from public, anon, authenticated;
grant execute on function public.reserve_video_upload(uuid, uuid, text, text, text, bigint, timestamptz, text, text, text, integer, jsonb, integer, bigint, integer, bigint, integer) to service_role;
grant execute on function public.mark_video_upload_received(uuid, uuid, uuid) to service_role;
grant execute on function public.verify_video_upload(uuid, uuid, bigint, jsonb, timestamptz, uuid) to service_role;
grant execute on function public.reject_video_upload(uuid, uuid, text) to service_role;
grant execute on function public.expire_video_upload_reservations(integer) to service_role;

-- Replace the old signature so PostgREST cannot select a bypassing overload.
drop function if exists public.enqueue_video_analysis_job(uuid, boolean);
create function public.enqueue_video_analysis_job(
  p_video_id uuid,
  p_allow_completed boolean default false,
  p_max_user_jobs integer default 3,
  p_max_global_jobs integer default 20
)
returns table (id uuid, video_id uuid, status text, attempt_count integer)
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
declare
  v_job public.analysis_jobs%rowtype;
  v_video public.videos%rowtype;
begin
  -- One lock order across all submissions protects queue counts across users.
  perform pg_advisory_xact_lock(hashtextextended('peso:analysis-admission', 0));
  select * into v_video from public.videos where videos.id = p_video_id for update;
  if not found then
    raise exception 'Video not found.' using errcode = 'P0001';
  end if;
  select * into v_job from public.analysis_jobs
  where analysis_jobs.video_id = p_video_id and analysis_jobs.status in ('queued', 'processing', 'retry_wait')
  order by analysis_jobs.created_at desc limit 1 for update;
  if found then
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
  if (select count(*) from public.analysis_jobs j join public.videos v on v.id = j.video_id
      where v.user_id = v_video.user_id and j.status in ('queued', 'processing', 'retry_wait')) >= p_max_user_jobs
    or (select count(*) from public.analysis_jobs where analysis_jobs.status in ('queued', 'processing', 'retry_wait')) >= p_max_global_jobs then
    raise exception 'Analysis queue capacity is full.' using errcode = 'P0001';
  end if;
  insert into public.analysis_jobs (video_id) values (p_video_id) returning * into v_job;
  update public.videos set status = 'queued' where videos.id = p_video_id;
  update public.upload_reservations set state = 'consumed', consumed_at = coalesce(consumed_at, now())
  where upload_reservations.id = v_video.upload_reservation_id;
  return query select v_job.id, v_job.video_id, v_job.status, v_job.attempt_count;
end;
$$;
revoke execute on function public.enqueue_video_analysis_job(uuid, boolean, integer, integer) from public, anon, authenticated;
grant execute on function public.enqueue_video_analysis_job(uuid, boolean, integer, integer) to service_role;
