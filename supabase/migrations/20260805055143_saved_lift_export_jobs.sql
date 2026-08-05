create table public.saved_lift_export_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  video_ids uuid[] not null,
  status text not null default 'queued'
    check (status in ('queued', 'processing', 'completed', 'failed', 'expired')),
  archive_path text,
  failure_code text,
  attempts smallint not null default 0 check (attempts >= 0),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  started_at timestamptz,
  completed_at timestamptz,
  expires_at timestamptz,
  constraint saved_lift_export_jobs_video_count_check
    check (cardinality(video_ids) between 1 and 50),
  constraint saved_lift_export_jobs_archive_owner_check
    check (archive_path is null or archive_path like (user_id::text || '/%')),
  constraint saved_lift_export_jobs_completed_fields_check
    check (
      status <> 'completed'
      or (archive_path is not null and completed_at is not null and expires_at is not null)
    )
);

create index saved_lift_export_jobs_user_created_idx
  on public.saved_lift_export_jobs (user_id, created_at desc);

create index saved_lift_export_jobs_expiry_idx
  on public.saved_lift_export_jobs (expires_at)
  where status = 'completed';

drop trigger if exists set_saved_lift_export_jobs_updated_at
  on public.saved_lift_export_jobs;
create trigger set_saved_lift_export_jobs_updated_at
before update on public.saved_lift_export_jobs
for each row
execute function public.set_updated_at();

alter table public.saved_lift_export_jobs enable row level security;

-- Export jobs are an internal backend record. Authenticated clients use the
-- owner-checked FastAPI routes instead of reading or mutating this table.
revoke all on public.saved_lift_export_jobs from anon, authenticated;
grant select, insert, update, delete on public.saved_lift_export_jobs to service_role;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'saved-lift-exports',
  'saved-lift-exports',
  false,
  null,
  array['application/zip']
)
on conflict (id) do update
set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- No storage.objects policies are created for this bucket. Only the backend's
-- service role may write archives or issue short-lived signed download URLs.
