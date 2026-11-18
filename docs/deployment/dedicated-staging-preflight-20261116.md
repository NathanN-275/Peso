# Dedicated staging preparation and quote — November 16, 2026

The owner-only Netlify Free project now serves the approved holding page.
Both staging DNS records and TLS certificates verify. The final release binding,
media activation and hosted application acceptance remain open.
This record authorizes no spending, credential deletion, provider or DNS write,
service resume, deployment, database change, fixture mutation or public launch.

## Verified privacy and cost

Signed-in Netlify dashboard: team `nathann-275`, credit-based **Free**, $0/month,
300 monthly credits, **223.4 remaining** at inspection. Team default is
**Private for new projects**. The project list has `peso-public-beta`,
`peso-marketing` and `peso-webapp`; no `peso-staging-web` was present.
No existing project's access settings were changed or freshly certified here.

[Netlify project visibility](https://docs.netlify.com/manage/security/secure-access-to-sites/project-visibility/)
supports owner-only private projects on Free/Personal and invited members on
Pro. The account's plan-selection screen quotes **$20/month for Pro**, unlimited
members, 3,000 credits/month. No upgrade was selected. Nathan-only staging can
use Free; the requested authorized-tester access needs the paid-plan decision
before inviting testers. Nathan selected **Nathan-only Free staging for now**;
no upgrade is requested. Do not share Nathan's session for tester access.

Protect production deploys **and** previews. After creation, independently test
anonymous denial on the custom hostname, default hostname, deploy permalinks,
`/app`, challenge assets and static assets. Separately verify private build/deploy
logs and anonymous dashboard/API log denial: project visibility does not prove
log privacy. Verify existing projects remain private. Disable automatic
publishing, builds/auto deploy, branch deploys and PR previews before content
upload. Leave Git disconnected for the manual-artifact path if possible.

Current [Netlify pricing](https://www.netlify.com/pricing/): one main-domain
deploy consumes 15 credits even while private, bandwidth is 20 credits/GB,
requests are 2 credits/10,000. Manual artifact upload needs no Netlify build.
For one candidate plus one rollback, 1 GB and 10,000 requests, budget **52
credits**; this is an example usage envelope, not permission or a measured
forecast. Free has a hard limit; do not enable paid recharge automatically.

Signed-in Render workspace `tea-d9poa1h42hec73f5k580`: **Hobby**, 0/2 included
custom domains used, 3/500 included pipeline minutes used, 86 MB/5 GB included
bandwidth used. These workspace totals are shared and can change.
[Current overages](https://render.com/articles/render-hobby-vs-pro-vs-scale)
are $5 per additional 1,000 Starter pipeline minutes, $0.15/GB outbound and
$0.25/month per domain above the allowance. A single API custom domain fits
the observed allowance; recheck immediately before approval and creation.

Both inspected staging pairs remain suspended, one API/worker instance each.
Each API is 0.5 CPU/512 MB at **$7/month**; each worker is 1 CPU/2 GB at
**$25/month**. Two hours for one pair is approximately **$0.089 compute** using
November's 720 hours; billing granularity, build time, usage and tax remain
separate. Do not resume both pairs. No paid resumption occurred.

## Source and service selection

Nathan approved merging GitHub `main` at `e9370d9f` into
`fix/merged-source-secret-coverage`. Local merge `1c8d66e4` brings in the Web
MVP private media runtime and the current dependency policy. The local staging
changes were restored from a retained stash and reconciled with the incoming
release and fixture controls. The deployment SHA remains pending final
provider binding and release validation.

| Pair | API / worker IDs | Observed source / deploy identity |
| --- | --- | --- |
| Historical `peso-beta-*` | `srv-dak9ohfqj5pc73ac2ga0` / `srv-dak9ohfqj5pc73ac2g8g` | `0191ff59ca9eea8dcfa54c0abc84bb7473482dda`; API `dep-db1bs3favr4c73b6eea0`, worker `dep-db1bs37avr4c73b6eclg` |
| Fresh Web MVP `peso-public-beta-staging-*-mo9c` | `srv-dbrrjqjrjlhs73cbn6b0` / `srv-dbrrjqjrjlhs73cbn6bg` | Render source `a43705709d1c1652bed86ee190a2afdd3ea7fcab` on both. API `dep-dbt4qpec6qcc73ao1u8g`, worker `dep-dbt4qqrbc2fs73d4agcg`. |

Render's deploy list did not include the image digests. Capture image identities
and the configuration snapshot before approving deployment or relying on rollback.

The newer readiness runbook identifies the fresh pair, which Nathan selected.
Historical bindings are preserved; the dedicated binding selects the fresh pair. The
active `render-beta.yaml` says Starter/Starter, which disagrees with the hosted
worker size; do not apply it and inadvertently reduce compute. The newer
`render-public-beta-staging.yaml` selects 0.5c-512mb/1c-2g and Dockerfile.mvp.

## Database/media prerequisite readback

Supabase confirms `peso-staging`, ref `iseqgaewjpjcxrndibep`, **ACTIVE_HEALTHY**,
region us-west-2. Only this project was queried. Storage buckets `videos` and
`profile-avatars` are private. Catalog reads find owner policies and private
media RPCs, including service-role-only execution for the provider-session and
grant authorization functions. This establishes catalog presence, not full RLS,
migration, credential or runtime acceptance.

`public.private_media_provider_policy` currently has **enabled=false**, with
version, settings, `verified_at` and `verified_until` all null. The implementation
requires a current attested policy before authorizing media. Do not enable
frontend/backend flags or populate the policy speculatively. Verify current
hosted Auth version/settings and the candidate's supported policy, migrations,
RLS and RPC grants; prepare any required database write for separate approval.
No user, session, Storage object or application row was changed.

## Concrete provider/configuration sequence after approval

1. Create `peso-staging-web` privately under the verified team. Capture its
   actual UUID; leave the release binding pending until readback. Reject the
   historical and production project IDs. Verify all hostname/log protection
   before deploying an artifact. Keep existing projects private.
2. Add `staging.usepeso.com` as the project's ordinary custom domain. Keep
   Cloudflare nameservers and existing apex/www/mail/branch records. Proposed
   DNS-only CNAME: `staging` to the provider-confirmed
   `peso-staging-web.netlify.app` target, TTL 300. Follow
   [Netlify external DNS](https://docs.netlify.com/manage/domains/configure-domains/configure-external-dns/).
   This does not use branch TLS. Existing ticket **#1196583** no longer blocks
   this design; no cancellation, resolution or new Support message is implied.
3. Associate `api-staging.usepeso.com` with the selected existing API only.
   Proposed DNS-only CNAME: `api-staging` to the fresh API's provider-confirmed
   hostname `peso-public-beta-staging-api-mo9c.onrender.com`. The historical
   `peso-beta-api` must remain untouched. No worker domain is needed.
   Follow [Render domains](https://render.com/docs/custom-domains).
4. Verify both managed certificates, hostname/chain/expiry and ordinary HTTPS
   without bypasses before Auth/Turnstile/CORS changes. Record anonymous
   Netlify denial on every URL class independently of authenticated access.
5. Prepare exact staging Auth Site URL/redirects (`/app/login`, `/app/reset`),
   retain required native callbacks and existing authorized staging flows.
   Restrict the real Turnstile widget to `staging.usepeso.com`; keep its secret
   in staging Auth. Browser CORS is exactly `https://staging.usepeso.com`.
   Media public origin is `https://api-staging.usepeso.com`; browser allowlist
   is exactly `https://staging.usepeso.com`. Do not allow default provider or
   sibling hosts to issue browser grants. Preserve Strict host-only cookies,
   owner/session checks, host validation, no-store and log redaction.
6. Repository guards now add an exact dedicated staging binding and
   `PESO_RELEASE_ENV=web-staging`. Require its UUID, isolated Supabase, exact
   web/API/challenge origins, verified public key and real Turnstile key.
   Reject production credentials, backend overrides, previews, branch builds
   and unexpected contexts. Keep historical dispatch unchanged. Require matching
   frontend/backend activation only after database/provider prerequisites.

The binding is `config/staging-web-release-binding.json`. Its actual site ID is
now recorded. Public-key SHA-256 and Turnstile-key SHA-256 remain null; status is
pending and both activation fields are false. Only set `private-config-verified`
after recording the actual site identity, privacy/log settings, valid TLS,
verified staging public key and real widget configuration. This status attests
configuration prerequisites, not completed hosted acceptance.

`scripts/netlify-build.js` dispatches this project only for external manual
production-context builds and forces `web-staging`; provider-build contexts and
previews fail. The ignore script stops automatic staging builds. Manual artifacts
contain `peso-release.json`, `_headers` and `_redirects`; the latter two preserve
security/cache headers and direct `/app` reloads during dashboard uploads.
Historical Netlify TOML and Render bindings remain unchanged.

For the final release build, set `SITE_ID` to the recorded UUID,
`PESO_RELEASE_ENV=web-staging`, `CONTEXT=production`, `COMMIT_REF=<full clean SHA>`,
`URL=https://staging.usepeso.com` and `EXPO_NO_DOTENV=1`, plus the verified
`EXPO_PUBLIC_*` values. `NETLIFY=true` and PR contexts are rejected. The validator
checks exact fingerprints and the build rechecks public-key acceptance against
the staging Auth endpoint. Do not populate the binding with synthetic values.

E2E additionally requires `PESO_E2E_SITE_ID`, `PESO_E2E_SOURCE_SHA`,
`PESO_E2E_API_URL=https://api-staging.usepeso.com`,
`PESO_E2E_WEB_BASE_URL=https://staging.usepeso.com`, the staging Supabase URL
and runner-only administrative key, unused signup email/password,
`PESO_E2E_STORAGE_STATE=<absolute private visitor-state file>` and
`PESO_E2E_RECEIPT_DIR=<absolute private directory outside this repository>`.
Keep the existing explicit fixture authorization variables. Global setup checks
the protected hosted artifact identity and verifies the administrative key
against staging before either spec creates a fixture. Browser Auth requests and
generated links are restricted to staging; fixture receipts record created IDs.
These login/recording tests do not implement full two-owner media acceptance.

## Two-hour acceptance window — prepared, not scheduled or approved

The schedule below describes full media acceptance. The later
[hosted acceptance readback](#hosted-acceptance-and-fixture-cleanup) records
the current media blockers and Nathan's decision for the first window.

Choose the start/end with Nathan after source, binding, privacy, TLS and media
policy prerequisites pass. The two-hour compute interval starts at first resume
and includes deployment/readiness/cleanup; stop on a prerequisite failure.
No automatic extension or compute resize. Render currently advertises
maintenance November 17 at 9 PM Eastern; recheck provider status when scheduling.

Before approval: select one clean reviewed full SHA; run focused dispatch,
origin, activation and fixture-isolation checks plus applicable existing
security/type/build/container/database checks. Verify real staging credentials
privately. Build once with dotenv inheritance disabled and verified staging
values; checksum a sorted frontend file manifest and the exact upload archive.
Prepare a minimal provider/DNS/config diff with previous values and costs.

After explicit deployment/spending approval: manually deploy API and worker
from that same SHA and upload that exact frontend artifact via Netlify manual
deployment. Record full source SHA, frontend manifest/archive checksums, Netlify
site/deploy ID, both Render service/deploy IDs, image identities/digests and
model versions. A source SHA alone does not prove identical backend images.
Current observed deploys above are rollback candidates, not accepted rollback
artifacts until their bytes/configuration and protection have been recorded.

Use headed Playwright with Nathan's interactive Netlify visitor login. Keep
storage state, fixture receipts, emails and traces privately outside Git with
directory 0700/files 0600. Use a separate empty browser context for anonymous
protection checks. Do not bypass the gate with injected cookies or a public URL.
After the protected hostname serves the approved artifact, open it in
Playwright Chromium with `playwright codegen --save-storage <private-state-file>
https://staging.usepeso.com`. Sign in to Netlify as the visitor, verify the
Peso sign-in page is accessible, then close the window to save the state.
Use `umask 077` and an absolute path outside Git. Leave Peso signed out so each
test starts with only Netlify visitor access.
Before any administrative fixture mutation, verify deployed site ID, artifact
SHA/configuration, API service IDs, database URL and credential against staging.
Use unique per-run users and durable ownership receipts; fail on existing signup
addresses and clean up only identities/objects created and recorded by that run.
Preserve existing staging users/data. Generated Auth links do not prove email.

| Window | Required observations |
| --- | --- |
| 0–20 min | Manual deployment/readiness, binding readback, anonymous gate and direct `/app` reload, exact CORS, visitor login |
| 20–40 min | Real signup/confirmation/reset email and CAPTCHA; expiry/retry; create two isolated owners only after guards |
| 40–90 min | Two-owner upload → validation → queue → analysis → playback → save → export → deletion/recovery; cross-owner denial; two longest accepted clips |
| 90–110 min | Logout/revocation and expired sessions; current UI, required browser/mobile, keyboard/reduced-motion/viewport flows |
| 110–120 min | Scoped fixture cleanup/readback, evidence, rollback if required, suspend worker then API and verify both suspended |

Record transfer, validation, queue wait and processing separately per clip,
with memory, restarts, artifact identities and accuracy/speed requirements from
the selected candidate's current PRR and accepted benchmarks. Name every unmet
or unexecuted target. The historical Starter <400 MB gate must not be silently
substituted for the current 2 GB worker's accepted requirements. Do not use a
short synthetic clip as longest-clip acceptance.

On hosted failure: keep protection intact, restore recorded frontend/backend
artifacts and configuration as appropriate, suspend the selected worker/API,
leave acceptance failed, and preserve sanitized evidence. Do not reverse
additive SQL with dependent records, modify production or resume Azure workers.
Passing local checks cannot close hosted acceptance.

## Remaining public beta gates

Finish Gate 3 credential retirement/rotation and provider verification; finish
staging acceptance, production geography refresh and operational guardrails;
obtain a fresh protected recovery point; separately review/approve production
migrations; verify production bindings/private artifact and repeat required
E2E; prepare protected release, final cost/rollback packet and obtain explicit
public-launch approval. No gate is closed by this preflight.

Verification for this preparation: signed-in Netlify/Render readback, current
primary provider documentation, Supabase project/catalog/control reads and
source/worktree inspection. Focused staging guard tests pass; final local
check results are recorded below. No real credentialed build, fixture mutation,
deployment or hosted acceptance has run. The integrated source has the private
media runtime. Its activation still depends on the staging provider attestation.

Local results before merging current main:

- Focused staging/dispatch/release/build/fixture tests: **47 passed**. Export
  orchestration uses isolated synthetic fixtures and a stubbed network verifier;
  it does not prove a real staging build or hosted behavior.
- `npm run typecheck`, `npm run deps:verify`, Playwright test discovery (six
  tests) and `git diff --check`: passed. No hosted test was executed.
- Full `npm run test:policy`: **348 passed, 8 failed**. The eight failures are
  audit CLI scenarios stopped by `Audit consumer scope changed; a fresh review
  is required.` The approved frontend scope is
  `6bb00beeef8b04023e9bfe30e042bb7f414a2611f88293b10cce0f489e83a242`.
  Replacing only this change's three audited scripts with their HEAD bytes in
  memory gives `433fa17beed0aad8c168071652b57ba1710baf3434b81cbd763df03369a5ac46`,
  already mismatching the approved scope. Current scope is
  `2fdb47e820554ade4333d16b6db17644834a6251e86a87b4d310d49d55b8a09b`.
  No audit allowlist, expiry, fingerprint or security check was weakened.
  Fresh source/security review is required before a release build; the old
  temporary backport policy also expires October 12, 2026 and is not a current
  November release approval.

Provider approval packet, now executed with Nathan's separate “yes”: create only the empty **Nathan-only private**
`peso-staging-web` project under `nathann-275` on the existing Free plan, with
no repository connection/build/content upload. Verify all-deploy private access,
private logs, disabled automatic publishing/branch deploys/PR previews and
record its actual UUID. If an empty manual project cannot be created without
an initial deployment or paid change, stop and report the exact requirement.
DNS/domain/Auth/Turnstile/media changes and paid resumption remain separate
pending actions. This request is necessary because Nathan explicitly withheld
DNS/provider-write authorization in the task; the Free preference is a scope
choice, not approval of a provider mutation. The subsequent “yes” authorized
this empty-project creation only.

## Empty project creation — November 16, 2026, 7:21 PM Eastern

Created through Netlify CLI's documented `sites:create` command with exact name,
team `nathann-275` and `--disable-linking`. No repository, CI setup, content
upload or deployment was included. The dashboard creation flow offered only
Git import or file deployment, so the CLI was used to preserve the approved
empty-project boundary. The official CLI was downloaded to a temporary cache;
Netlify's authorization page reported Authorization Granted. Its credential is
kept in the local CLI configuration, never this repository or evidence.

- Project: [peso-staging-web](https://app.netlify.com/projects/peso-staging-web).
- Project ID: `c2be6c9f-89fc-4303-befc-423aabcf9bfa`.
- Default hostname: `peso-staging-web.netlify.app`.
- Dashboard: **Production visibility Private**, **Deploy Preview visibility
  Private**, Nathan Ngau as sole Owner, and **Project has not yet been deployed**.
- API readback: correct team/name/ID, `sso_login=true`,
  `sso_login_context=all`, zero deploys and no published deploy.
- Developer settings: **Current repository: Not linked**. There is no Git
  trigger for builds, branch deployments or PR previews.
- Anonymous default-host `/` and `/app` return 404 while the project is empty;
  the unauthenticated deploy-list API returns 401. These results do not prove
  protection of deployed content, deploy permalinks or future logs.

The unlinked project's `build_settings` is empty. A narrow documented update
request for stopped builds/private logs/no allowed branches returned success
but did **not** persist those settings; readback remained empty and no Git
repository was created. Do not claim those explicit switches are configured.
No deploy exists to lock against automatic publishing or to test log access.
Before any separately approved upload, configure and verify the applicable
manual-deployment/publishing/log controls; stop if doing so requires a paid
feature. Keep production and preview access Private throughout.

The tracked site binding now contains the real UUID and remains **pending**.
No DNS/custom domain, certificate, Auth/Turnstile/backend setting, paid-plan
change or compute resumption occurred. Existing projects were not modified.

## Local integration checks

The updated source passed typecheck, the 51 focused release and build checks,
127 private media tests, and 32 committed-source scanner tests. Playwright
discovered six tests. The root and marketing dependency audits passed at
their existing thresholds. The combined frontend built with synthetic
values and met the bundle budget with 547,271 gzip bytes of startup JavaScript.

The initial full policy run passed 719 of 720 tests. The historical dispatcher
fixture hit its five-second timeout during parallel checks. It passed in
isolation and the full rerun at concurrency two passed all 720 tests.

Gitleaks reported three `generic-api-key` findings in the staged changes.
They match literal Render service identifiers in the new project binding,
the release plan, and the release validator's test fixture. The Render
readback confirms the fresh service identifier and the historical ID
appears in the existing release binding. The scanner policy remains
unchanged. Review the exact occurrences in the staging commit under
the existing byte-pinned policy before release.

### Committed-source review after consolidating service references

The launch plan now links to the dedicated binding for its service IDs.
The wrong-service test reads the historical ID from the existing combined
binding and still verifies that the staging validator rejects it. All 15
focused release and staging tests passed. The scanner and its policy retain
their existing content.

Gitleaks 8.30.1 scanned 10,626,482 bytes at commit
`b6b3c4cd7b2cc7342b81802e6efadee667e548c9`. It reported six findings.
The existing policy classified five and blocked one. The findings report
SHA-256 verified as
`678456a6e87e0862e8248f410431cc0915f52d6e8fdaf68aee1b029298d8e779`.

The remaining `generic-api-key` match is in
`config/staging-web-release-binding.json`, line 9, columns 5–47. It contains
the Render API service ID. The authenticated Render connector returned
that exact ID for `peso-public-beta-staging-api-mo9c` in workspace
`tea-d9poa1h42hec73f5k580`. It also verified the separately bound worker and
the historical API.

| Evidence | SHA-256 |
| --- | --- |
| Archived binding file | `7812402ded566fcaa6dfdee0dcc84ec95f38ecf253bac9d0123f0e66a8bdfca0` |
| Matched source line | `247ff2f461b42d8eca2c173eac91fac5a8140cc5da4908fa2865947d530b8d42` |

Review this exact occurrence again once the binding has its verified provider
values. Filling in those values changes the file hash, so a decision on the
current pending binding would expire before the release build. Use the existing
exact-occurrence review and rerun the committed-source scan on the resulting
candidate. See [public identifier review](public-identifier-review-20261030.md).

## Domain change for approval

Cloudflare public DNS returned NXDOMAIN for both proposed staging hostnames
on CNAME, A, and AAAA lookups. The authoritative nameserver confirmed both
names are absent, and public DNS returned no apex CAA records.
`main.usepeso.com` still points to `main--peso-webapp.netlify.app`.
Render readback confirms both selected services are suspended, with auto-deploy
off and one instance each. The API target below matches its Render service URL.

| Provider association | Cloudflare record in `usepeso.com` | Expected target |
| --- | --- | --- |
| Add `staging.usepeso.com` as the primary custom domain on Netlify project `c2be6c9f-89fc-4303-befc-423aabcf9bfa` | `staging`, CNAME, DNS only, TTL 300 seconds | `peso-staging-web.netlify.app` |
| Add `api-staging.usepeso.com` to the suspended Render API `srv-dbrrjqjrjlhs73cbn6b0` | `api-staging`, CNAME, DNS only, TTL 300 seconds | `peso-public-beta-staging-api-mo9c.onrender.com` |

Add the provider associations first. Confirm both CNAME targets against the
provider instructions, check for conflicting records in the Cloudflare
dashboard, and recheck the Render custom-domain allowance before saving. The
expected added cost is $0 within the observed allowance. Stop for review if
either target differs, a record already exists, or a provider requires a paid
change, deployment, or compute resumption. Preserve the existing records and
the normal Netlify project-domain TLS path.

After DNS propagates, verify both provider domain statuses and inspect the
certificate chains for the exact hostnames using ordinary HTTPS verification.
An empty or suspended service can return an HTTP error after a valid TLS
handshake. Record TLS and HTTP results independently. If a provider requires
deployment or resumption to complete TLS, record that dependency for the next
approval. Rollback removes only these two new CNAMEs and their new provider
associations.

Once both certificates verify, prepare the separate Auth, Turnstile and Render
configuration change. The API settings are
`BACKEND_CORS_ORIGINS=https://staging.usepeso.com`,
`PRIVATE_MEDIA_PUBLIC_ORIGIN=https://api-staging.usepeso.com`, and
`PRIVATE_MEDIA_BROWSER_ORIGINS=https://staging.usepeso.com`. The media flags on
the API, worker and frontend stay off until the staging Auth policy attestation
and release checks pass. Verify CORS with the exact staging website and the
historical website as a negative test against the new configuration.

## Approved domain change status

Nathan approved the two provider associations, two Cloudflare records and TLS
verification. The Netlify API confirms `staging.usepeso.com` as the custom
domain of `peso-staging-web` (project `c2be6c9f-89fc-4303-befc-423aabcf9bfa`).
The readback shows all-deploy private access, zero deploys, automatic TLS
enabled, and no certificate status yet.

The Render API remained suspended with auto-deploy off at readback.
The Render connector lacks a custom-domain action, and the Cloudflare
authoritative nameserver returned NXDOMAIN for both names. This chat could
not open the dashboards and had no authenticated CLI or API access for
either remaining write. The Render association, both CNAMEs and both
certificate verifications are pending. The release binding stays pending.

### DNS and TLS verification

Nathan added the Render custom domain and the two Cloudflare records.
Cloudflare's authoritative and public resolvers return both approved CNAMEs
with a 300-second TTL. The Render endpoint passes public TLS chain and
hostname verification. It returns HTTP 503 while the service is suspended.

Netlify initially returned HTTP 422 from certificate provisioning. After
confirming DNS through both Cloudflare nameservers and Google Public DNS,
Netlify accepted the retry with HTTP 200. The first readback still showed
no installed certificate and the edge presented its default `*.netlify.app`
certificate. The site remains private and has no published deploy.

## Release and acceptance readback

On November 16 at 8:24 PM Eastern, both public CNAMEs resolved to the selected
services. Ordinary HTTPS verified for `api-staging.usepeso.com` and returned
503. The Netlify hostname failed certificate name verification. The authenticated
Netlify API subsequently returned no certificate record, `ssl=false`, all-deploy
sign-in protection, zero deploys and no published deploy. The project still has
empty build settings. Continue using the same hostname and verify both an
installed certificate and ordinary HTTPS before staging configuration changes.
At 8:45 PM Eastern, Netlify still reported no certificate and zero deploys.
Ordinary HTTPS returned the same certificate name mismatch.
[Netlify certificate troubleshooting](https://docs.netlify.com/manage/domains/troubleshooting/troubleshoot-ssl-and-https/)

### Release candidate

The current branch is 35 commits ahead of its local upstream tracking ref.
Gitleaks 8.30.1 reproduced the six findings on `b6b3c4cd7b2cc7342b81802e6efadee667e548c9`.
Five matched the existing policy and the current binding occurrence still blocks.
The repeat runs emitted the same findings in different orders. Preserve each
report and its own checksum. Review the exact binding occurrence after the real
provider fingerprints are in place. The checked-in binding remains pending.

The independent history scan with the repository's configuration exited 1 on
both the full and first-parent local upstream-to-HEAD ranges. It found three
Render ID references introduced by `b5b8d12316abe6de284d41d01dcd4f26844d9282`
in the binding, this branch's launch plan and the wrong-service test. Two are
absent from the current tree. The committed-source review applies to the final
archived tree. The history findings need their own review against the eventual
CI event range. The branch, scanner and policy are unchanged.

The manual build rejects tracked and untracked changes. Use a separate clean
checkout of the final reviewed full SHA with the existing checkout preserved.
The [Render validation workflow](../../.github/workflows/render-beta-validate.yml)
accepts `main` or `feat/combined-public-beta` for manual dispatch and checks SHA
ancestry. Agree on a validation path before publishing source. Verify the final
SHA is reachable in the linked Git repository before triggering either Render
service with an explicit commit. Feature-branch publication alone does not run
the protected-branch security checks.

#### GitHub validation and Netlify preview impact

GitHub readback found no open PR from `fix/merged-source-secret-coverage`.
Its public remote ref is `8f7094c71bc4b17774ce147e6fbe14c2825b2350`.
Remote `main` is `e9370d9f6675be3fe5567043b458ab51afae0933`, an ancestor of the
local head. The manual validation workflow's second eligible branch is absent
from the remote. The required Render CI secret and workspace variable names
exist. Their presence does not establish that their values are valid.

A same-repository PR targeting `main` would trigger Security Checks and the
path-matched Render validation job. GitHub can check out a synthetic merge
commit for the PR. Record both commits and compare their tree IDs before
crediting CI evidence to the exact deploy source. The migration-preview job
requires a separate manual dispatch under the existing approved branch and
environment restrictions. Preserve the apply approvals.
[GitHub pull request events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)

The pinned Gitleaks Action uses the first and last commits returned by the PR
commits API and a no-merges, first-parent range. The local approximation of
that range and the full `origin/main..HEAD` scan both exited 1 and produced the
same three findings. The normalized metadata checksum is
`5b5eb8f6b4f68df7859f7770a92a619b22cc16de5fcfc4cc526cadafbca302e3`.
Repeat against the finalized source and actual event range before relying on
CI. [Pinned Action implementation](https://github.com/gitleaks/gitleaks-action/blob/dcedce43c6f43de0b836d1fe38946645c9c638dc/src/gitleaks.js)

The dedicated Netlify project remains unlinked. The linked `peso-public-beta`
and `peso-webapp` projects have builds enabled, all-deploy sign-in protection
and `main` eligible as a preview base. Their last 20 deploy records included
15 and 14 previews respectively. The API did not give an explicit current
preview switch. Verify that setting on both projects before requesting PR
approval. The observed `peso-marketing` build only lists `production` as an
eligible base. Any preview setting change needs separate authorization.
[Netlify preview controls](https://docs.netlify.com/deploy/deploy-types/deploy-previews/)

#### Local Linux container evidence

Built `Dockerfile.mvp` with `--pull` for Linux/amd64 from an archive of the
exact current commit, preserving normal Git file modes. The local image ID is
`sha256:a1e9ce4b6bccb76775e03c5d9a8ca1cda8925c8f513d80181b23c18e1182903a`.
`verify_container_runtime.sh` passed offline as UID/GID 10001. Its checks
covered API and worker imports, three pose models, quality preflight, FFmpeg
formats, thumbnails and export. All five avatar normalizer tests passed.
An initial archive used overly restrictive modes and failed the import check.
The verified rebuild used normal tracked modes in a private parent directory.
Trivy 0.74.0, the version pinned by CI, scanned the local image tar with the
November 16 vulnerability database. The vulnerability report had zero HIGH
or CRITICAL package findings, including unfixed findings. Report SHA-256 is
`a7e1e2eebc0c401b1735119798f3062d7380cc230fd7de75a9b90a80c5d054c2`.
These results identify a local image. Record fresh CI and hosted evidence for
the final reviewed candidate and the actual Render artifacts.

Typecheck, 83 focused release checks, 231 fixture/Auth and related frontend
checks, and 133 targeted backend tests with 193 subtests passed. Playwright
discovered the six existing Chromium cases. The final binding and hosted
artifact still need their applicable release checks.

### Hosted acceptance and fixture cleanup

Nathan approved the first window's scope on November 16. It covers the
owner-only Netlify gate, exact candidate and service identity, API readiness,
allowed and denied CORS origins, real signup/confirmation/reset email and
Turnstile, plus the browser and layout checks. Keep media disabled on API,
worker and frontend. Timing, provider changes, fixture writes and paid compute
require separate approval.
Hosted media acceptance requires the provider settlement contract, scoped owner
cleanup and actual hosted-role rehearsal to pass first. The existing Chromium
recording case stops at upload review. See [source write acceptance](private-media-source-write-attempts.md)
and the [Web MVP runtime gates](web-mvp-runtime.md).

The first window can start after both certificates verify, the release source
and binding pass, and access, rollback, browser and fixture prerequisites have
been checked. Verify the holding page and its privacy before the compute clock
starts. In the window, verify service and artifact identity, readiness and CORS
before creating fixtures. Use the remaining time for browser and Auth checks,
then reconcile fixtures, restore the holding page on failure if approved, and
verify both Render services are suspended before the deadline. Media upload,
processing, playback, export and deletion stay open for the later media window.

Set `PLAYWRIGHT_BROWSERS_PATH` to a private cache with the versions pinned by
the release checkout. Install with `./node_modules/.bin/playwright install
chromium webkit` and smoke both engines before starting the compute clock.
Playwright 1.62.1's Chromium 151 and WebKit 26.5 were installed in a private
temporary cache. Both passed local headed launch and page checks. Chromium
needed the macOS process permissions outside the command sandbox. WebKit passed
a retry after its first launch timed out. The cache is local to this runner.
After a protected artifact is available, use a fresh private run directory.

```sh
umask 077
export PESO_E2E_RUN_DIR="$(mktemp -d /private/tmp/peso-e2e.XXXXXXXX)"
export PESO_E2E_RECEIPT_DIR="$PESO_E2E_RUN_DIR/receipts"
export PESO_E2E_STORAGE_STATE="$PESO_E2E_RUN_DIR/netlify-chromium.json"
mkdir "$PESO_E2E_RECEIPT_DIR"
./node_modules/.bin/playwright codegen --browser=chromium \
  --save-storage "$PESO_E2E_STORAGE_STATE" https://staging.usepeso.com
chmod 600 "$PESO_E2E_STORAGE_STATE"
```

Save only Nathan's interactive Netlify visitor sign-in. After separate fixture
authorization and a matching protected artifact identity, set the E2E variables
above plus `PESO_E2E_ENV=staging` and `PESO_E2E_ALLOW_ADMIN_FIXTURES=true`.
Load the runner-only credential and unique signup inputs privately. Record
each created identity in the run receipts. Keep reports and results alongside
those receipts with restricted permissions.

```sh
PLAYWRIGHT_HTML_OUTPUT_DIR="$PESO_E2E_RUN_DIR/report" \
  npm run test:web:e2e -- --headed --project=chromium \
  --output "$PESO_E2E_RUN_DIR/results"
```

Use empty browser contexts to verify anonymous denial of candidate bytes from
the custom/default host, actual deploy permalinks, app and release metadata
routes, challenge and static assets, and deploy logs. Test `/health/ready`
and independent dashboard/runtime binding readback. The readiness endpoint
checks queue schema and outbox access. Verify the real browser preflight for
`GET /videos/saved` with the `authorization` request header. Require the exact
staging website origin and credentials. Require no allowed-origin header for
the default Netlify hostname, deploy permalink, historical site and an
unrelated origin.

Repeat the required WebKit flows in a separate headed visitor context at
1280×900 with reduced motion and at the selected mobile width. Check keyboard
skip-link visibility and activation, layout, fonts, reload, navigation and Auth.
Verify real iOS Safari and native smoke separately where required by the
[PRR](../product/PRR.md). This runner has no Maestro and its Xcode 16.4 is below
the native project's documented minimum. Generated Auth links demonstrate link
handling. Observe real delivery and real CAPTCHA separately.

The Chromium suite creates up to three Auth accounts and has no teardown.
Approve cleanup for exact per-run identities, reconcile incomplete receipts,
and verify user identity before deletion. For a later approved media run,
drain receipted jobs and verify terminal attempts and scoped user-owned
deletion before removing Auth accounts. Retain ambiguous receipts for follow-up
and keep cleanup acceptance open. The account-wide deletion route is unsuitable
for this teardown. [Owner deletion](private-media-owner-deletion.md)

### Artifact custody, costs and rollback

Build once in the clean checkout. Confirm the frontend output includes
`index.html`, `peso-release.json`, `_headers` and `_redirects` at its root and
contains no symlinks. Write a sorted SHA-256 file manifest and a ZIP to a fresh
private directory outside Git. Checksum both, test the ZIP and compare the
extracted file manifest. Use the exact archive for a ZIP-based deploy to the
approved project ID. Record the published deploy ID and compare deployed file
hashes where available. Verify effective headers, redirects, and the protected
release identity. [Netlify ZIP deployment](https://docs.netlify.com/api-and-cli-guides/api-guides/get-started-with-api/)

The empty Netlify project has no frontend rollback target. On November 16,
Nathan selected an owner-only static holding page for rollback. The local
archive contains one HTML page and Netlify's `_headers` file for no-store,
no-index and a restrictive content security policy. The archive file list,
extracted bytes and checksum passed verification. Upload still requires
separate approval for the exact project and archive after TLS verification.
Before upload confirm all-deploy protection and team credits. After upload
verify Nathan's access and anonymous denial on the custom hostname, default
hostname and deploy permalink. Record the holding deploy ID as the rollback
target and confirm it stays available before the candidate upload. Netlify's
project access setting controls privacy.

The holding page consumes 15 Netlify credits. The holding page plus candidate
consume 30, or 52 with the example 1 GB and 10,000 requests. Republishing the
retained holding deploy is free. Exhaustion pauses all projects on the team.
Disabling only this project is a containment option that preserves deploy
history and settings.
[Netlify credits](https://docs.netlify.com/manage/accounts-and-billing/billing/billing-for-credit-based-plans/how-credits-work/) ·
[Disable a project](https://docs.netlify.com/manage/projects/disable-project/)

The selected Render services are both suspended, linked to `main` and set to
auto-deploy off. Both latest retained deploys were triggered by resume. Before
any resume, check the linked ref, effective environment and staging queue,
and account for any interim deploy. Record service/deploy IDs, observed SHA,
model versions and image evidence per service. The inspected Git deploy
records and build logs did not expose final image digests. A base image digest
does not identify the deployed image. If matching image bytes are required,
obtain an approved digest-pinned deployment path before opening the window.
Confirm previous artifacts are selectable and compatible. Render rollback
reuses the target deploy's service-specific environment values for that deploy.
Saved service settings and environment-group values persist. Capture the
approved configuration diff and restore its applicable values independently.
[Render exact-commit deploy](https://render.com/docs/deploys#deploying-a-specific-commit) ·
[Render rollback](https://render.com/docs/rollbacks)

The two-hour compute estimate remains $0.089 before other metered usage and
tax. Reserve time for containment and shutdown earlier than the last ten
minutes. Render readiness alone can take up to 15 minutes, and the worker
has a five-minute shutdown delay configured. On failure stop new fixture intake,
contain the frontend, retain incomplete cleanup receipts, and verify suspension
of the worker and then the API by the approved deadline. Restore only approved
compatible artifacts and settings within the available time.
[Render pricing](https://render.com/pricing) · [Render health checks](https://render.com/docs/health-checks)


## Execution checkpoint — November 17, 2026

Netlify Support ticket #1196713 established that an initial production deploy
was required for certificate provisioning. Nathan separately approved the support
request, routing confirmation, and exact holding ZIP upload before TLS with a
free certificate retry. Holding deploy 6afbc190c9a060d455a54082 is published and
ready. The approved original ZIP SHA-256 was
0f26fff44e9c590949d57c8aec53318f44c44e1226f8a98fadfd62200903b6b5.
The custom certificate was issued November 16 at 10:03 PM Eastern and expires
February 14, 2027 at 9:04 PM Eastern.

On November 17, ordinary hostname and chain validation passed on the custom,
default and exact deploy hostnames. Eighteen anonymous HTTPS requests returned
401 across root, index, headers, app, challenge and release-metadata URLs.
Readback retains all-deploy sign-in protection, empty build settings and the
exact holding deploy. Nathan confirmed the holding text in his signed-in browser.

The prior temporary checkout and evidence were absent on continuation. The
dedicated changes were reconstructed on post-#52 main
99ab4cef70cf483938f193f096e916649ba2e031 and exactly matched preparation tree
aa738fb285584c7d183c00b23866a0b0c52a95e3 before subsequent edits.
The former temporary commit was never published and is not a release candidate.
Current receipts and clean checkout are under ignored
artifacts/owner-only-staging-20261117/, with a redacted handoff copied to
$TMPDIR/peso-staging-handoff.md. The original temporary ZIP is absent; do not
attribute its checksum to a recreated archive. The published rollback remains.

All 723 policy tests and typecheck passed on the reconstructed tree. The current
staging public key was again accepted by the isolated Auth endpoint, with SHA-256
25fe02e09661d7d1b8e91bf94cccf820abb376c6750bb8539b4681db2496016e.
The preparation binding records that hash but stays pending. All 52 local and
hosted migration versions match; the CLI dry run and source-bound CI remain
required. Current public Auth settings still disable signup and require email
confirmation.

The next approval packet specifies exact Auth URL/redirect additions, staging
Turnstile hostname replacement and save-only Render CORS/origin settings.
It preserves suspension, media-off flags, native callbacks, historical redirect
entries, CAPTCHA and email confirmation. Signup enablement, fixtures, source
publication, candidate upload and the two-hour window are separately gated.
No Render service was resumed and no fixtures were written in this chat.


### Approved save-only configuration applied

Nathan approved the exact provider packet on November 17. Supabase's saved Site
URL is now https://staging.usepeso.com/app. Its redirect list contains both exact
staging /app/login and /app/reset URLs, plus the four retained historical/native
callbacks. Signup remains disabled and confirmation remains required.

The peso-student-main Turnstile widget now permits only staging.usepeso.com,
retaining Managed mode and pre-clearance off. A private comparison confirmed its
existing secret matches staging Auth's configured CAPTCHA secret. No secret was
changed, printed in the receipts or retained; the fields were masked afterward.

The selected Render API and worker now save exactly https://staging.usepeso.com
for BACKEND_CORS_ORIGINS. The API additionally saves the staging API origin for
PRIVATE_MEDIA_PUBLIC_ORIGIN and the exact staging website for
PRIVATE_MEDIA_BROWSER_ORIGINS. Both services remain suspended with auto-deploy
off and PRIVATE_MEDIA_ENABLED=false. These are saved values; runtime CORS and
readiness must be tested after the separately approved deployment.

The clean candidate binding is private-config-verified, with verified public-key
and Turnstile site-key fingerprints and both media fields false. Configuration
attestation is not hosted acceptance. The final source and history scanner
review, source-bound CI, migration dry run and immutable artifact remain open.
See staging-public-identifier-review-20261117.md for the exact new occurrence.


### Local scanner review approved

Finalizing the real widget fingerprint produced a second binding finding at
line 12 in addition to the Render ID at line 9. Nathan separately approved the
exact byte-pinned public-key-fingerprint classification, file-and-line pin
selection and the two actual introducing-commit history fingerprints. No
prefix, file or rule allowlist was added. All 39 scanner controls passed.
Independent Standards review found an overstated pending-authority label;
that was corrected and rechecked. Spec review found no actionable issue.
The final local source and history scans must be retained separately from the
earlier prototype evidence. Source publication and hosted CI remain gated.

Netlify's current Free credit balance is 193.2 after the 15-credit holding
upload. The later candidate upload is another 15 credits, retaining the
30-credit two-upload estimate before usage. Render currently lists the selected
API plan at $7/month and worker plan at $25/month, one instance each; the
November two-hour compute estimate remains about $0.089 before other usage
and tax. Both are suspended. Existing peso-public-beta and peso-webapp projects
have private logs and PR previews enabled for main as an eligible base. A
source PR may trigger those existing previews; do not change their settings
without separate approval. The dedicated staging project remains unlinked.
