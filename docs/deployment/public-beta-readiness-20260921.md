# Combined public web beta readiness — 2026-09-21

Status: **NO-GO; implementation and operational acceptance are incomplete.**
Source requirements: Nathan's `peso_public_web_beta_launch_plan.pdf`, dated
September 21. This report records fresh observations separately from historical
evidence. It does not authorize publication, spending, migrations, or deletion.

## Candidate and working tree

- Inspected branch: `main`; HEAD `4572479745a85abca43e75c9f16fb17418d52bdf`.
- Pre-existing local modifications: `CONTEXT.md`, `docs/product/PRD.md`, and
  `docs/product/PRR.md`; pre-existing deletions:
  `docs/adr/0018-public-web-beta-release-scope.md` and
  `docs/deployment/public-beta-launch-plan.md`. Preserve these edits.
- Fresh baseline: app TypeScript check passed; all 215 repository policy tests
  passed. These checks do not prove deployed or human acceptance.
- GitHub CLI authentication is invalid. PR creation and protection verification
  require a working authenticated path.

## Verified provider inventory

Read-only Render connector inspection on September 21:

| Resource | Identity | Observed configuration |
| --- | --- | --- |
| Beta API | `srv-dak9ohfqj5pc73ac2ga0` | Suspended; Oregon; Starter; Docker; repository root; `./Dockerfile`; health `/health/ready`; `main`; automatic deploy off |
| Beta worker | `srv-dak9ohfqj5pc73ac2g8g` | Suspended; Oregon; Starter; Docker; command `python -m app.jobs.analysis_worker`; 300-second shutdown grace; `main`; automatic deploy off |
| Historical production API | `srv-d9poevht0dsc73d07d3g` | Not suspended; Ohio; Free Python runtime; root `backend`; health `/health`; `production`; automatic deploy off |

Render workspace: `tea-d9poa1h42hec73f5k580`. No resources were resumed or
modified. Account rates, credits, disks, environment names, deployment image
identities, log retention, and usage still require verification. Do not apply
the root `render.yaml` as a description of the existing beta: it declares
different service names and a Standard worker.

Read-only Netlify dashboard inspection on September 21:

- Display name `usepeso.com` resolves to project `peso-webapp`, ID
  `230da8eb-f00e-45d4-ba54-95f2e26f21c4`.
- Its production visibility and Deploy Preview visibility are both **Private**.
- Overview shows `https://usepeso.com/`, repository `NathanN-275/Peso`, and last
  published August 28. Exact domain assignments, TLS and deployed commit remain
  to be captured; an overview link alone is not DNS evidence.
- Separate `peso-marketing` project exists and is marked Private in the project
  list; exact ID, bindings and preview visibility still require inspection.
- No project or access-control settings were changed.

Subsequent domain-management inspection confirms `usepeso.com` as the primary
domain on `peso-webapp`, `www.usepeso.com` configured to redirect to it, and
Netlify's Let’s Encrypt certificate covering both names (auto-renew before
November 26). Independent DNS/anonymous TLS probing remains open.

Historical September 20 evidence identifies production Supabase
`jfgiydtrskpqxyorvvbc` and isolated staging `iseqgaewjpjcxrndibep`. Current plan,
migrations, backups, authentication settings, storage headroom and advisors
are **not yet reverified**. Nathan's selection of the eventual public database
is pending; do not repurpose staging or transfer its data to production.

## Confirmed implementation gaps

1. Netlify dispatch exports the app only for the historical app project's
   `main` branch deploy. Other deploys produce marketing; historical app
   production builds are explicitly skipped. A new combined project needs an
   explicit build binding without changing historical project behavior.
2. Homepage links still lead to `/beta`, with preview-only wording. Combined
   artifacts need signup links while preserving the existing visual design and
   historical marketing-only artifact.
3. Backend unsaved retention defaults to 24 hours, not the required 72 hours.
   Cleanup deletes media then marks the row discarded; it does not remove
   associated results. Candidate selection followed by storage deletion also
   needs a database-backed save/cleanup race solution.
4. Budget admission already has an authenticated disable webhook and durable
   reservation guard. Actual spend/resource triggers, accepted-job completion,
   leak checks, and manual resume require verification.
5. US-IP admission, including direct signup bypass protection and trustworthy
   proxy provenance, has not been established.
6. The tracked Render beta release binding is `pending`; it must not be marked
   accepted without measured runtime evidence.

## Required evidence still open

- Exact private candidate deploy, route/deep-link/assets checks and bundle
  credential inspection; complete desktop and phone-browser E2E.
- Worker restart, queue/concurrency/reservation isolation and cleanup races;
  60/90-second benchmarks using Nathan's clips, with queue time separate.
- Versioned acceptance clips and reviewed tracking annotations; sampled visual
  evidence without calling model outputs ground truth.
- Fresh backend/integration/database isolation tests, dependency/secret/container
  scans and shared native compatibility checks for the final candidate.
- Scoped credential remediation, retained Git history purge status and current
  security findings; old scan results are historical only.
- Production-capable email sender, verification/reset delivery and legal review;
  account deletion, support and retention wording.
- Migration order, backup limitations, restore rehearsal, compatible rollback,
  outage procedure, projected total billing and tested intake stop.
- Protected release PR and manifest; Nathan's private E2E acceptance and distinct
  final launch confirmation; production smoke tests and launch monitoring.

## Approval boundaries

Keep existing sites and all candidate deploys access-controlled. Before paid
provisioning, service resumption with billing impact, increased capacity,
destructive operations, DNS changes or publication, present the exact operation,
impact, cost and rollback to Nathan. The $35 alert and $50 target do not authorize
spending. No production migration or launch is approved by this report.

## Local implementation and verification checkpoint

- Added `config/combined-web-release-binding.json` with a deliberately unbound
  `site_id`. Dispatch can build the complete artifact for a reviewed new project
  in production, preview and branch contexts. Existing projects retain their
  previous behavior. Bind only after verifying new-project access controls;
  the binding is not itself an access-control mechanism.
- New-project configuration is prepared in `netlify.combined.toml`, retaining
  route and security-header behavior without the historical `main` branch's
  hardcoded staging Supabase/API variables. Select this config for the new
  project; configure separately reviewed public values in each deploy context.
- Combined artifacts now link homepage/header/footer CTAs to `/app/signup`;
  marketing-only artifacts keep `/beta`. Existing layout is preserved. Footer
  already has a bounded 88px wordmark rule; further mobile visual QA is pending.
- Changed API unsaved TTL default to 72 hours and documented the environment
  setting. Prepared migration `202609210001_unsaved_video_retention.sql` to
  align the database default; it has **not** been applied. Existing deadlines
  are untouched. Full deletion and race-safe retention remain open.
- Privacy draft describes the requested three-day/no-training policy while
  explicitly retaining deletion-verification and legal-review launch gates.
- Web signup no longer requires a US-residency declaration. Copy and its E2E
  expectation now match the requested IP-based audience. Backend geo admission
  and direct Supabase signup enforcement remain required before launch.
- App typecheck passed; 217 policy tests passed. Backend baseline: 485 passed,
  nine database tests skipped, 34 subtests passed. The first backend invocation
  used the wrong working directory and failed collection; rerunning from
  `backend` passed. The added retention-default test and cleanup suite then
  passed all 24 tests after fixing the test's missing cleanup-token fixture.
- Marketing build passed its artifact verifier. Combined build passed with
  **dummy public configuration**, dotenv disabled. This is compilation evidence,
  not a production release build or acceptance of the pending Render binding.
  Latest startup JS: 520,897 gzip bytes (614,400 limit); fonts: 58,224 bytes (204,800
  limit). Static Supabase security audit and whitespace check passed.
- Local browser inspection verifies signup CTA destinations and unchanged
  homepage layout. Signup opens and survives direct refresh with the updated
  audience wording. Demo media initially appeared unavailable before lazy
  loading; scrolling to its section verified readyState 4, no media error,
  active playback at 12.67 seconds of 18.93 seconds. Complete phone/app route QA
  is still pending. Dummy Turnstile configuration reports verification errors;
  this build cannot establish real authentication acceptance.
- Supabase CLI has no authenticated access token; live inspection needs the
  signed-in dashboard or restored CLI authentication. No secret was requested
  in chat or copied into this report.
