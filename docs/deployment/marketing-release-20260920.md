# Public marketing release evidence — 2026-09-20

## Decision

**Separate-project implementation in progress; publication remains gated.**
Existing local marketing work is preserved. On September 21 at 02:10 UTC,
Render live auto-deploy was changed to Off and verified through its API
(`autoDeploy=no`, `autoDeployTrigger=off`). The retained live deploy is still
`dep-daaed1qjnfac738a8cig`, commit `6a9a07180cd3306df4d92c3cf7d8849d3d890288`.
No backend deployment, migration, credential change, or service resumption occurred.

The team default is verified Private for new projects; team ID
`6a7264bb5030ed5c1b4a1fa3`, slug `nathann-275`, plan Free. GitHub authentication
works with network access; the earlier invalid-token observation was caused
by restricted network access. Production ruleset `22210122` is active with
no bypass actors. Marketing project creation, hosted acceptance, exact preview
check, DNS/TLS cutover, and action-time public confirmation remain pending.
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
