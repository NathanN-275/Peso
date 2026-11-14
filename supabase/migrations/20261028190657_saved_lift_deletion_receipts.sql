-- Retry proof survives both video and Auth metadata. It contains no media/token.
create table public.saved_lift_deletion_receipts (
  video_id uuid primary key check (video_id <> '00000000-0000-0000-0000-000000000000'),
  user_id uuid not null check (user_id <> '00000000-0000-0000-0000-000000000000'),
  created_at timestamptz not null default pg_catalog.clock_timestamp(),
  completed_at timestamptz
);
alter table public.saved_lift_deletion_receipts enable row level security;
revoke all on public.saved_lift_deletion_receipts from public, anon, authenticated;
grant select on public.saved_lift_deletion_receipts to service_role;
grant insert (video_id, user_id) on public.saved_lift_deletion_receipts to service_role;
grant update (completed_at) on public.saved_lift_deletion_receipts to service_role;

create function public.guard_saved_lift_deletion_receipt()
returns trigger language plpgsql security invoker set search_path = ''
as $$
begin
  if tg_op = 'DELETE' then
    raise exception 'Deletion retry proof must be retained.' using errcode = '55000';
  elsif tg_op = 'INSERT' then
    perform v.id from public.videos v where v.id = new.video_id and v.user_id = new.user_id
      and v.discarded_at is null and (coalesce(v.save_state = 'saved', false) or coalesce(v.is_saved, false))
      and not exists (select 1 from public.video_deletion_outbox o where o.video_id = v.id)
      for update nowait;
    if not found then
      raise exception 'A current owned Saved Lift is required for a new receipt.' using errcode = '55000';
    end if;
    if new.completed_at is not null then
      raise exception 'A deletion receipt must begin pending.' using errcode = '55000';
    end if;
  elsif new.video_id is distinct from old.video_id or new.user_id is distinct from old.user_id
      or new.created_at is distinct from old.created_at
      or (old.completed_at is not null and new.completed_at is distinct from old.completed_at) then
    raise exception 'Deletion receipt identity and completion cannot change.' using errcode = '55000';
  end if;
  if new.completed_at is not null and
      (not pg_catalog.isfinite(new.completed_at)
       or exists (select 1 from public.videos v where v.id = new.video_id)
       or exists (select 1 from public.video_deletion_outbox o where o.video_id = new.video_id)) then
    raise exception 'Deletion metadata is still pending.' using errcode = '55000';
  end if;
  return new;
end;
$$;
revoke all on function public.guard_saved_lift_deletion_receipt() from public, anon, authenticated;
grant execute on function public.guard_saved_lift_deletion_receipt() to service_role;
create trigger guard_saved_lift_deletion_receipt before insert or update or delete
on public.saved_lift_deletion_receipts for each row execute function public.guard_saved_lift_deletion_receipt();

create function public.guard_deleted_video_identity()
returns trigger language plpgsql security invoker set search_path = '' set lock_timeout = '2s'
as $$
begin
  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id or new.user_id is distinct from old.user_id then
      raise exception 'Video identity cannot change.' using errcode = '55000';
    end if;
    return new;
  end if;
  -- Before INSERT takes its unique-index lock, serialize missing-row reuse too.
  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('peso:saved-delete:' || new.id::text, 58271));
  if exists (select 1 from public.saved_lift_deletion_receipts r where r.video_id = new.id) then
    raise exception 'This video identity has been retired.' using errcode = '55000';
  end if;
  return new;
end;
$$;
revoke all on function public.guard_deleted_video_identity() from public, anon, authenticated;
grant execute on function public.guard_deleted_video_identity() to service_role;
create trigger guard_deleted_video_identity before insert or update of id, user_id
on public.videos for each row execute function public.guard_deleted_video_identity();

create function public.revoke_saved_lifts(p_user_id uuid, p_video_ids uuid[])
returns table(video_id uuid, user_id uuid, completed boolean, task jsonb)
language plpgsql security invoker set search_path = '' set lock_timeout = '2s'
as $$
declare
  v_ids uuid[];
  v_pending uuid[];
  v_key bigint;
begin
  if p_user_id is null or p_user_id = '00000000-0000-0000-0000-000000000000'
     or p_video_ids is null or coalesce(pg_catalog.array_ndims(p_video_ids), 0) <> 1
     or pg_catalog.cardinality(p_video_ids) not between 1 and 50
     or pg_catalog.array_position(p_video_ids, null) is not null
     or pg_catalog.array_position(p_video_ids, '00000000-0000-0000-0000-000000000000'::uuid) is not null
     or (select count(distinct id) from pg_catalog.unnest(p_video_ids) selected(id)) <> pg_catalog.cardinality(p_video_ids) then
    raise exception 'A distinct selection of 1 to 50 videos and an owner are required.' using errcode = '22023';
  end if;
  select pg_catalog.array_agg(id order by id) into v_ids from pg_catalog.unnest(p_video_ids) selected(id);
  -- Sort actual advisory keys, including collisions, before acquiring row locks.
  for v_key in select distinct pg_catalog.hashtextextended('peso:saved-delete:' || id::text, 58271)
      from pg_catalog.unnest(v_ids) selected(id) order by 1 loop
    perform pg_catalog.pg_advisory_xact_lock(v_key);
  end loop;
  perform v.id from public.videos v where v.id = any(v_ids) order by v.id for update;
  perform r.video_id from public.saved_lift_deletion_receipts r where r.video_id = any(v_ids)
    order by r.video_id for update;
  if exists (
    select 1 from pg_catalog.unnest(v_ids) selected(id)
    left join public.videos v on v.id = selected.id
    left join public.saved_lift_deletion_receipts r on r.video_id = selected.id
    where (r.video_id is not null and r.user_id is distinct from p_user_id)
       or (v.id is not null and v.user_id is distinct from p_user_id)
       or (r.video_id is null and v.id is null)
  ) then
    raise exception 'The complete Saved Lift selection is unavailable.' using errcode = '42501';
  end if;
  if exists (
    select 1 from pg_catalog.unnest(v_ids) selected(id)
    left join public.videos v on v.id = selected.id
    left join public.saved_lift_deletion_receipts r on r.video_id = selected.id
    where (r.video_id is null and (v.discarded_at is not null
           or not (coalesce(v.save_state = 'saved', false) or coalesce(v.is_saved, false))
           or exists (select 1 from public.video_deletion_outbox o where o.video_id = selected.id)))
       or (r.completed_at is not null and (v.id is not null
           or exists (select 1 from public.video_deletion_outbox o where o.video_id = selected.id)))
  ) then
    raise exception 'Only Saved Lifts or matching deletion retries are available.' using errcode = '55000';
  end if;
  select pg_catalog.array_agg(selected.id order by selected.id) into v_pending
    from pg_catalog.unnest(v_ids) selected(id)
    left join public.saved_lift_deletion_receipts r on r.video_id = selected.id
    where r.completed_at is null;
  if pg_catalog.cardinality(v_pending) > 0 then
    insert into public.saved_lift_deletion_receipts(video_id, user_id)
      select selected.id, p_user_id from pg_catalog.unnest(v_pending) selected(id)
      where not exists (select 1 from public.saved_lift_deletion_receipts r where r.video_id = selected.id)
      on conflict on constraint saved_lift_deletion_receipts_pkey do nothing;
    perform public.revoke_video_media(p_user_id, v_pending, true);
  end if;
  return query select r.video_id, r.user_id, r.completed_at is not null,
      case when r.completed_at is null then pg_catalog.to_jsonb(o) else null::jsonb end
    from public.saved_lift_deletion_receipts r
    left join public.video_deletion_outbox o on o.video_id = r.video_id
    where r.video_id = any(v_ids) and r.user_id = p_user_id order by r.video_id;
end;
$$;
revoke all on function public.revoke_saved_lifts(uuid, uuid[]) from public, anon, authenticated;
grant execute on function public.revoke_saved_lifts(uuid, uuid[]) to service_role;

create function public.read_saved_lift_deletion_receipts(p_user_id uuid, p_video_ids uuid[])
returns table(video_id uuid, user_id uuid, completed boolean, task jsonb)
language sql stable security invoker set search_path = ''
as $$
  select r.video_id, r.user_id,
      r.completed_at is not null
        and not exists (select 1 from public.videos v where v.id = r.video_id)
        and not exists (select 1 from public.video_deletion_outbox o where o.video_id = r.video_id),
      null::jsonb
    from public.saved_lift_deletion_receipts r
    where r.user_id = p_user_id and r.video_id = any(p_video_ids) order by r.video_id;
$$;
revoke all on function public.read_saved_lift_deletion_receipts(uuid, uuid[]) from public, anon, authenticated;
grant execute on function public.read_saved_lift_deletion_receipts(uuid, uuid[]) to service_role;

-- A cleanup worker may acknowledge only the exact snapshot it processed.
-- This is not an assertion about Storage or a fence against late publishers.
create or replace function public.complete_video_media_deletion(
  p_video_id uuid,
  p_user_id uuid,
  p_storage_paths text[],
  p_archive_paths text[],
  p_export_prefixes text[],
  p_delete_metadata boolean
)
returns boolean
language plpgsql
security invoker
set search_path = ''
set lock_timeout = '2s'
as $$
declare
  v_video public.videos%rowtype;
  v_task public.video_deletion_outbox%rowtype;
begin
  if p_video_id is null or p_user_id is null or p_storage_paths is null
     or p_archive_paths is null or p_export_prefixes is null
     or p_delete_metadata is null then
    raise exception 'The complete cleanup snapshot is required.' using errcode = '22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('peso:saved-delete:' || p_video_id::text, 58271));
  -- Revocation locks videos before outbox rows. Keep the same order here.
  select * into v_video from public.videos v where v.id = p_video_id for update;
  if found and (v_video.user_id is distinct from p_user_id
      or v_video.discarded_at is null or coalesce(v_video.is_saved, false)
      or v_video.save_state is distinct from 'pending') then
    return false;
  end if;
  perform r.video_id from public.saved_lift_deletion_receipts r
    where r.video_id = p_video_id for update;
  if exists (select 1 from public.saved_lift_deletion_receipts r where r.video_id = p_video_id
      and (r.user_id is distinct from p_user_id or not p_delete_metadata)) then
    return false;
  end if;
  select * into v_task from public.video_deletion_outbox o
    where o.video_id = p_video_id for update;
  if not found or v_task.user_id is distinct from p_user_id
     or v_task.storage_paths is distinct from p_storage_paths
     or v_task.archive_paths is distinct from p_archive_paths
     or v_task.export_prefixes is distinct from p_export_prefixes
     or v_task.delete_metadata is distinct from p_delete_metadata then
    return false;
  end if;
  if exists (select 1 from public.analysis_jobs j where j.video_id = p_video_id
             and j.status in ('queued', 'processing', 'retry_wait')) then
    return false;
  end if;

  if p_delete_metadata then
    -- Do not wait on a child writer that might next request our video lock.
    perform j.id from public.analysis_jobs j where j.video_id = p_video_id
      order by j.id for update nowait;
    perform r.id from public.analysis_results r where r.video_id = p_video_id
      order by r.id for update nowait;
    perform r.id from public.upload_reservations r where r.video_id = p_video_id
      order by r.id for update nowait;
    delete from public.analysis_results r where r.video_id = p_video_id;
    delete from public.videos v where v.id = p_video_id and v.user_id = p_user_id;
  end if;
  delete from public.video_deletion_outbox o where o.video_id = p_video_id;
  if p_delete_metadata then
    update public.saved_lift_deletion_receipts r set completed_at = pg_catalog.clock_timestamp()
      where r.video_id = p_video_id and r.user_id = p_user_id and r.completed_at is null;
  end if;
  return true;
end;
$$;
revoke all on function public.complete_video_media_deletion(uuid, uuid, text[], text[], text[], boolean)
  from public, anon, authenticated;
grant execute on function public.complete_video_media_deletion(uuid, uuid, text[], text[], text[], boolean)
  to service_role;
