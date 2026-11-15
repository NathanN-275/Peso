-- Admission and publication share the video locks used by revocation. Storage
-- uploads still need a durable intent protocol before late-object cleanup is safe.
create function public.fence_saved_lift_export_publication()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  if tg_op = 'UPDATE' then
    if new.id is distinct from old.id or new.user_id is distinct from old.user_id
       or new.video_ids is distinct from old.video_ids then
      raise exception 'Archive identity and selection cannot change.' using errcode = '55000';
    end if;
    if (old.status = 'expired' and new.status <> 'expired')
       or (old.status = 'failed' and new.status not in ('failed', 'expired'))
       or (old.status = 'completed' and new.status in ('queued', 'processing'))
       or (old.status = 'processing' and new.status = 'queued') then
      raise exception 'Archive state cannot be reopened.' using errcode = '55000';
    end if;
    if old.status = 'completed' and new.status = 'failed'
       and new.failure_code is distinct from 'archive_missing' then
      raise exception 'A worker cannot fail a published archive.' using errcode = '55000';
    end if;
    if old.status = 'completed' and new.status = 'completed'
       and (new.archive_path is distinct from old.archive_path
         or new.completed_at is distinct from old.completed_at
         or new.expires_at is distinct from old.expires_at) then
      raise exception 'A completed archive cannot be republished.' using errcode = '55000';
    end if;
  end if;
  if new.status <> 'completed' and new.archive_path is not null then
    raise exception 'An incomplete archive cannot publish a path.' using errcode = '55000';
  end if;
  if tg_op = 'INSERT' or new.status in ('queued', 'processing', 'completed') then
    if new.id is null or new.id = '00000000-0000-0000-0000-000000000000'::uuid
       or new.user_id is null or new.user_id = '00000000-0000-0000-0000-000000000000'::uuid
       or coalesce(pg_catalog.array_ndims(new.video_ids), 0) <> 1
       or pg_catalog.cardinality(new.video_ids) not between 1 and 50
       or pg_catalog.array_position(new.video_ids, null) is not null
       or (select count(distinct id) from pg_catalog.unnest(new.video_ids) selected(id))
          <> pg_catalog.cardinality(new.video_ids) then
      raise exception 'A distinct selection of 1 to 50 videos is required.' using errcode = '22023';
    end if;
    -- A direct UPDATE already holds its archive row. Fail fast on a video lock
    -- rather than wait against revocation's video-before-archive lock order.
    perform v.id from public.videos v where v.id = any(new.video_ids)
      order by v.id for update nowait;
    if exists (
      select 1 from pg_catalog.unnest(new.video_ids) selected(id)
      left join public.videos v on v.id = selected.id
      where v.id is null or v.user_id is distinct from new.user_id
         or v.discarded_at is not null or v.storage_state = 'pruned'
         or not (coalesce(v.save_state = 'saved', false) or coalesce(v.is_saved, false))
         or (v.expires_at is not null and
             (not pg_catalog.isfinite(v.expires_at) or v.expires_at <= pg_catalog.clock_timestamp()))
         or exists (select 1 from public.video_deletion_outbox o where o.video_id = selected.id)
         or not exists (select 1 from public.analysis_results r where r.video_id = selected.id)
    ) then
      raise exception 'The complete archive selection is unavailable.' using errcode = '55000';
    end if;
    if new.status = 'completed' and
       (new.archive_path is distinct from new.user_id::text || '/' || new.id::text || '.zip'
        or new.completed_at is null or not pg_catalog.isfinite(new.completed_at)
        or new.expires_at is null or not pg_catalog.isfinite(new.expires_at)
        or new.expires_at <= pg_catalog.clock_timestamp()) then
      raise exception 'A completed archive needs a current deterministic artifact.' using errcode = '55000';
    end if;
  end if;
  return new;
end;
$$;
revoke all on function public.fence_saved_lift_export_publication() from public, anon, authenticated;
grant execute on function public.fence_saved_lift_export_publication() to service_role;
create trigger fence_saved_lift_export_publication
before insert or update on public.saved_lift_export_jobs
for each row execute function public.fence_saved_lift_export_publication();
