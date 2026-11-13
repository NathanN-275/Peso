-- A cleanup worker may acknowledge only the exact snapshot it processed.
-- This is not an assertion about Storage or a fence against late publishers.
create function public.complete_video_media_deletion(
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

  -- Revocation locks videos before outbox rows. Keep the same order here.
  select * into v_video from public.videos v where v.id = p_video_id for update;
  if found and (v_video.user_id is distinct from p_user_id
      or v_video.discarded_at is null or coalesce(v_video.is_saved, false)
      or v_video.save_state is distinct from 'pending') then
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
  return true;
end;
$$;
revoke all on function public.complete_video_media_deletion(uuid, uuid, text[], text[], text[], boolean)
  from public, anon, authenticated;
grant execute on function public.complete_video_media_deletion(uuid, uuid, text[], text[], text[], boolean)
  to service_role;
