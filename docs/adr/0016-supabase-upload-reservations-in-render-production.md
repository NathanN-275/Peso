# ADR 0016: Use Supabase-backed upload reservations in Render production

## Status

Accepted

## Context

The isolated Render beta already proves the server-mediated Supabase upload
reservation path against `peso-staging`. The public beta uses the existing
Render API and worker with the separate production Supabase project, but its
Blueprint still defaults to Azure-backed reservations. Reusing the beta setting
without a production boundary could allow a staging service to point at the
production project, or the reverse.

## Decision

Use the existing `/upload-reservations` API contract and Supabase storage
provider for both production Render services. The browser continues to upload
only through the authenticated, owner-checked API; it never receives a
service-role key or direct source-upload permission.

`render.yaml` sets the following non-secret values on `Peso-backend` and
`peso-analysis-worker`:

- `PESO_DEPLOYMENT_ENVIRONMENT=production`;
- `UPLOAD_RESERVATIONS_ENABLED=true`; and
- `UPLOAD_STORAGE_PROVIDER=supabase`.

Runtime configuration maps each named environment to exactly one Supabase
project: `student` to `peso-staging` (`iseqgaewjpjcxrndibep`) and `production`
to production (`jfgiydtrskpqxyorvvbc`). A named environment with the wrong
project, an unknown environment, or Supabase reservations without a named
environment fails before a Supabase client is created.

Production Supabase credentials and the cleanup token remain Render-managed
secrets. The reviewed production migration must be applied before an accepted
backend deployment; this ADR does not apply a remote migration or deploy a
service.

## Consequences

- No user-facing API shape changes; production activates the existing
  reservation lifecycle.
- Production and staging remain mutually exclusive data and credential
  boundaries, even though both use the same provider.
- A production rollback must restore API and worker configuration together;
  additive reservation migrations remain in place unless separately verified
  safe to reverse.
