# Local production-security verification — 2026-09-03

This is local implementation evidence, not production acceptance. No cloud resources, remote database migrations, provider settings, or deployed clients were changed.

## Verified locally

- Full backend pytest suite: 453 passed, 9 skipped, 29 subtests passed. The nine database tests require a dedicated database and were executed separately below.
- Real PostgreSQL 17 integration suite: 9 passed against a disposable localhost database. This exercised the actual reservation migration, concurrent count/byte limits, validation leases, foreign-owner rejection, client-role privileges, expiry, persistent budget shutdown, verified-only queue admission, queue limits, and account-deletion tombstones.
- Frontend/repository policy suite: 172 passed. TypeScript typechecking and the migration/RLS audit passed.
- Student and security-foundation Bicep templates compiled locally without errors. Compilation does not establish Azure service availability, runtime RBAC behavior, or successful deployment.
- Backend Docker image built successfully. Offline API, worker, and cleanup imports passed as UID 10001. The allowlisted build context was 1.116 MB and excluded local environments and media.
- Python and Node dependency audits passed with the repository's existing documented exceptions. This does not waive the new high/critical container scan gate.
- Gitleaks found no secrets in the staged implementation patch. Whitespace validation passed.

## Release blockers and outstanding evidence

- Full-history Gitleaks found a credential-shaped value in the deleted historical file `backend/newrelic.ini`, line 33, commit `7569775929945f66a33d95f08f2fff8efec4bbae`. The value was redacted and is not reproduced here. Its revocation/rotation status is unknown. No history rewrite or scanner exception was made; resolve the finding before claiming a clean repository-history scan.
- Trivy scans are configured to fail CI and deployment on high/critical findings; a local Trivy image scan was not executed. The candidate image must pass that gate before deployment.
- All real-Azure acceptance cases in [the staging gate](production-security.md) remain outstanding, including SAS replay/expiry enforcement, cross-owner blob access, alert-to-shutdown delivery, cleanup, resource limits, cost, migration/rollback, deletion verification, and restore drills.
- Supabase authentication controls, privileged-operator MFA, GitHub required checks/environment reviewers, alert recipients, and Key Vault secrets require operator verification. No credentials were added to app environment files.
- Upload reservations remain disabled by default. Do not release the reservation client until the matching backend, migration, storage, and rollback gates pass. Paid-subscription approval remains required before uncapped public growth.
