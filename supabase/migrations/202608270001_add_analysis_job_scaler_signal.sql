do $$
begin
  if not exists (
    select 1
    from pg_catalog.pg_roles
    where rolname = 'analysis_job_scaler'
  ) then
    create role analysis_job_scaler
      noinherit
      nologin
      nosuperuser
      nocreatedb
      nocreaterole
      noreplication
      nobypassrls;
  else
    alter role analysis_job_scaler
      noinherit
      nologin
      nosuperuser
      nocreatedb
      nocreaterole
      noreplication
      nobypassrls;
  end if;
end;
$$;

create or replace function public.pending_video_analysis_job_count()
returns integer
language sql
stable
security definer
set search_path = pg_catalog
as $$
  select count(*)::integer
  from public.analysis_jobs
  join public.videos on videos.id = analysis_jobs.video_id
  where analysis_jobs.job_type = 'video_analysis'
    and analysis_jobs.status in ('queued', 'retry_wait')
    and analysis_jobs.available_at <= pg_catalog.now()
    and videos.discarded_at is null;
$$;

revoke all privileges on all tables in schema public from analysis_job_scaler;
revoke all privileges on all sequences in schema public from analysis_job_scaler;
revoke all privileges on all routines in schema public from analysis_job_scaler;
revoke all privileges on schema public from analysis_job_scaler;

revoke execute on function public.pending_video_analysis_job_count()
  from public, anon, authenticated;

grant usage on schema public to analysis_job_scaler;
grant execute on function public.pending_video_analysis_job_count()
  to analysis_job_scaler;
