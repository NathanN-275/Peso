-- Dedicated disposable PostgreSQL fixture only. These are synthetic Auth stand-ins.
create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create role unrelated_caller nologin;
create schema auth;
create table auth.users (
  id uuid primary key,
  instance_id uuid not null default '00000000-0000-0000-0000-000000000000',
  aud text default 'authenticated',
  role text default 'authenticated',
  is_anonymous boolean default false,
  banned_until timestamptz,
  deleted_at timestamptz
);
create table auth.sessions (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default clock_timestamp(),
  not_after timestamptz,
  aal text default 'aal1',
  oauth_client_id uuid,
  scopes text,
  refresh_token_hmac_key text,
  refresh_token_counter bigint
);
create table auth.refresh_tokens (
  id bigint generated always as identity primary key,
  instance_id uuid not null default '00000000-0000-0000-0000-000000000000',
  user_id varchar(255) not null,
  session_id uuid references auth.sessions(id) on delete cascade,
  revoked boolean not null default false,
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp()
);
create index refresh_tokens_session_id_idx on auth.refresh_tokens(session_id);
alter table auth.users enable row level security;
alter table auth.sessions enable row level security;
alter table auth.refresh_tokens enable row level security;
revoke all on auth.users, auth.sessions, auth.refresh_tokens from public, anon, authenticated, service_role, unrelated_caller;
grant usage on schema auth, public to anon, authenticated, service_role, unrelated_caller;
