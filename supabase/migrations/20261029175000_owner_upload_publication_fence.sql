begin;
set local lock_timeout = '2s';

-- Freeze both sources until backfill and guards are installed, preserving old
-- tombstones. No live row can slip between the backfill and trigger creation.
lock table public.upload_reservations, public.videos in share row exclusive mode nowait;
insert into public.private_media_owners(user_id)
  select v.user_id from public.videos v where v.user_id is not null
  union select r.user_id from public.upload_reservations r where r.user_id is not null
  on conflict do nothing;

-- Called before child/global locks by the three reservation RPCs. Only initial
-- reservation admission creates a missing owner row.
create function public.lock_active_private_media_owner(p_user_id uuid, p_create boolean default false)
returns void language plpgsql security invoker set search_path = ''
as $$
declare v_at timestamptz;
begin
  if p_user_id is null or p_user_id = '00000000-0000-0000-0000-000000000000'::uuid or p_create is null then
    raise exception 'A nonzero owner is required.' using errcode = '22023';
  end if;
  if p_create then
    insert into public.private_media_owners(user_id) values(p_user_id) on conflict do nothing;
  end if;
  select o.deleting_at into v_at from public.private_media_owners o where o.user_id=p_user_id for update;
  if not found or v_at is not null then
    raise exception 'Owner is unavailable for new media work.' using errcode = '55000';
  end if;
end;
$$;
revoke all on function public.lock_active_private_media_owner(uuid,boolean) from public,anon,authenticated;
grant execute on function public.lock_active_private_media_owner(uuid,boolean) to service_role;

-- Direct table writes already hold a child lock. Do not wait for an owner or
-- insert one here: a future owner-first cleanup may be waiting for that child.
create function public.assert_active_private_media_owner(p_user_id uuid)
returns void language plpgsql security invoker set search_path = ''
as $$
declare v_at timestamptz;
begin
  if p_user_id is null or p_user_id = '00000000-0000-0000-0000-000000000000'::uuid then
    raise exception 'A nonzero owner is required.' using errcode = '22023';
  end if;
  select o.deleting_at into v_at from public.private_media_owners o where o.user_id=p_user_id for update nowait;
  if not found or v_at is not null then
    raise exception 'Owner is unavailable for new media work.' using errcode = '55000';
  end if;
end;
$$;
revoke all on function public.assert_active_private_media_owner(uuid) from public,anon,authenticated;
grant execute on function public.assert_active_private_media_owner(uuid) to service_role;

create function public.fence_owner_upload_reservation()
returns trigger language plpgsql security invoker set search_path = ''
as $$
begin
  if tg_op='UPDATE' then
    -- Preserve the provider-independent tombstone on Auth/video FK removal.
    if ((new.user_id is null and old.user_id is not null
          and (pg_catalog.to_jsonb(new)-array['user_id','updated_at']) = (pg_catalog.to_jsonb(old)-array['user_id','updated_at']))
        or (new.video_id is null and old.video_id is not null
          and (pg_catalog.to_jsonb(new)-array['video_id','updated_at']) = (pg_catalog.to_jsonb(old)-array['video_id','updated_at']))) then
      return new;
    end if;
    if new.id is distinct from old.id or new.user_id is distinct from old.user_id
       or new.blob_path is distinct from old.blob_path then
      raise exception 'Reservation identity and path cannot change.' using errcode='55000';
    end if;
    -- Shortening only the deadline reduces authority, including intentional
    -- expiration. It cannot carry a new lease, path, size or identity.
    if (pg_catalog.to_jsonb(new)-array['expires_at','updated_at'])
         = (pg_catalog.to_jsonb(old)-array['expires_at','updated_at'])
       and pg_catalog.isfinite(new.expires_at) and new.expires_at<old.expires_at then
      return new;
    end if;
    -- Reject/expiry/cleanup cannot carry a hidden admission or publication.
    if (pg_catalog.to_jsonb(new)-array['state','rejection_reason','validation_owner','validation_expires_at','blob_deleted_at','cleanup_confirmed_at','updated_at'])
         = (pg_catalog.to_jsonb(old)-array['state','rejection_reason','validation_owner','validation_expires_at','blob_deleted_at','cleanup_confirmed_at','updated_at'])
       and (new.state=old.state or (old.state in ('issued','uploaded') and new.state in ('rejected','expired')))
       and (new.validation_owner is null or new.validation_owner is not distinct from old.validation_owner)
       and (new.validation_expires_at is null or new.validation_expires_at is not distinct from old.validation_expires_at)
       and (new.blob_deleted_at is not distinct from old.blob_deleted_at or
            (new.blob_deleted_at is not null and pg_catalog.isfinite(new.blob_deleted_at)
             and (old.blob_deleted_at is null or new.blob_deleted_at>=old.blob_deleted_at)))
       and (new.cleanup_confirmed_at is not distinct from old.cleanup_confirmed_at or
            (new.cleanup_confirmed_at is not null and pg_catalog.isfinite(new.cleanup_confirmed_at)
             and (old.cleanup_confirmed_at is null or new.cleanup_confirmed_at>=old.cleanup_confirmed_at))) then
      return new;
    end if;
  end if;
  perform public.assert_active_private_media_owner(new.user_id);
  if new.state='uploaded' and (new.validation_owner is null or new.validation_expires_at is null
       or not pg_catalog.isfinite(new.validation_expires_at)
       or new.validation_expires_at<=pg_catalog.clock_timestamp()) then
    raise exception 'A current validation lease is required.' using errcode='55000';
  end if;
  if new.state in ('issued','uploaded') and
     (not pg_catalog.isfinite(new.expires_at) or new.expires_at<=pg_catalog.clock_timestamp()) then
    raise exception 'Upload reservation expired before publication.' using errcode='55000';
  end if;
  return new;
end;
$$;
revoke all on function public.fence_owner_upload_reservation() from public,anon,authenticated;
grant execute on function public.fence_owner_upload_reservation() to service_role;
create trigger fence_owner_upload_reservation before insert or update on public.upload_reservations
for each row execute function public.fence_owner_upload_reservation();

create function public.fence_owner_video_publication()
returns trigger language plpgsql security invoker set search_path = ''
as $$
begin
  if tg_op='UPDATE' then
    -- Exact revoke-only shape used by revoke_video_media. Path/identity/analysis
    -- changes remain subject to owner denial even when discarded_at is set.
    if (pg_catalog.to_jsonb(new)-array['discarded_at','is_saved','save_state','expires_at','updated_at'])
         = (pg_catalog.to_jsonb(old)-array['discarded_at','is_saved','save_state','expires_at','updated_at'])
       and new.discarded_at is not null and pg_catalog.isfinite(new.discarded_at)
       and (old.discarded_at is null or new.discarded_at=old.discarded_at)
       and new.is_saved is false and new.save_state='pending' and new.expires_at is null then
      return new;
    end if;
    -- A legacy table without the retired-ID guard must not move a deleting
    -- owner's row into a different active owner to escape denial.
    if old.user_id is distinct from new.user_id then
      perform public.assert_active_private_media_owner(old.user_id);
    end if;
  end if;
  perform public.assert_active_private_media_owner(new.user_id);
  return new;
end;
$$;
revoke all on function public.fence_owner_video_publication() from public,anon,authenticated;
grant execute on function public.fence_owner_video_publication() to service_role;
create trigger fence_owner_video_publication before insert or update on public.videos
for each row execute function public.fence_owner_video_publication();

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

create or replace function public.mark_video_upload_received(p_reservation_id uuid, p_user_id uuid, p_validation_owner uuid)
returns setof public.upload_reservations
language plpgsql
security invoker
set search_path = public, pg_temp
as $$
begin
  perform public.lock_active_private_media_owner(p_user_id, false);
  perform pg_advisory_xact_lock(hashtextextended('peso:media-validation', 0));
  if (select count(*) from public.upload_reservations where validation_expires_at > pg_catalog.clock_timestamp()) >= 2 then
    raise exception 'Media validation capacity is full.' using errcode = 'P0001';
  end if;
  return query update public.upload_reservations
  set state = 'uploaded', uploaded_at = coalesce(uploaded_at, pg_catalog.clock_timestamp()),
      validation_owner = p_validation_owner, validation_expires_at = pg_catalog.clock_timestamp() + interval '5 minutes'
  where id = p_reservation_id and user_id = p_user_id
    and state in ('issued', 'uploaded') and expires_at > pg_catalog.clock_timestamp()
    and (validation_expires_at is null or validation_expires_at <= pg_catalog.clock_timestamp())
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
  perform public.lock_active_private_media_owner(p_user_id, false);
  select * into v_reservation from public.upload_reservations
  where id = p_reservation_id and user_id = p_user_id for update;
  if not found then
    raise exception 'Upload reservation not found.' using errcode = 'P0001';
  end if;
  if v_reservation.state in ('verified', 'consumed') and v_reservation.video_id is not null then
    return query select v_reservation.video_id;
    return;
  end if;
  if v_reservation.state <> 'uploaded' or not pg_catalog.isfinite(v_reservation.expires_at) or v_reservation.expires_at <= pg_catalog.clock_timestamp()
    or v_reservation.validation_owner is distinct from p_validation_owner
    or v_reservation.validation_expires_at is null or not pg_catalog.isfinite(v_reservation.validation_expires_at)
    or v_reservation.validation_expires_at <= pg_catalog.clock_timestamp()
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
  set state = 'verified', verified_at = pg_catalog.clock_timestamp(), actual_bytes = p_actual_bytes,
      media_metadata = p_media_metadata, video_id = v_video_id,
      validation_owner = null, validation_expires_at = null
  where id = p_reservation_id;
  return query select v_video_id;
end;
$$;

commit;
