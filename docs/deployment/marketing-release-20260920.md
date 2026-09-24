# Public marketing release evidence — 2026-09-20

## Decision

**Private production published; DNS cutover and public exposure remain gated.**
See the September 21 continuation below for current state; earlier sections are historical evidence.
Existing local marketing work is preserved. On September 21 at 02:10 UTC,
Render live auto-deploy was changed to Off and verified through its API
(`autoDeploy=no`, `autoDeployTrigger=off`). The retained live deploy is still
`dep-daaed1qjnfac738a8cig`, commit `6a9a07180cd3306df4d92c3cf7d8849d3d890288`.
No backend deployment, migration, credential change, or service resumption occurred.

The team default is verified Private for new projects; team ID
`6a7264bb5030ed5c1b4a1fa3`, slug `nathann-275`, plan Free. GitHub authentication
works with network access; the earlier invalid-token observation was caused
by restricted network access. Production ruleset `22210122` is active with
no bypass actors. Marketing project creation and exact preview checks are complete. Hosted acceptance,
DNS/TLS cutover, and action-time public confirmation remain pending.
This does not approve the public beta; all full-beta blockers in the
[PRR](../product/PRR.md) and [beta evidence](public-beta-release-20260920.md)
remain open.

## Implemented

- `web:build:marketing` cleans `dist`, builds Astro, removes authentication
  output, emits forced 302 redirects, and validates the final artifact.
  Failure removes partial output. The final artifact contains exactly `/`,
  `/beta`, `/privacy`, and `/terms` plus marketing assets.
- Signup, sign-in, and prototype links now lead to “Beta coming soon.” No
  forms or email collection were added. Legal pages distinguish the current
  informational site from the future beta draft; draft legal approval remains
  a separate beta requirement.
- Generated `_redirects` sends `/app`, `/app/*`, `/auth`, and `/auth/*` to
  `/beta` using `302!`. This takes precedence over the retained private-beta
  rewrite in TOML. The local preview server applies these generated redirects.
- Netlify's dispatcher requires app project ID `230da8eb-f00e-45d4-ba54-95f2e26f21c4` and selects the private-beta release build only for the
  stable `branch-deploy` of `main`. Production, release PR previews from
  `main`, other previews, and unknown contexts default to marketing.
- `web:build:private-beta` retains the combined Astro/Expo build;
  `web:build:release` retains its environment validation. Switching builds
  clears stale output, including marketing redirects.
- CI's new `marketing-build` job checks a clean marketing build, performs an
  actual Expo export, and checks another marketing build without app credentials.

## Local verification

| Check | Result |
| --- | --- |
| Clean marketing build | Pass; four pages, no retained app/auth output or detected backend call code |
| Actual Expo export followed by marketing build | Pass; exported app bundles removed |
| Repository policy suite | 210 passed before dispatcher addition; its additional context-selection test passed separately (211 tests total) |
| App typecheck | Pass |
| Whitespace/diff check | Pass |
| Desktop and mobile browser review | Home reviewed at desktop and 390px mobile; beta notice and privacy page reviewed on mobile; no home horizontal overflow |
| Navigation and refresh | Beta CTA, legal links, terms refresh, and redirected beta refresh passed locally |
| Local HTTP smoke | Four public pages returned 200; nine app/auth paths (including stale JS asset paths) returned 302 with Location `/beta` |
| Security header configuration | Existing policy tests pass; no change to deployed header configuration |
| Private Netlify release preview | Not created; live redirects, header responses, injected snippets, and runtime request inspection still require hosted acceptance |

Local output is not evidence of Netlify's access-control isolation. The
loopback preview does not emulate Netlify authentication or security headers.

## Historical observations before separate-project implementation

Netlify UI observed on September 20, 2026 (EDT):

- Project `peso-webapp`, ID `230da8eb-f00e-45d4-ba54-95f2e26f21c4`.
- Production visibility **Private**; Deploy Preview visibility **Private**.
- Currently published deploy `6a9234045e436787ff1076ed`, published August 28,
  production commit `6a9a07180cd3306df4d92c3cf7d8849d3d890288`.
- Existing production permalink:
  `https://6a9234045e436787ff1076ed--peso-webapp.netlify.app/`.
  This is an old app-containing release, not a marketing rollback candidate.
- [Netlify visibility documentation](https://docs.netlify.com/manage/security/secure-access-to-sites/project-visibility/)
  separates previews from production but states public visibility exposes
  production deploys. No verified protection for old app-containing production
  permalinks was established. **Stop: do not make production public.**

Render monitoring plugin read-only results:

- `Peso-backend`, service `srv-d9poevht0dsc73d07d3g`, tracks `production`.
- `autoDeploy=yes`, `autoDeployTrigger=commit`; a production merge is not
  isolated from backend deployment. **Stop before the release merge.**
- Retained live deploy `dep-daaed1qjnfac738a8cig`, commit
  `6a9a07180cd3306df4d92c3cf7d8849d3d890288`; native Python Free service,
  root directory `backend`. No backend mutation was performed.
- Azure backend deployment is workflow-dispatch-only in repository configuration.
- GitHub CLI authentication is invalid. No PR/check/protection changes were
  attempted; the existing beta evidence records missing required checks.

## Netlify baseline

Read from Usage & billing on September 20, 2026 around 22:00 EDT. This is a
preparation baseline, not a launch measurement; refresh immediately before
an eventual release.

| Measurement | Observed value |
| --- | --- |
| Plan | Free, 300 credits per month |
| Billing cycle | September 4–October 3, 2026 |
| Production deploy usage | 0 credits; no usage |
| Web requests | 11,734 requests; 2.3 credits |
| Bandwidth | 0.3 credits |
| Compute | 0 credits |
| AI inference | 0 credits |
| Total consumed | 2.6 credits |
| Remaining | 297.4 credits |

## Separate-project release gates

1. Create `peso-marketing` privately; configure package `web`, base root,
   `web/netlify.toml`, production branch `production`, no branch deploys, and
   private Deploy Previews. Every deploy must contain only marketing assets.
2. Keep app project `230da8eb-f00e-45d4-ba54-95f2e26f21c4` private, including all
   historic URLs. Skip its production builds while preserving branch/previews.
3. Require existing checks plus container-security, reservation-database-security,
   marketing-build, and the exact marketing Netlify preview check on one protected
   `main` → `production` PR. Merge only after every check passes.
4. Complete hosted desktop/mobile, navigation, legal, refresh, redirects, headers,
   and network inspection. Inventory old app deploy URLs and deny anonymous access.
5. Publish marketing production privately; capture deploy identity and usage.
6. Record DNS/domain assignments, move apex and www, retain apex primary and
   www redirect, preserve unrelated records, and verify both TLS certificates.
   If setup fails, remain private and restore the previous assignments.
7. Obtain Nathan's action-time confirmation immediately before making marketing
   production public. Verify all four pages, redirects, preview privacy, historic
   app privacy, and unchanged backend identity. Restore Private on any failure.

## Current local verification

- Clean marketing build and real Expo export followed by marketing build: pass.
- Dispatcher matrix: exact app project + main branch-deploy only; all other
  projects/contexts select marketing, including a main-sourced preview.
- App production ignore path: pass without commit metadata; preview/branch builds
  remain buildable.
- Repository policy suite: 213 passed; added dedicated marketing config test passed.
- Production Blueprint API and worker both set `autoDeployTrigger: off`.
- ADR 0017 records separate hosting; all full-beta blockers remain open.

## Hosting and protection implementation — September 21, 02:24 UTC

- Created `peso-marketing`, project ID `19cbad85-dd2d-4d3b-a24a-242de78d30af`.
  Production and Deploy Preview visibility verified Private; deploy logs private.
  Repository NathanN-275/Peso, production branch `production`, package `web`,
  base `/`, output `dist`, branch deploys None, PR previews enabled.
- Creation produced an initial private marketing deploy from `main` at
  `8c2b3e91258691d97c9c220899135f23f04c82f5`, deploy `6ab092fd426764843e174cb0`,
  before production branch configuration was saved. It used the project-ID-gated
  marketing dispatcher. This is a bootstrap deploy, not the accepted release.
- Protected release PR: https://github.com/NathanN-275/Peso/pull/46.
  Active ruleset `22210122` retains every existing requirement and no bypasses;
  added container-security, reservation-database-security, marketing-build,
  and the observed exact `netlify/peso-marketing/deploy-preview` check.
- Private marketing preview `6ab09376bd8bb800090f3fb6` passed the exact Netlify
  check, with four pages, five redirects, three header rules, 26 total files
  and 1.8 MB. Hosted inspection remains in progress.
- Anonymous HEAD requests to the marketing preview and historical app permalink
  `6a9234045e436787ff1076ed--peso-webapp.netlify.app` both returned HTTP 401.
- GitGuardian incident `37243448` flagged literal `?Set` within the Bash
  required-variable guard on line 5 of `scripts/configure_azure_scaler_role.sh`
  in historical commit `99548d6`. Source and dashboard occurrence confirm this
  is diagnostic text, not a password. Classified the exact incident as
  “Not a secret (false positive)”; scanning remains enabled. No credentials
  changed and no history rewrite or broad exclusion was used. A new commit
  requests fresh PR scanning because the check rerequest API returned 404.
- Local TypeScript check passed. Existing main workflow published a candidate
  container image only; no backend runtime deployment was requested.
- No domains moved and no public visibility enabled. Full-beta blockers remain open.

GitGuardian's fresh check on `7355f84` passed after exact false-positive triage.
Hosted QA then found that Astro's inline demo loader conflicts with `script-src
'self'`. The loader is now an external fingerprinted asset; CSP remains strict,
and the marketing verifier rejects executable inline scripts. Policy suite and
marketing build were rerun before pushing this correction.


## Hosted acceptance update — September 21

- Release head `a024a9f02b933aa282f21c92dee61b7c08c45157`: all required
  checks passed; GitGuardian passed. PR 46 remains open, unmerged, with clean
  merge state and no protection bypass. Preview deploy is
  `6ab096ecf37b7f000812b2ea` (27 files, 1.8 MB).
- Desktop navigation, four pages, legal-page refresh, and external demo-video
  playback passed. Browser navigation of `/app`, `/app/`, `/app/signup`,
  `/app/_expo/static/js/web/old-bundle.js`, `/auth`, `/auth/`,
  `/auth/turnstile/`, and `/auth/old.js` reached `/beta/`.
  Netlify processed five redirect rules and three header rules successfully.
  Authenticated raw response headers/status and a full network capture remain
  pending; browser navigation alone does not establish the 302 status.
- Observed page assets were marketing assets plus Netlify-injected private-site
  tools. No signup, upload, analysis or email forms were present. Repository
  artifact checks passed; this is not a substitute for a complete hosted
  network inspection.
- Nathan supplied a phone screenshot and is checking mobile navigation/legal
  pages. Automated hosted viewport override did not take effect (actual viewport
  remained 1280px), so hosted mobile acceptance is not yet recorded as passed.
- With Nathan's explicit approval, disabled only the marketing Netlify Drawer.
  Settings readback shows Drawer Disabled and heads-up display Disabled. A fresh
  preview has no collaboration iframe; Netlify's private-site `nl-hud-frame`
  remains. The white browser toolbar area in the phone screenshot is not proven
  to have the same cause as the removed collaboration iframe.
- Marketing environment-variable UI explicitly states no variables are set.
  Form detection is disabled. No backend variables or authentication origins
  were changed.
- App production and Deploy Preview visibility were rechecked as Private.
  Anonymous URL inventory is in `evidence/app-deploy-privacy-20260921.json`:
  40 responses were 401, 12 were 404, and three were 500. Netlify UI identifies
  the three 500 URLs as canceled/failed builds with deployment skipped:
  `6ab095daf5ba6800088c7297` canceled;
  `6ab095d8e56cba00081134fa` and `6ab092eb1b0a150008b1b6b3` failed.
  No app content was returned; 500 itself is not evidence of authentication.
- Render was rechecked: live deploy `dep-daaed1qjnfac738a8cig`, commit
  `6a9a07180cd3306df4d92c3cf7d8849d3d890288`, Auto-Deploy selector text `Off`.
  No backend deployment or service resumption was performed.
- DNS snapshot is in `evidence/dns-before-20260921.txt`. Apex is assigned to
  peso-webapp with www redirect; www CNAME points to peso-webapp.netlify.app.
  Cloudflare nameservers, MX routing and SPF records must be preserved. Full
  DNS-zone inventory and domain/TLS cutover remain pending.
- Usage after private bootstrap, September 20 around 22:33 EDT: Free plan,
  17.7/300 credits consumed, 282.3 remaining; production deploy 15 credits,
  11,809 requests (2.4 credits), bandwidth 0.3, compute/AI zero. Refresh before
  launch. No paid upgrade was purchased.
- Marketing stays Private. Domain moves and public exposure have not occurred.
  All full-beta blockers remain open.


## Private production continuation — September 21, 2026, approximately 18:20 UTC

Nathan confirmed mobile acceptance and instructed continuation after PR 46 merged.
The working tree was clean at entry (`main`, `3c65cfb`). Existing implementation
and successful prior tests were retained; no repeat deploy was triggered.

### Release identity and usage

- GitHub confirms PR 46 merged at `2026-09-21T18:15:01Z`, merge commit
  `d92dfea5334d338cf7af842f0d1b3672ca3d1cc9`; remote production points there.
- Marketing project `19cbad85-dd2d-4d3b-a24a-242de78d30af` automatically published
  deploy `6ab17428436e50000838783f` privately from that commit. Build ran
  14:15:07–14:15:26 EDT; 27 files, 1.8 MB, four generated pages, five redirect
  rules and three header rules processed without errors.
- Netlify UI confirms production Private, Deploy Previews Private, logs private,
  package `web`, root base, `dist`, marketing-only build/verifier, production
  branch `production`, no branch deploys, PR previews enabled.
- Usage snapshot: Free plan, September 4–October 3 cycle; two production deploys
  / 30 credits, 12,445 requests / 2.5 credits, bandwidth 0.4 credits, compute and
  AI zero; total 32.9/300 credits, 267.1 remaining. No upgrade or extra build.

### Verification completed and remaining

- Authenticated production browser verified `/`, `/beta/`, `/privacy/`, `/terms/`;
  navigation through privacy, terms and beta passed, terms and beta refresh passed.
  Every page had zero form/input controls. Observed assets were same-origin
  marketing assets and Netlify private-owner HUD; no backend assets observed.
  Asset inventory is not a full network capture and does not prove absence of
  runtime backend requests. Full authenticated network capture remains pending.
- Browser navigations `/app`, `/app/`, `/app/signup`,
  `/app/_expo/static/js/web/old-bundle.js`, `/auth`, `/auth/`,
  `/auth/turnstile/`, `/auth/old.js` all reached `/beta/`.
  Authenticated raw 302 responses and actual security-header responses remain
  pending; source configuration and processed Netlify rules are supporting
  evidence, not a substitute for those response checks.
- Deploy file browser contains only beta/privacy/terms page directories,
  marketing-assets/demo directories and root marketing/configuration files.
  Four intended HTML pages; no app/auth directory. Mobile acceptance is recorded
  from Nathan's instruction, not a new automated viewport test.
- App project `230da8eb-f00e-45d4-ba54-95f2e26f21c4` production and previews remain
  Private. Main branch deploys and PR previews remain enabled; builds Active.
  Merge-triggered production deploy `6ab1742831f2590008630728` is canceled;
  repository ignore command unconditionally skips this app production context.
  Published app deploy remains `6a9234045e436787ff1076ed`.
- Fresh anonymous HEAD inventory is in
  `evidence/private-production-probes-20260921.json`: 45 HTTP 401, 12 HTTP 404,
  three HTTP 500 and one HTTP 301 across 61 probes. Historical app results are
  unchanged (40/12/3); the three failed/canceled artifacts remain non-serving,
  and HTTP 500 is not authentication evidence. Marketing production, its exact
  permalink, PR 46 alias and recorded preview permalink all return 401.
- Render dashboard verifies service `srv-d9poevht0dsc73d07d3g`, live deploy
  `dep-daaed1qjnfac738a8cig`, commit
  `6a9a07180cd3306df4d92c3cf7d8849d3d890288`, branch production, Auto-Deploy Off.
  No backend runtime request or deployment, migration, credential change,
  authentication-origin change, service resumption or protection bypass occurred.

### DNS, TLS, and rollback checkpoint

- `evidence/dns-pre-cutover-20260921.txt` records fresh public DNS: apex A
  `75.2.60.5` and `99.83.231.61`; www CNAME `peso-webapp.netlify.app`;
  Cloudflare MX, SPF and nameservers unchanged from prior evidence.
- Netlify still assigns apex primary and www automatic redirect to peso-webapp.
  Its Let's Encrypt certificate covers both domains, auto-renews before
  November 26, and normal certificate-validating curl requests succeed:
  apex returns 401, www returns 301 to apex. This is pre-cutover TLS evidence.
- Cloudflare is signed out. Nathan was asked to complete sign-in because its
  Continue action explicitly accepts subscription terms. Full DNS-zone inventory
  is unavailable until sign-in; public DNS queries cannot inventory all records.
- No domain/DNS assignment was changed. Rollback is not invoked; the previous
  assignment remains intact. Do not move domains until the full zone baseline
  and remaining private acceptance checks are available. Preserve unrelated
  records; if cutover fails, retain Private and restore the above assignment.
- Public action-time confirmation has NOT been requested or granted. It is not
  yet the final gate: private raw headers/network checks, Cloudflare inventory,
  domain move and post-cutover TLS must finish first. Then ask Nathan immediately
  before making only marketing production public, keeping previews and app private.
  All full-beta blockers remain open.


## Cloudflare zone inventory continuation — September 21

- Signed-in Cloudflare DNS UI now accessible; zone ID
  `19ca8408385bfaa58c66b3beb9de4582`. Captured all 12 records (UI confirms
  1–12 of 12) in `evidence/cloudflare-zone-pre-cutover-20260921.json`.
- Apex is actually a DNS-only CNAME to `apex-loadbalancer.netlify.com` with
  Auto TTL; prior public A answers are flattened results, not two configured
  A records. Preserve this CNAME during cutover unless Netlify explicitly
  requires another target. WWW is DNS-only CNAME `peso-webapp.netlify.app`,
  Auto TTL. All ten unrelated MX/TXT records must remain byte-for-byte intact.
- No DNS, domain, visibility, backend, credential or authentication changes.
  Marketing production/previews were rechecked Private before this inventory.
- Supported browser inspection lacks authenticated raw response/network export.
  Nathan selected guided DevTools capture as fallback and was given steps to
  export a sanitized HAR excluding cookies and authorization headers. Capture
  remains pending; do not substitute asset inventory for this required gate.
- Cutover and public confirmation remain pending; rollback not invoked because
  assignments remain unchanged. Every full-beta blocker remains open.
