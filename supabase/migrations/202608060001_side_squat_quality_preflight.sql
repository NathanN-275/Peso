alter table public.videos
  add column if not exists quality_preflight jsonb,
  add column if not exists quality_preflight_required boolean not null default false;

comment on column public.videos.quality_preflight is
  'Versioned sampled-frame quality evidence recorded before side-view squat analysis.';

comment on column public.videos.quality_preflight_required is
  'True only for new submissions that must pass the side-view squat preflight gate.';
