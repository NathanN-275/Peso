-- A long transaction must not extend the lifetime of geographic admission data.
create or replace function public.is_us_beta_ip(p_ip inet)
returns boolean language sql volatile security invoker
set search_path = ''
as $$
  select exists (
    select 1 from public.us_beta_ip_ranges as allowed
    where p_ip <<= allowed.network
      and pg_catalog.isfinite(allowed.valid_until)
      and allowed.valid_until > pg_catalog.clock_timestamp()
  );
$$;
revoke execute on function public.is_us_beta_ip(inet) from public, anon, authenticated;
grant execute on function public.is_us_beta_ip(inet) to service_role, supabase_auth_admin;
