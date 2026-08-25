# Peso Production Readiness Review

**Status:** Beta readiness checklist | **Updated:** 2026-08-25

This review is the release gate for the focused web beta. It is not a claim that every exercise, camera view, or future coaching feature is production-ready.

## Readiness summary

| Area | Status | Evidence / remaining action |
| --- | --- | --- |
| Product scope | Ready with limits | Side-view squat is the supported path; frontal analysis remains limited. |
| Authentication and ownership | Ready | Supabase JWT and owner-scoped API/storage policies are implemented and tested. |
| Durable processing | Ready | Database-backed jobs, worker leases, heartbeats, recovery, and public stages are implemented. |
| Tracking quality | Beta / monitor | Pin-assisted tracking, quality preflight, diagnostics, and evaluation fixtures exist; continue collecting held-out failures. |
| Data safety | Ready with operational checks | Signed media access and cleanup controls exist; verify production environment values before release. |
| Automated verification | Ready to run in CI | `.github/workflows/security.yml` covers backend tests, frontend checks, audits, RLS/migration review, and secret scanning. |
| User documentation | In progress | Keep this review, the README, and backend deployment notes aligned with each release. |

## Release checklist

### Product

- [ ] Confirm the release only advertises supported side-view squat behavior.
- [ ] Verify upload, quality advisory, progress, review, save, discard, and history flows on web.
- [ ] Verify the same Saved Lift is readable and manageable on mobile.
- [ ] Confirm limited and failed results explain what the athlete can do next.

### Engineering

- [ ] Run `npm run typecheck`.
- [ ] Run `npm run test:policy`.
- [ ] Run `npm run dashboard:typecheck` and `npm run dashboard:build`.
- [ ] Run backend tests with production-like required environment variables.
- [ ] Apply and verify all Supabase migrations, RLS policies, storage buckets, and indexes.
- [ ] Confirm Render API and worker deployments use the same model/configuration version.

### Security and privacy

- [ ] Set `BACKEND_ENV=production` and explicit production CORS origins.
- [ ] Set non-placeholder service, JWT, cleanup, and storage configuration secrets.
- [ ] Verify signed URL expiration, upload limits, per-user quotas, and cleanup jobs.
- [ ] Confirm logs do not expose tokens, raw media, or unnecessary personal data.
- [ ] Review dependency and secret-scan results; resolve or document exceptions.

### Observability and support

- [ ] Confirm worker heartbeat, queue age, failure, timeout, and stale-job signals are visible.
- [ ] Confirm analysis diagnostics are retained for support and evaluation.
- [ ] Verify a user can recover from refresh, browser close, worker restart, and expired playback access.
- [ ] Record the deployed frontend, backend, migration, and model versions.

## Exit criteria

Release is approved when all required checklist items pass, no unresolved high-severity security issue remains, supported-flow smoke tests pass on web and mobile, and the owner accepts the documented limitations. Any unchecked item becomes a tracked follow-up rather than an implicit promise.

## Post-release review

Within the first beta cycle, review completion rate, failure/limited-result rate, queue latency, corrected reps, tracking identity failures, and support reports. Feed held-out examples into analysis evaluation before changing thresholds or claiming broader exercise/view support.
