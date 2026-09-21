# Public beta release evidence — 2026-09-20

## Decision

**NO-GO: required operational and end-to-end acceptance remains incomplete.**
No release PR was opened or merged, no production deployment was triggered,
and no site visibility, provider credentials, or remote database schema was changed.
The private Render beta remains private. Supported public scope is side-view
squat analysis only.

## Candidate and verified targets

- Local candidate: `5f77461b4b5364022d27cecb0b74eba1d6cbc121`.
- GitHub `main`: `e190bf5457b9eef55b9a77549bf5b28fce11c4b8`.
  The local accuracy/memory commit is not yet on remote `main`.
- GitHub `production`: `6a9a07180cd3306df4d92c3cf7d8849d3d890288`.
  This branch SHA is not independent evidence of the published frontend version.
- Netlify project: `peso-webapp`, ID `230da8eb-f00e-45d4-ba54-95f2e26f21c4`.
  The UI reports the last published deploy on August 28 and production visibility
  **Private**. Published frontend commit still needs capture.
- Production website: `https://usepeso.com`.
- Production backend configured in Netlify:
  `https://peso-backend-3u4u.onrender.com`.
- Render service `srv-d9poevht0dsc73d07d3g`: Free Python 3 runtime, tracking
  `production`, last successful commit `6a9a07180cd3306df4d92c3cf7d8849d3d890288`,
  live deploy `dep-daaed1qjnfac738a8cig`. The production project lists only this
  service; no production worker was visible. This differs from `render.yaml`'s
  Starter Docker API and Standard worker. Confirm and prepare the production
  runtime conversion before release; do not assume merging deploys that topology.
  The two private Render beta services are suspended and were left unchanged.
- Production Supabase: `jfgiydtrskpqxyorvvbc` (`PesoDatabase`).
- Private staging Supabase: `iseqgaewjpjcxrndibep` (`peso-staging`).
- Candidate local container: `peso-backend:public-release-5f77461`, reported image
  ID `sha256:a416475e7fbd576722f77ba2d7087cfd062431453589dec546044eda70ea3132`.
  This is local scan evidence, not a published or deployed image digest.

## Completed validation

| Gate | Result |
| --- | --- |
| App typecheck | Pass |
| Repository policy tests | 207 passed |
| Dashboard typecheck/build | Pass |
| Dashboard tests | 17 passed across four files |
| Backend pytest | 485 passed, nine database tests skipped |
| Dedicated PostgreSQL 17 security tests | All nine passed separately; disposable localhost instance removed |
| Static migration/RLS audit | Pass |
| Production web release build | Pass with public values read from Netlify Production; dotenv loading disabled |
| Web budget on that output | 520,927 gzip JavaScript bytes / 614,400 limit; 58,224 font bytes / 204,800 limit |
| Node dependency audit | Pass under existing documented build-tool exceptions for brace-expansion and image-size; no new exceptions |
| Python dependency audit | All 73 installed candidate-container package versions audited; no known vulnerabilities |
| Gitleaks | No leaks across 225 locally reachable commits; redaction enabled |
| Container build | Pass using repository Dockerfile and `--pull` |
| Offline container runtime | Pass as UID/GID 10001, read-only filesystem, no network, dropped capabilities; inference, API/worker imports, codecs, rotation, thumbnails, exports and upload formats |
| Trivy 0.74.0 | Zero HIGH/CRITICAL findings with freshly downloaded DB; unfixed findings included; exit code zero |
| Staging migration history | All 23 repository migrations applied, through `202609030001` |
| Staging security advisors | No warnings/errors found |

The initial release build attempt had no public variables and correctly failed.
It was rerun successfully after reading the actual Netlify production values.
The initial Node audit was network-blocked and passed with network access.
The Mac requirements-based Python audit could not resolve Linux-only MediaPipe
0.10.30. The successful replacement audit inventories every installed package
from the candidate Linux image, then uses `pip_audit --no-deps --disable-pip`
on those pinned versions; it does not omit transitive runtime packages.

GitHub security run [35273068977](https://github.com/NathanN-275/Peso/actions/runs/35273068977)
passed backend, frontend, secret, container, and reservation-database checks for
remote `main`. Its production-source job was skipped because it was not a
production PR. Those checks do not cover local candidate `5f77461`.

## Provider checks and remaining blockers

### Supabase

Production migration history ends at `202608270001`. A successful read-only
`supabase db push --linked --dry-run` lists these pending migrations:

- `202608300001_azure_analysis_queue_scaler.sql`
- `202609030001_upload_reservations.sql`

Do not claim upload-reservation production readiness before applying and
verifying the reviewed migrations during the coordinated release. Staging is
already current, so no staging migration write was needed.

Production security advisors reported four warnings: disabled leaked-password
protection and GraphQL schema visibility for `profiles`, `videos`, and
`analysis_results`. All five existing public tables have RLS enabled. The three
flagged tables have authenticated owner-scoped SELECT policies, including
video ownership for analysis results. Schema discoverability alone is not
evidence of cross-user row access; live two-user API/storage acceptance is
still required. Review leaked-password protection availability and configuration.

Production storage metadata confirms private `videos`, `profile-avatars`, and
`saved-lift-exports` buckets. Videos have a 50 MiB limit and an explicit video
MIME allowlist; avatars have a 512 KiB limit and an image allowlist. This does
not verify signed URL expiry, cleanup execution, deployed quotas, or ownership
isolation through every API path.

### Netlify and GitHub

Netlify Production variables were read and match the existing production
backend and Supabase project. `PESO_RELEASE_ENV=production`; the challenge URL
is `https://usepeso.com/auth/turnstile/`; the Turnstile site key is not a known
Cloudflare test key; a public Supabase publishable key is configured. No secret
values are recorded here.

The current Netlify-hosted homepage explicitly describes side-view squats.
`/app/signup` renders; unauthenticated `/app/saved-lifts` routes to login.
These are existing-deploy route checks in the signed-in operator browser,
not anonymous public-access or release-preview acceptance. Netlify explicitly
reports both production and Deploy Preview visibility as Private.

Separate unauthenticated HTTP probes returned **401** for `https://usepeso.com/`
and its `/auth/turnstile/` page. The production backend `/health/ready` timed
out on the first probe and returned **503** for subsequent production-origin
and untrusted-origin probes. Backend readiness and live CORS therefore remain
blocked, not passed. Resolve service health before production acceptance.

The active [Protect production ruleset](https://github.com/NathanN-275/Peso/rules/22210122)
requires PRs, blocks deletion and force pushes, has no bypass actors, and
requires up-to-date branches plus backend-security, frontend-security,
secret-scan, production-release-source, and netlify/peso-webapp/deploy-preview.
It does **not** require container-security or reservation-database-security;
add these before the release merge. The connector can read the ruleset but
cannot administer branch protection; the local GitHub CLI authentication is
invalid. No open PRs were returned by the repository search.

### Credentials and full acceptance

The September 13 security report still identifies outstanding Student scaler,
GitHub, and Key Vault credential work, GitHub Support purge confirmation for
retained PR #38 history, and a GitGuardian rerun. No new provider evidence
closing those items was supplied. Local Gitleaks does not cover GitHub's
retained pull-request refs or cached views. Coordinate rotation across all
consumers and verify the worker before marking it complete.

The browser E2E command failed at its staging precondition. The runner lacks
the required staging URL, admin-fixture credentials, and isolated signup inbox
and password. Do not substitute production credentials or remove the guard.
Signup/login/reset, upload/analysis/save/discard/playback/history, refresh,
browser close, worker restart, expired URLs, failure/retry, and two-user isolation
remain unverified for the release candidate.

Maestro is unavailable and installed Xcode is 16.4, below the runbook's 26.4
minimum. Mobile shared-Saved-Lift acceptance remains incomplete.

## Resume order

1. Close provider credential, GitGuardian, and Support purge blockers; obtain
   the staging runner fixture configuration without placing secrets in chat.
2. Complete staging/browser/mobile acceptance and record backend/model versions.
3. Review production migrations, runtime secrets, exact CORS, quotas, signed
   URLs, cleanup and sanitized logging; capture the rollback deploy identity.
4. Enforce the missing GitHub checks. Publish the validated candidate to `main`
   through the approved integration path and verify its exact commit checks.
5. Open one `main` → `production` release PR, validate its Netlify preview at
   `/`, `/app/signup`, and an app deep link, then merge only after all PRR gates
   pass. Coordinate production schema/backend/frontend versions as one release.
6. Complete the production visibility change and live smoke test only at launch.
   Browser-based access expansion requires action-time confirmation.
7. Capture the Netlify billing-cycle baseline and monitor completion/failure,
   limited results, queue latency, corrected reps, tracking failures and support
   reports. Start the first-cycle monitoring window at the actual launch; no
   monitoring results or launch date are claimed here.

## Local evidence

Sanitized command outputs and the Trivy JSON report are retained in
`artifacts/public-beta-release-20260920/` (gitignored). The report describes
observed results without copying credentials, auth links or user media.
