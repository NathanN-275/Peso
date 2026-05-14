alter table public.videos
  add column if not exists is_saved boolean not null default false,
  add column if not exists saved_at timestamptz,
  add column if not exists discarded_at timestamptz;

create index if not exists videos_user_id_saved_at_idx
  on public.videos (user_id, saved_at desc)
  where is_saved = true;
