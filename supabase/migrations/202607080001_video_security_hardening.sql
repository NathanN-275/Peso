alter table public.videos
  add constraint videos_storage_path_owner_check
  check (storage_path like (user_id::text || '/%'))
  not valid;

alter table public.videos
  add constraint videos_original_storage_path_owner_check
  check (original_storage_path is null or original_storage_path like (user_id::text || '/%'))
  not valid;

alter table public.videos
  add constraint videos_playback_path_owner_check
  check (playback_path is null or playback_path like (user_id::text || '/playback/%'))
  not valid;

alter table public.videos
  add constraint videos_thumbnail_path_owner_check
  check (thumbnail_path is null or thumbnail_path like (user_id::text || '/thumbnails/%'))
  not valid;

drop policy if exists "Users can insert own videos" on public.videos;
drop policy if exists "Users can update own videos" on public.videos;
drop policy if exists "Users can delete own videos" on public.videos;

revoke insert, update, delete on public.videos from authenticated;
grant select on public.videos to authenticated;

update storage.buckets
set
  file_size_limit = 52428800,
  allowed_mime_types = array[
    'video/mp4',
    'video/quicktime',
    'video/x-m4v',
    'video/m4v',
    'video/webm'
  ]
where id = 'videos';

update storage.buckets
set
  file_size_limit = 524288,
  allowed_mime_types = array[
    'image/jpeg',
    'image/png',
    'image/webp'
  ]
where id = 'profile-avatars';
