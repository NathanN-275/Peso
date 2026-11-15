-- Snapshots survive metadata removal and are consumed only after shared cleanup
-- supports these fields; the current cleanup consumer is not yet sufficient.
alter table public.video_deletion_outbox
  add column archive_paths text[] not null default '{}'::text[],
  add column export_prefixes text[] not null default '{}'::text[],
  add column delete_metadata boolean not null default false;

grant update (storage_paths, archive_paths, export_prefixes, delete_metadata)
  on public.video_deletion_outbox to service_role;

create function public.revoke_video_media(
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
    select coalesce(pg_catalog.array_agg(distinct p.path order by p.path), '{}'::text[])
      into v_storage_paths from public.videos v
      cross join lateral pg_catalog.unnest(array[
        v.storage_path, v.original_storage_path, v.playback_path, v.thumbnail_path
      ]) as p(path)
      where v.id = v_id and p.path is not null;
    select coalesce(pg_catalog.array_agg(distinct paths.path order by paths.path), '{}'::text[])
      into v_archive_paths from (
        select e.archive_path as path from public.saved_lift_export_jobs e
          where e.user_id = p_user_id and v_id = any(e.video_ids) and e.archive_path is not null
        union all
        -- Include the deterministic late-upload name even for queued jobs.
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
revoke all on function public.revoke_video_media(uuid, uuid[], boolean) from public, anon, authenticated;
grant execute on function public.revoke_video_media(uuid, uuid[], boolean) to service_role;
