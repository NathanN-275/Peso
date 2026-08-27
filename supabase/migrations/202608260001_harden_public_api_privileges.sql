-- Client roles do not need to invoke the event-trigger helper directly.
revoke all privileges on function public.rls_auto_enable() from public, anon, authenticated;

-- Trigger functions resolve built-ins from pg_catalog and app objects from public.
alter function public.set_updated_at() set search_path = pg_catalog, public;

-- Remove broad default grants, then restore only the operations used by clients.
revoke all privileges on table public.analysis_results from public, anon;
revoke all privileges on table public.profiles from public, anon;
revoke all privileges on table public.videos from public, anon;

revoke all privileges on table public.analysis_results from authenticated;
revoke all privileges on table public.profiles from authenticated;
revoke all privileges on table public.videos from authenticated;

grant select on table public.analysis_results to authenticated;
grant select, insert, update, delete on table public.profiles to authenticated;
grant select on table public.videos to authenticated;
