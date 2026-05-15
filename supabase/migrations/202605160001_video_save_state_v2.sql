alter table public.videos
  drop column if exists is_saved,
  drop column if exists discarded_at;

alter table public.videos
  add column if not exists save_state text not null default 'pending'
    check (save_state in ('pending', 'saved')),
  add column if not exists saved_at timestamptz,
  add column if not exists expires_at timestamptz default now() + interval '24 hours',
  add column if not exists is_bookmarked boolean not null default false;

create index if not exists videos_user_id_saved_at_idx
  on public.videos (user_id, saved_at desc)
  where save_state = 'saved';

create index if not exists videos_pending_expires_at_idx
  on public.videos (expires_at)
  where save_state = 'pending';