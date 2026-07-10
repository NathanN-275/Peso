alter table public.videos
  add constraint videos_storage_path_shape_check
  check (
    storage_path !~ '(^/|/$|//|\\|://|(^|/)\.\.?(/|$))'
  )
  not valid;

alter table public.videos
  add constraint videos_original_storage_path_shape_check
  check (
    original_storage_path is null
    or original_storage_path !~ '(^/|/$|//|\\|://|(^|/)\.\.?(/|$))'
  )
  not valid;

alter table public.videos
  add constraint videos_playback_path_shape_check
  check (
    playback_path is null
    or playback_path !~ '(^/|/$|//|\\|://|(^|/)\.\.?(/|$))'
  )
  not valid;

alter table public.videos
  add constraint videos_thumbnail_path_shape_check
  check (
    thumbnail_path is null
    or thumbnail_path !~ '(^/|/$|//|\\|://|(^|/)\.\.?(/|$))'
  )
  not valid;

revoke insert, update, delete on public.videos from authenticated;
