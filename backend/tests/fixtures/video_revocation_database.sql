-- Supplemental schema for the disposable peso_revocation_test database only.
-- The common security fixture is loaded first; production queue SQL is loaded
-- after this so the lock tests exercise its real constraints and functions.
drop table public.analysis_jobs;
alter table public.videos
  alter column fps type numeric(8,2),
  add column created_at timestamptz not null default now(),
  add column updated_at timestamptz not null default now(),
  add column saved_at timestamptz,
  add column performed_reps integer,
  add column load_value numeric,
  add column load_unit text,
  add column storage_optimized_at timestamptz,
  add column storage_optimization_error text;
alter table public.analysis_results
  add column model_version text not null default 'fixture',
  add column created_at timestamptz not null default now(),
  add constraint fixture_analysis_model_unique unique(video_id, model_version);
create schema storage;
create table storage.buckets (
  id text primary key, name text, public boolean, file_size_limit bigint,
  allowed_mime_types text[]
);
create role public_probe nologin;
grant usage on schema public to public_probe;
