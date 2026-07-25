alter table public.videos
  add column if not exists performed_reps integer,
  add column if not exists load_value numeric(10, 2),
  add column if not exists load_unit text;

alter table public.videos
  drop constraint if exists videos_performed_reps_check,
  add constraint videos_performed_reps_check
    check (performed_reps is null or performed_reps >= 1),
  drop constraint if exists videos_load_value_check,
  add constraint videos_load_value_check
    check (load_value is null or load_value >= 0),
  drop constraint if exists videos_load_unit_check,
  add constraint videos_load_unit_check
    check (load_unit is null or load_unit in ('lb', 'kg')),
  drop constraint if exists videos_workout_details_all_or_none_check,
  add constraint videos_workout_details_all_or_none_check
    check (
      (performed_reps is null and load_value is null and load_unit is null)
      or
      (performed_reps is not null and load_value is not null and load_unit is not null)
    );
