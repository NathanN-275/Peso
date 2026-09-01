#!/usr/bin/env bash
set -euo pipefail

: "${SUPABASE_DB_URL:?Set SUPABASE_DB_URL to the environment owner connection URL.}"
: "${AZURE_SCALER_POSTGRES_PASSWORD:?Set AZURE_SCALER_POSTGRES_PASSWORD.}"
: "${AZURE_SCALER_POSTGRES_ROLE:?Set AZURE_SCALER_POSTGRES_ROLE to peso_azure_scaler_student.}"

case "$AZURE_SCALER_POSTGRES_ROLE" in
  peso_azure_scaler_student) ;;
  *)
    echo "AZURE_SCALER_POSTGRES_ROLE must be an approved environment-specific role name." >&2
    exit 1
    ;;
esac

psql "$SUPABASE_DB_URL" \
  --no-psqlrc \
  --set=ON_ERROR_STOP=1 \
  --set=scaler_role="$AZURE_SCALER_POSTGRES_ROLE" \
  --set=scaler_password="$AZURE_SCALER_POSTGRES_PASSWORD" <<'SQL'
select format(
  'create role %I login password %L nosuperuser nocreatedb nocreaterole noinherit noreplication',
  :'scaler_role',
  :'scaler_password'
)
where not exists (select 1 from pg_roles where rolname = :'scaler_role')
\gexec

select format(
  'alter role %I with login password %L nosuperuser nocreatedb nocreaterole noinherit noreplication',
  :'scaler_role',
  :'scaler_password'
)
\gexec

select format('grant connect on database %I to %I', current_database(), :'scaler_role')
\gexec
select format('grant usage on schema azure_scaler to %I', :'scaler_role')
\gexec
select format('revoke all privileges on all tables in schema public from %I', :'scaler_role')
\gexec
select format('revoke all privileges on all sequences in schema public from %I', :'scaler_role')
\gexec
select format('revoke all privileges on all functions in schema public from %I', :'scaler_role')
\gexec
select format('revoke all privileges on all functions in schema azure_scaler from %I', :'scaler_role')
\gexec
select format('grant execute on function azure_scaler.analysis_queue_depth() to %I', :'scaler_role')
\gexec
select format('alter role %I set statement_timeout = %L', :'scaler_role', '5s')
\gexec
select format('alter role %I set default_transaction_read_only = %L', :'scaler_role', 'on')
\gexec
SQL

echo "Configured least-privileged Azure scaler role: $AZURE_SCALER_POSTGRES_ROLE"
