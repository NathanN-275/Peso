alter table public.videos
  add column if not exists weight numeric(10, 2),
  add column if not exists weight_unit text,
  add column if not exists corrected_rep_count integer,
  add column if not exists user_notes text;

alter table public.videos
  drop constraint if exists videos_weight_unit_check;

alter table public.videos
  add constraint videos_weight_unit_check
  check (weight_unit is null or weight_unit in ('lb', 'kg'));

alter table public.videos
  drop constraint if exists videos_weight_check;

alter table public.videos
  add constraint videos_weight_check
  check (weight is null or weight >= 0);

alter table public.videos
  drop constraint if exists videos_corrected_rep_count_check;

alter table public.videos
  add constraint videos_corrected_rep_count_check
  check (corrected_rep_count is null or corrected_rep_count >= 0);
