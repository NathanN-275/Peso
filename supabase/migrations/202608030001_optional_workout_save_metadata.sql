alter table public.videos
  drop constraint if exists videos_workout_details_all_or_none_check,
  drop constraint if exists videos_load_details_all_or_none_check,
  add constraint videos_load_details_all_or_none_check
    check (
      (load_value is null and load_unit is null)
      or
      (load_value is not null and load_unit is not null)
    );
