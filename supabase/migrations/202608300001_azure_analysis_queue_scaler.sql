create schema if not exists azure_scaler;

revoke all privileges on schema azure_scaler
from public, anon, authenticated, service_role;

alter default privileges in schema azure_scaler
revoke execute on functions from public;

create or replace function azure_scaler.analysis_queue_depth()
returns bigint
language sql
stable
security definer
set search_path = ''
as $$
  select count(*)
  from public.analysis_jobs
  where status in ('queued', 'retry_wait')
    and available_at <= timezone('utc', now());
$$;

revoke all privileges on function azure_scaler.analysis_queue_depth()
from public, anon, authenticated, service_role;

comment on function azure_scaler.analysis_queue_depth() is
  'Returns only queue depth for the least-privileged Azure Container Apps scaler login.';
