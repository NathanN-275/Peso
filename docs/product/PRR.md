# Peso Production Readiness Review

**Status:** Public beta blocked pending operational acceptance | **Updated:** 2026-11-09

The blocked status was revalidated on November 9. The approved isolated restore, synthetic-account cleanup and migration rehearsal have passed within their recorded scopes; production application and remaining hosted release acceptance are open. See the [current gate tracker](../deployment/public-beta-acceleration-plan-20261105.md) for the latest evidence and blockers.

This review is the release gate for the focused web beta. It is not a claim that every exercise, camera view, or future coaching feature is production-ready.

The public beta targets PesoDatabase (`jfgiydtrskpqxyorvvbc`) and a fresh
production Render API and worker. Separate staging services use `peso-staging`
during approved test windows. The combined homepage and `/app` release uses
US-IP signup and allows signed-in users to upload from abroad. Release proceeds
through the protected `main` → `production` path. Follow the
[scope decision](../adr/0021-scope-us-ip-signup-and-replace-render-pair.md)
and [approved gate sequence](../deployment/public-beta-launch-plan.md).
See the dated
[release evidence](../deployment/public-beta-release-20260920.md) for completed
checks and remaining blockers; local passes do not establish deployed acceptance.

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

## Gate 2: release security and offline runtime

Gate 2 requires matching evidence for the exact candidate. Record its source
commit, lockfiles, patch identities, tested image and relevant runtime
versions. Retain complete dependency and container reports. CRITICAL and
untreated HIGH findings block. Nathan must approve any temporary HIGH treatment
for its exact finding, evidence, artifact scope and expiry; enforced policy must
also support it, and written approval never overrides a failing security job.
The current web audit's no-HIGH-exceptions guard remains in force; this scope
change does not alter audit policy. Complete matching evidence closes Gate 2
without another manual sign-off, subject to any required HIGH-treatment approval.

Run the existing Linux build, patch-integrity and offline container checks,
covering API/worker imports, native inference, media processing and supported
formats. Runtime versions must match the claimed candidate environment. Required
checks and matching evidence must complete successfully, including isolation
and cleanup; missing evidence or unexplained failures block closure. Earlier
evidence applies only when its inputs and coverage still match. Later build and
cutover gates bind the deployed artifact or repeat applicable checks because a
matching source commit does not identify arbitrary rebuilds. Metadata and
synthetic fixtures do not establish hosted compatibility; a boundary snapshot
does not establish continuous isolation.

Browser behavior and accessibility are accepted in Gates 11/12. Gate 11 covers
the login/signup shell, fonts and reload behavior, plus WebKit keyboard skip-link
visibility at 1280x900 with reduced motion and a mobile width. Gate 12 covers
required browser user flows and real authentication. Gates 11/12 own current
visual regression acceptance. Required accessibility failures block launch.
The historical Firefox reproduction, full 120-page/33-control matrix and
exhaustive source/input/visual comparison are diagnostic follow-up unless a
finding shows release security impact, which returns to Gate 2. Moving an item
does not mark it passed or waive launch acceptance. Existing CI jobs and
security enforcement remain in force.

## Historical marketing-only preparation checklist

These items describe the earlier information-only launch path. Retain them as
historical preparation evidence; they are not the target of the approved public
beta deployment plan. All required full-beta gates still apply.

- [ ] Create a private `peso-marketing` project using package `web`, base root,
      `production` branch, private previews, and no branch deploys.
- [ ] Keep `peso-webapp` private and skip its production builds.
- [ ] Pass clean and post-Expo-export marketing builds and artifact verification.
- [ ] Verify desktop/mobile layout, navigation, legal pages, refresh, forced
      app/auth redirects, no backend requests, and security headers on a private Netlify preview.
- [ ] Verify production can become public while staging, previews, and every
      older app-containing deploy URL remain protected. Stop if unverified.
- [ ] Verify the production merge cannot deploy any backend; record and retain
      the existing backend deploy identity.
- [ ] Use one protected `main` → `production` PR with all required checks passing,
      including marketing-build, container-security, reservation-database-security,
      and the new marketing project’s exact Netlify preview check.
- [ ] Publish the marketing artifact with production visibility still private.
- [ ] Capture deploy ID, commit, URL, and current Netlify billing-cycle baseline.
- [ ] Record DNS/domain assignments; move apex and www to marketing, preserving
      unrelated DNS, apex primary, www redirect, and verified TLS for both names.
      If setup fails, remain private and restore the previous domain assignment.
- [ ] Obtain Nathan's action-time confirmation immediately before public visibility.
- [ ] Verify anonymous marketing access and redirected app/auth entry points;
      repeat checks against staging, previews, and historical deploy URLs.
- [ ] Restore private visibility immediately if isolation fails. Never roll back
      to an app-containing deploy while production is public.

See [marketing release evidence](../deployment/marketing-release-20260920.md).

## Public beta release checklist

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
- [ ] Record the exact production API/worker image or deployed commit and model
      versions, and verify the accepted Starter accuracy/memory evidence applies
      to that release. Do not reopen the cleared accuracy gate without a change
      that invalidates its evidence.
- [ ] Pass `npm run web:build:release` with verified production variables and
      `npm run web:budget` for the same output.
- [ ] Require container and reservation-database security checks alongside the
      existing GitHub security, production-source, and Netlify preview checks.

### Security and privacy

- [ ] Verify `BACKEND_ENV=production` and exact approved production CORS origins
      on the production API. Keep Student and private-beta origins isolated.
- [ ] Set non-placeholder service, JWT, cleanup, and storage configuration secrets.
- [ ] Verify signed URL expiration, upload limits, per-user quotas, and cleanup jobs.
- [ ] Confirm logs do not expose tokens, raw media, or unnecessary personal data.
- [ ] Review dependency and secret-scan results; resolve or document exceptions.
- [ ] Complete outstanding credential rotations, GitHub Support history-purge
      confirmation, and GitGuardian verification. A clean local Gitleaks scan
      does not prove cached pull-request history was purged.

### Observability and support

- [ ] Confirm worker heartbeat, queue age, failure, timeout, and stale-job signals are visible.
- [ ] Confirm analysis diagnostics are retained for support and evaluation.
- [ ] Verify a user can recover from refresh, browser close, worker restart, and expired playback access.
- [ ] Record the deployed frontend, backend, migration, and model versions.

## Exit criteria

Release is approved when all required checklist items pass, no unresolved high-severity security issue remains, supported-flow smoke tests pass on web and mobile, and the owner accepts the documented limitations. An unchecked required item blocks release; tracking it as a follow-up does not waive the gate.

## Post-release review

Within the first beta cycle, review completion rate, failure/limited-result rate, queue latency, corrected reps, tracking identity failures, and support reports. Feed held-out examples into analysis evaluation before changing thresholds or claiming broader exercise/view support.
