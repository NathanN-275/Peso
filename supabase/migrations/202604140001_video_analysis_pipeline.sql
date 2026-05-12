create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

create table if not exists public.videos (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  storage_path text not null unique,
  source_type text not null default 'camera_roll',
  exercise_type text not null,
  view_type text not null,
  status text not null default 'uploaded' check (status in ('uploaded', 'queued', 'processing', 'completed', 'failed')),
  duration_ms integer,
  fps numeric(8, 2),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.analysis_results (
  id uuid primary key default gen_random_uuid(),
  video_id uuid not null references public.videos (id) on delete cascade,
  model_version text not null,
  result_json jsonb not null,
  created_at timestamptz not null default timezone('utc', now()),
  unique (video_id, model_version)
);

create index if not exists videos_user_id_created_at_idx
  on public.videos (user_id, created_at desc);

create index if not exists videos_status_idx
  on public.videos (status);

create index if not exists analysis_results_video_id_idx
  on public.analysis_results (video_id);

drop trigger if exists set_videos_updated_at on public.videos;
create trigger set_videos_updated_at
before update on public.videos
for each row
execute function public.set_updated_at();

alter table public.videos enable row level security;
alter table public.analysis_results enable row level security;

drop policy if exists "Users can view own videos" on public.videos;
create policy "Users can view own videos"
on public.videos
for select
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users can insert own videos" on public.videos;
create policy "Users can insert own videos"
on public.videos
for insert
to authenticated
with check (auth.uid() = user_id);

drop policy if exists "Users can update own videos" on public.videos;
create policy "Users can update own videos"
on public.videos
for update
to authenticated
using (auth.uid() = user_id)
with check (auth.uid() = user_id);

drop policy if exists "Users can delete own videos" on public.videos;
create policy "Users can delete own videos"
on public.videos
for delete
to authenticated
using (auth.uid() = user_id);

drop policy if exists "Users can view analysis for own videos" on public.analysis_results;
create policy "Users can view analysis for own videos"
on public.analysis_results
for select
to authenticated
using (
  exists (
    select 1
    from public.videos
    where public.videos.id = analysis_results.video_id
      and public.videos.user_id = auth.uid()
  )
);

insert into storage.buckets (id, name, public)
values ('videos', 'videos', false)
on conflict (id) do update set public = excluded.public;

drop policy if exists "Users can upload own private videos" on storage.objects;
create policy "Users can upload own private videos"
on storage.objects
for insert
to authenticated
with check (
  bucket_id = 'videos'
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists "Users can read own private videos" on storage.objects;
create policy "Users can read own private videos"
on storage.objects
for select
to authenticated
using (
  bucket_id = 'videos'
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists "Users can update own private videos" on storage.objects;
create policy "Users can update own private videos"
on storage.objects
for update
to authenticated
using (
  bucket_id = 'videos'
  and (storage.foldername(name))[1] = auth.uid()::text
)
with check (
  bucket_id = 'videos'
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists "Users can delete own private videos" on storage.objects;
create policy "Users can delete own private videos"
on storage.objects
for delete
to authenticated
using (
  bucket_id = 'videos'
  and (storage.foldername(name))[1] = auth.uid()::text
);
