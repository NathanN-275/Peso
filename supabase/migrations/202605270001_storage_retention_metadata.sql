alter table public.videos
  add column if not exists thumbnail_path text,
  add column if not exists original_size_bytes bigint,
  add column if not exists uploaded_size_bytes bigint,
  add column if not exists was_compressed boolean,
  add column if not exists storage_state text not null default 'available'
    check (storage_state in ('available', 'pruned')),
  add column if not exists storage_pruned_at timestamptz;

create index if not exists videos_saved_available_expires_at_idx
  on public.videos (expires_at)
  where save_state = 'saved'
    and storage_state = 'available';

create index if not exists videos_thumbnail_path_idx
  on public.videos (thumbnail_path)
  where thumbnail_path is not null;
