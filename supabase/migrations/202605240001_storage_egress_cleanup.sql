alter table public.videos
  add column if not exists is_saved boolean not null default false,
  add column if not exists saved_at timestamptz,
  add column if not exists discarded_at timestamptz,
  add column if not exists thumbnail_path text,
  add column if not exists playback_path text,
  add column if not exists original_storage_path text,
  add column if not exists storage_optimized_at timestamptz,
  add column if not exists storage_optimization_error text;

update public.videos
set is_saved = true
where save_state = 'saved'
  and is_saved = false;

update public.videos
set save_state = 'saved'
where is_saved = true
  and save_state <> 'saved';

alter table public.videos
  drop constraint if exists videos_status_check;

alter table public.videos
  add constraint videos_status_check
  check (status in ('pending', 'uploaded', 'queued', 'processing', 'completed', 'failed'));

create index if not exists videos_user_id_is_saved_idx
  on public.videos (user_id, saved_at desc)
  where is_saved = true and discarded_at is null;

create index if not exists videos_discarded_cleanup_idx
  on public.videos (discarded_at)
  where is_saved = false and discarded_at is not null;

create index if not exists videos_failed_cleanup_idx
  on public.videos (updated_at)
  where status = 'failed' and is_saved = false;

create index if not exists videos_unsaved_status_created_at_idx
  on public.videos (status, created_at)
  where is_saved = false;

create index if not exists videos_playback_path_idx
  on public.videos (playback_path)
  where playback_path is not null;
