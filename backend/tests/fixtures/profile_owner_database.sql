-- Synthetic provider-shaped metadata only; no Storage server or backing bytes.
create function auth.uid() returns uuid language sql stable set search_path='' as $$
  select nullif(pg_catalog.current_setting('request.jwt.claim.sub',true),'')::uuid
$$;
create function storage.foldername(name text) returns text[] language sql immutable as $$
  select (string_to_array(name,'/'))[1:array_length(string_to_array(name,'/'),1)-1]
$$;
create function storage.extension(name text) returns text language sql immutable as $$
  select reverse(split_part(reverse(name),'.',1))
$$;
create table storage.objects (
  id uuid primary key default gen_random_uuid(),bucket_id text not null,name text not null,
  metadata jsonb,unique(bucket_id,name)
);
alter table storage.objects enable row level security;
grant usage on schema storage to authenticated,service_role;
grant select,insert,update,delete on storage.objects to authenticated,service_role;
grant insert on auth.users to supabase_auth_admin;

-- Model the trusted provider's signup INSERT authority in this synthetic schema.
create policy fixture_auth_signup on auth.users for insert to supabase_auth_admin with check(true);
