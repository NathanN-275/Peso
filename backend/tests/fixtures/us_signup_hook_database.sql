-- Disposable hook fixture: model a restore without Studio's implicit schema grant.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create role supabase_auth_admin nologin;
revoke usage on schema public from public;
grant usage on schema public to anon, authenticated, service_role;
-- No auth.users table: a before-user-created hook cannot depend on its new row.
