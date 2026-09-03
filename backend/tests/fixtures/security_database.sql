-- Minimal isolated schema for exercising the production reservation migration.
-- Only used in the dedicated localhost peso_security_test database in CI.
create extension if not exists pgcrypto;
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create schema auth;
create table auth.users (id uuid primary key);
create function public.set_updated_at() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end;
$$;
create table public.videos (
  id uuid primary key default gen_random_uuid(), user_id uuid references auth.users(id) on delete cascade,
  storage_path text, source_type text, exercise_type text, view_type text, status text,
  duration_ms integer, fps numeric, save_state text, expires_at timestamptz,
  original_size_bytes bigint, uploaded_size_bytes bigint, was_compressed boolean,
  storage_state text, tracking_setup jsonb, quality_preflight_required boolean,
  discarded_at timestamptz
);
create table public.analysis_jobs (
  id uuid primary key default gen_random_uuid(), video_id uuid references public.videos(id) on delete cascade,
  status text default 'queued', attempt_count integer default 0, created_at timestamptz default now()
);
grant usage on schema public, auth to service_role, authenticated, anon;
grant all on public.videos, public.analysis_jobs to service_role;
