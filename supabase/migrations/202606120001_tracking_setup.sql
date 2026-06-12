alter table public.videos
  add column if not exists tracking_setup jsonb;

comment on column public.videos.tracking_setup is
  'Optional versioned user-supplied reference-frame anchors for pin-assisted tracking.';
