-- Auth must resolve the invoker hook after restore without relying on Studio grants.
grant usage on schema public to supabase_auth_admin;
