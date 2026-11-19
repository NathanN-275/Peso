# Public Web Beta Deployment Plan

On November 11, Nathan approved US-IP signup, uploads from abroad for signed-in
users, and separate fresh Render API and worker pairs for staging and production.
The decision supersedes earlier references to upload geography and reuse of the
old Render pair.
[Scope decision](../adr/0021-scope-us-ip-signup-and-replace-render-pair.md).

## Dedicated staging checkpoint — November 18, 2026

Nathan upgraded the owner-only Netlify staging team to Personal on November 18.
Staging uses `staging.usepeso.com`.
The protected holding deploy has verified HTTPS and anonymous denial. The
[dedicated staging binding](../../config/staging-web-release-binding.json)
is `private-config-verified` and records the Netlify site, Render services,
Supabase project and key fingerprints. Both selected Render services are
suspended. The next private staging upload requires exact artifact approval
and current deploy eligibility. [Current gate tracker](public-beta-acceleration-plan-20261105.md#current-gate-tracker--november-18-2026).

Signup is verified for its tested scope. Remaining hosted browser and Auth
checks still require an approved window. Media attestation and activation are
off pending supported provider settlement, scoped cleanup and hosted-role
rehearsal. [Dedicated staging preflight](dedicated-staging-preflight-20261116.md).

Remaining release order: finish Gate 3 credential retirement/rotation and
provider verification; pass staging acceptance, production geography refresh
and guardrails; obtain a fresh protected recovery point and separately approve
production migrations; verify production bindings and its private artifact,
then repeat required E2E acceptance; prepare protected release, final costs and
rollback evidence, and obtain public-launch approval before exposure.

Approved by Nathan in this chat on September 30, 2026. This replaces the older
plan's dependency on an unavailable source PDF. Target: the combined homepage
and authenticated `/app`, US-IP signup, and side-view squats.

## Current Web MVP scope — November 5, 2026

Nathan explicitly selected Render for the backend and Supabase for Auth, Postgres
and video Storage, excluding Azure from MVP runtime and deployment. The combined
marketing site, authenticated /app with US-IP signup, and side-view squat workflow remain
in scope. Existing data preservation and the mandatory security, recovery,
monitoring and user-flow checks below remain required. Follow the
[Azure-free runtime and preservation boundary](web-mvp-runtime.md); historical
Student/Azure work is outside this MVP. Action-time approvals remain in force.

## Execution contract

Nathan renewed the public Web Beta goal on October 25, 2026 and authorized
autonomous progress, recommended routine decisions and delegated work. Continue
through independent preparation, implementation and verification without a
routine approval between chunks. A failed required gate remains failed;
dependent release acceptance cannot advance until its blocker is resolved.
Report material changes, verification results and the next blocker concisely.
Keep credentials and backup contents outside Git. Record only sanitized
evidence and exact release identifiers. Preserve existing data and projects.
Commit messages include summary, what changed, why, affected systems, and tests.

Nathan explicitly approved the planned 40 marketing regression cases, relevant
existing checks, and local builds/audits, including fixing and rerunning
failures. This supersedes earlier spent single-use grants for this new local
work; it does not retroactively change their scope or results. Keep public
exposure, destructive data changes and new costs for final approval. Required
provider sign-in or protected human actions still need Nathan when unavailable
to the agent. See [the current execution contract](autonomous-public-beta-execution-20261025.md).

## Current evidence

Use the [November 16 readiness refresh](public-beta-readiness-20261116.md)
for the current source/CI reconciliation and all-14-gate status. Daybreak login
is not a prerequisite: repository-enforced CI, complete raw audit reports,
image identity and offline runtime evidence provide the Gate 2 evidence path.
The existing thresholds and candidate/artifact matching requirements still apply.

## Gates

1. **Freeze candidate:** reconcile working changes and PR #47, select a source
   SHA, run policy/type/backend tests, local builds with explicit non-production
   fixtures and migration audits. Production-build acceptance remains mandatory
   in Gate 11, as Nathan confirmed on September 30.
2. **Release security and offline runtime:** record the exact candidate source,
   lockfiles, patch identities, tested image and relevant runtime versions.
   Retain complete dependency/container reports. All CRITICAL and untreated
   HIGH findings block; a temporary HIGH treatment requires Nathan's approval
   of the exact finding, evidence, artifact scope and expiry, and must be
   accepted by enforced policy. Written approval never overrides a failing
   security job. The current web audit's no-HIGH-exceptions guard remains in
   force; this scope change does not alter audit policy. Complete matching
   evidence closes Gate 2 without another manual sign-off, subject to any HIGH
   treatment approval. Run the existing Linux build, patch-integrity and offline
   container checks for the candidate, preserving API/worker imports, native
   inference, media processing and supported-format coverage. Runtime versions
   must match the claimed candidate environment. Required checks, matching
   evidence, isolation and cleanup must succeed; missing evidence or unexplained
   failures block closure. Reuse earlier evidence only when its inputs and
   coverage still apply. Later build/cutover gates must bind the deployed
   artifact or repeat applicable checks; matching source alone does not prove
   arbitrary rebuilds are identical. Metadata and synthetic fixtures do not
   establish hosted compatibility. A boundary snapshot does not establish
   continuous isolation. Browser functionality and accessibility belong to
   Gates 11/12; historical exhaustive diagnostics are follow-up unless they
   establish release security impact. Preserve current CI jobs and enforcement.
3. **Credential history:** finish credential rotation or verified retirement,
   provider verification and documented GitHub Support disposition; verify
   secret scans. The [November 16 disposition](gate-3-support-disposition-20261116.md)
   resolves history removal for the documented revoked New Relic key; it does
   not establish a purge or close remaining credential work.
4. **Staging authentication:** dedicated staging Render services bound to
   `peso-staging` during approved test windows, with isolated test users,
   redirects, email, Turnstile, browser and required native authentication tests.
5. **Hosted recovery:** approved disposable target, logical restore, custom
   Storage policies, real owner/non-owner access and object-byte verification.
6. **Fresh recovery point:** verified writer freeze, private export, checksums,
   Storage inventory/bytes and verified protected off-machine copy.
7. **Production migrations:** review current dry run, apply reviewed chain,
   verify history, RPCs, RLS, grants and Data API behavior.
8. **US-IP signup:** authoritative geography source and refresh, managed Auth
   hook, and IPv4/IPv6, spoofing and expiry failure tests at signup.
9. **Guardrails:** retention/cleanup, budget alerts and intake stop, delivery,
   accepted-job draining, quotas and monitoring acceptance.
10. **Render cutover:** approved fresh production API and worker identities,
    matching PesoDatabase credentials, manual deployment, API readiness then
    worker acceptance and two longest-clip measurements. Retain the old pair
    suspended.
11. **Private Web App:** combined Netlify project, verified binding and production
    configuration, release build/budget, preview and historical URL privacy.
    Verify current login/signup shell, fonts and reload behavior; include the
    historical Firefox reproduction as diagnostic follow-up. Verify WebKit
    keyboard skip-link visibility at 1280x900 with reduced motion and at a
    mobile width, plus current visual regressions on the Marketing Site and
    Web App. Required accessibility failures block launch.
12. **End-to-end acceptance:** two owners; upload through analysis, save, export,
    deletion, recovery and mobile compatibility; isolation and expired sessions.
    Cover required browser user flows and real authentication, including
    authenticated uploads from abroad under the normal upload controls. The
    historical 120-page/33-control matrix, exhaustive source/input/visual
    comparison and remaining browser reproduction detail are diagnostic
    follow-up, not blanket Gate 2 prerequisites. Gates 11/12 own current visual
    regression acceptance. Any finding showing release security impact returns
    to Gate 2. Moving a requirement does not mark it passed or waive required
    launch acceptance.
13. **Protected release:** one main-to-production PR, required checks on the
    release SHA, recorded frontend/backend/migration/model identifiers.
14. **Public launch:** final costs, identities and rollback evidence; Nathan's
    action-time confirmation; public smoke tests and first-cycle monitoring.

## Fresh Render service preparation

Use `render-public-beta-staging.yaml` for the staging pair and
`render-public-beta.yaml` for the production pair. Both use the MVP Dockerfile,
manual deployments, and one Starter API and one 1 CPU / 2 GB worker. Bind
staging only to `peso-staging` with its own credentials and
`https://staging.usepeso.com` as the allowed Web App origin. Use
`https://api-staging.usepeso.com` from the dedicated staging binding and verify
HTTPS before each approved window. Keep signup disabled outside approved tests.

A new Git-backed service can build on creation. Before approving creation,
pin the linked branch tip to the reviewed SHA, verify its target workspace,
region, service names and configuration, and verify the exact deployed SHA
on both services. Stop the test window on a mismatch. Keep production creation
behind its migration and recovery gates. Retain the old pair suspended.

Use the recorded service identities in the verified staging configuration.
Record provider-assigned production IDs, Blueprint hashes and source revision
when verifying the pending production binding. Update the exact ID pins in
release validation and retain the committed-source scanner's exact-occurrence
review.
Use the [Web MVP production preflight](web-mvp-migrations.md#production-cutover-preflight)
before production cutover. Provision the fresh production pair after the
approved migration and verification pass.

## Source checkpoint and production acceptance

`PESO_RELEASE_ENV=public-beta` requires the private candidate binding that Gate
11 creates. Nathan approved separating Gate 1 source verification from Gate 11
hosted release-build acceptance on September 30. Gate 1 uses a local fixture
build with dotenv loading disabled; that output must never be deployed. Gate 11
must run production release validation and build/budget checks with the real
verified binding. Never bypass the validator or invent provider evidence.

A source SHA can identify a tested checkpoint; subsequent implementation gates
create new SHAs that require fresh applicable checks before release. Gate 1
cannot freeze the final release bytes before those changes exist.

## First-cycle monitoring handoff

During private production acceptance, verify that heartbeat, queue age,
failure, timeout and stale-job signals are visible on the exact release
services and database before requesting public exposure.
[PRR launch checklist](../product/PRR.md#observability-and-support)

Start the baseline when the approved production release becomes public. Use one
UTC observation window that includes the public smoke test. Record its bounds,
frontend source and Netlify deploy, API and worker deploys, production database
project, and the person who accepts ownership of the first-cycle PRR review.
Keep aggregate readings and evidence references in the release record. Keep raw
logs, user identifiers, credentials and billing receipts private.

| Reading | Evidence to retain |
| --- | --- |
| API and worker errors | Use the verified production Render service IDs and the same UTC range in each service's runtime logs. Record the count of returned error-or-higher entries, whether all pages were read, and any unresolved event class. If HTTP status-count metrics are available for the production API host, record total requests and 5xx responses. Mark missing status series unavailable and keep the runtime log and smoke request evidence. [Render logs](https://render.com/docs/logging) · [Render metrics](https://render.com/docs/service-metrics) |
| Analysis queue health | From the verified PesoDatabase project, record queued, retry-wait, processing and expired-lease counts and the age of the oldest job whose scheduled time has arrived. Use aggregate reads of `public.analysis_jobs` at a single stated database timestamp. Count each status separately. Within `queued` and `retry_wait`, count jobs with `available_at` at or before the timestamp and use the oldest such `available_at` for age. Count a `processing` lease as expired or invalid if it is missing, nonfinite or at or before that timestamp. These are table observations. A worker can skip a job while its owner or row is locked or cancel work for revoked media. |
| Queue latency | Confirm the public smoke job completes with the expected analysis outcome and match its exact job ID in the private logs of the verified worker deploy. For a newly queued job that completed on its first attempt, use an authorized read-only PesoDatabase query to measure `public.analysis_jobs.created_at` to `stage_timestamps.downloading` on that exact row. Both timestamps must be finite, timezone-aware, ordered and within the UTC smoke window. Record milliseconds and observation time as queue-to-reported download stage, which includes worker startup and progress reporting. If the job retried or the source or timing is unavailable, retain the job outcome and mark the timing unavailable. The current claim RPC omits the timestamps the worker needs to emit `queue_wait`. Capture first-cycle samples with the same measure. [Claim RPC](../../supabase/migrations/20261029180203_owner_analysis_admission.sql) · [Worker stages](../../backend/app/jobs/analysis_worker.py) |
| Spend and intake | Retain the current calendar-month actual and projected provider totals, their source timestamps, quota/headroom and the observed intake state. Read current credit usage and cycle dates in the production Netlify team’s Usage & billing page and record them separately. Record the enabled budget monitor run and any reached-milestone delivery receipts. [Intake and budget runbook](intake-stop.md) |
| Alert delivery | Confirm the receiving operator and an actual test or event receipt for each alert path required by the launch plan. Render service notifications cover provider service events. Budget alerts use the separate workflow and Gmail sender. Retain date, route and outcome without copying email contents. [Render notifications](https://render.com/docs/notifications) · [Budget email acceptance](intake-stop.md#hosted-acceptance-before-activation) |

Review the public smoke and privacy receipts before signing off the handoff.
Record a real zero only when the observation source returned a complete result.
The named owner reviews completion, failure and limited-result rates, queue
latency, corrected reps, Tracking Recovery and support reports during the first
beta cycle. [PRR post-release review](../product/PRR.md#post-release-review)

## Completion

All mandatory PRR gates pass, no blocking security finding remains, production
bindings agree, US-IP signup fails closed, two-user acceptance and recovery pass,
and Nathan authorizes public exposure. Local checks alone do not prove this.
