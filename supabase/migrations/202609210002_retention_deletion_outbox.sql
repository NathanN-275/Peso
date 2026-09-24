-- Media deletion is asynchronous. Keep only the identifiers needed to retry it;
-- analysis results and history disappear atomically when expiry is claimed.
create table public.video_deletion_outbox (
  video_id uuid primary key,
  user_id uuid not null,
  storage_paths text[] not null,
  created_at timestamptz not null default now()
);
alter table public.video_deletion_outbox enable row level security;
revoke all on public.video_deletion_outbox from public, anon, authenticated;
grant select, insert, delete on public.video_deletion_outbox to service_role;

create function public.claim_expired_video_deletion(p_video_id uuid)
returns setof public.video_deletion_outbox
language plpgsql security invoker set search_path = public, pg_temp
as $$
declare
  v_video public.videos%rowtype;
  v_paths text[];
begin
  -- Saving updates this same row. Whichever transaction locks first wins;
  -- a completed save is rechecked before any record or object is removed.
  select * into v_video from public.videos where id = p_video_id for update;
  if not found then return; end if;
  if v_video.save_state is distinct from 'pending' or v_video.expires_at is null
     or v_video.expires_at > now() then return; end if;
  if coalesce((to_jsonb(v_video)->>'is_saved')::boolean, false) then return; end if;
  -- Queue recovery, not retention, owns stale/retry work. Never interrupt an
  -- accepted job based on the video's updated_at timestamp.
  if exists (select 1 from public.analysis_jobs where video_id = p_video_id
             and status in ('queued', 'processing', 'retry_wait')) then return; end if;
  select array_agg(distinct path) into v_paths from unnest(array[
    v_video.storage_path, to_jsonb(v_video)->>'original_storage_path',
    to_jsonb(v_video)->>'playback_path', to_jsonb(v_video)->>'thumbnail_path'
  ]) path where path is not null and path <> '';
  if v_paths is null or exists (
    select 1 from unnest(v_paths) path
    where path not like v_video.user_id::text || '/%'
       or path like '%/../%' or path like '%/./%'
  ) then raise exception 'Unsafe retention storage path'; end if;
  insert into public.video_deletion_outbox(video_id, user_id, storage_paths)
    values (v_video.id, v_video.user_id, v_paths);
  -- The established analysis_results and analysis_jobs FKs cascade. Explicit
  -- result deletion also supports older installations without that cascade.
  delete from public.analysis_results where video_id = p_video_id;
  delete from public.videos where id = p_video_id;
  return query select * from public.video_deletion_outbox where video_id = p_video_id;
end;
$$;
revoke execute on function public.claim_expired_video_deletion(uuid) from public, anon, authenticated;
grant execute on function public.claim_expired_video_deletion(uuid) to service_role;
