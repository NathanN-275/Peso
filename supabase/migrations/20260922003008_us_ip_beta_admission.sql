-- Empty until a reviewed, versioned geography dataset is loaded. Unknown or
-- expired data denies admission. Do not enable the Auth hook before rehearsal.
create table public.us_beta_ip_ranges (
  network cidr primary key,
  source_version text not null,
  valid_until timestamptz not null
);
create index us_beta_ip_ranges_lookup on public.us_beta_ip_ranges using gist (network inet_ops);
alter table public.us_beta_ip_ranges enable row level security;
revoke all on public.us_beta_ip_ranges from public, anon, authenticated;
grant select on public.us_beta_ip_ranges to service_role, supabase_auth_admin;
create policy us_beta_ip_ranges_internal_read on public.us_beta_ip_ranges
  for select to service_role, supabase_auth_admin using (true);

create function public.is_us_beta_ip(p_ip inet)
returns boolean language sql stable security invoker
set search_path = public, pg_temp
as $$
  select coalesce(exists (
    select 1 from public.us_beta_ip_ranges
    where p_ip <<= network and valid_until > now()
  ), false);
$$;
revoke execute on function public.is_us_beta_ip(inet) from public, anon, authenticated;
grant execute on function public.is_us_beta_ip(inet) to service_role, supabase_auth_admin;

create function public.hook_us_ip_before_user_created(event jsonb)
returns jsonb language plpgsql security invoker
set search_path = public, pg_temp
as $$
declare
  client_ip inet;
begin
  -- Only Supabase Auth's metadata is authoritative, never user_metadata.
  begin
    client_ip := nullif(event->'metadata'->>'ip_address', '')::inet;
  exception when invalid_text_representation then
    client_ip := null;
  end;
  if event->'metadata'->>'name' = 'before-user-created'
     and client_ip is not null and public.is_us_beta_ip(client_ip) then
    return '{}'::jsonb;
  end if;
  return jsonb_build_object('error', jsonb_build_object('http_code',403,
    'message','This beta accepts signup from US IP addresses. VPNs and proxies may affect detection; IP location does not establish residency.'));
end;
$$;
revoke execute on function public.hook_us_ip_before_user_created(jsonb) from public, anon, authenticated, service_role;
grant execute on function public.hook_us_ip_before_user_created(jsonb) to supabase_auth_admin;
