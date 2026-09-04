-- RUN ONLY after the staging release checklist has passed and reservation-capable
-- clients are the supported minimum version. This is intentionally not automatic.
begin;
drop policy if exists "Users can upload own private videos" on storage.objects;
drop policy if exists "Users can update own private videos" on storage.objects;
drop policy if exists "Users can delete own private videos" on storage.objects;
commit;
