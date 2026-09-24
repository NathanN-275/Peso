# Netlify releases and usage controls

Peso uses Netlify's credit-based Free plan during the commercial beta. Production
deploys cost 15 credits each, while Deploy Previews and branch deploys do not
consume production-deploy credits. Bandwidth and web requests still consume
credits in every deploy context.

## Public marketing release (current launch)

The public marketing launch is information-only and does not clear public-beta
blockers. `npm run web:build:marketing` cleans `dist`, builds Astro, removes
all authentication output, generates forced temporary app/auth redirects, and
verifies the final artifact. It needs no app/backend credentials. The dedicated `peso-marketing` project uses `web/netlify.toml` in every context.
Set its package directory to `web` in Netlify UI, base to repository root,
publish directory to `dist`, production branch to `production`, branch deploys
to none, and Deploy Previews to enabled/private. Do not copy app environment
variables, auth configuration, functions, forms, snippets, or app rewrites.
The separate configuration preserves marketing cache/security headers and
blocks browser connections and form submissions with CSP.

The shared dispatcher selects `web:build:release` only for app project
`230da8eb-f00e-45d4-ba54-95f2e26f21c4`, `CONTEXT=branch-deploy`, and `BRANCH=main`.
All other selections fail closed to marketing, including previews from `main`.
The app project's ignore command skips production builds for this release;
private branch/preview builds retain change filtering. Generated `_redirects`
force temporary 302 redirects from `/app`, `/app/*`, `/auth`, and `/auth/*` to
`/beta`, including historical bundle paths.

Follow the [marketing checklist](../product/PRR.md#public-marketing-launch-checklist)
and [dated evidence](marketing-release-20260920.md). Before pushing or merging,
verify live backend deployment triggers: the historical `main` → `production`
diff includes backend changes, so file filtering alone is not proof of safety.
Disable the live production backend auto-deploy trigger and verify it before a
release merge; retain the recorded live backend version. Editing a Blueprint
alone does not change an existing service's live settings.

Keep both projects private during preparation. Keep the app project private permanently for this launch.
A private-preview setting does not prove old production permalinks remain
protected when production is made public. Inventory and verify every old
app-containing deploy URL. If isolation cannot be established, stop the release.
Do not change visibility to experiment with protection. Obtain action-time
confirmation only after all gates pass and the marketing deploy is published
privately. On isolation failure, restore Private immediately; while public,
rollback is allowed only to a verified marketing-only artifact.

Capture the new deploy ID, commit, URL, timestamp, backend identity, billing
cycle, and production/bandwidth/request/compute/total credits. The historical
baseline below is not a current launch baseline.

## Private/public beta configuration (future launch)

The following app-specific configuration and acceptance applies to the beta,
not the information-only marketing launch.

### One-time configuration

Before changing any branch setting, record the live state in the baseline table
below and locate the Git commit attached to the currently published deploy.

1. Create the remote `production` branch at the currently published commit.
2. In **Netlify > Project configuration > Build & deploy > Continuous deployment
   > Branches and deploy contexts**, set `production` as the production branch.
3. Enable an individual branch deploy for `main` and leave Deploy Previews enabled.
4. In GitHub, protect `production`: require a pull request and required checks,
   and block direct pushes, force pushes, and branch deletion.
5. Require the existing security checks, the `production-release-source` check,
   and the Netlify Deploy Preview check before a production merge.
6. Keep `EXPO_PUBLIC_PRODUCTION_BACKEND_URL` on the currently approved hosted
   backend in Production. Only the private `main` branch may use the exact
   accepted Render beta URL; it is not a production cutover.
7. Configure these public build variables in every applicable deploy context:
   `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY`,
   `EXPO_PUBLIC_TURNSTILE_SITE_KEY`, `EXPO_PUBLIC_AUTH_CHALLENGE_URL`, and
   `EXPO_PUBLIC_PRODUCTION_BACKEND_URL`. The challenge URL must be the exact
   HTTPS `/auth/turnstile/` page on that deploy's stable origin.
8. Set `PESO_RELEASE_ENV=render-beta` on the stable `main` branch deploy and
   `PESO_RELEASE_ENV=production` in Production. Production builds reject
   Cloudflare test site keys.
9. At beta launch, disable site-wide password protection under **Project
   configuration > Access & security > Visitor access**. Netlify Basic Auth
   disables CDN caching for the whole site; use application authentication for
   `/app` instead.

If the current published commit is not an ancestor of `main`, review the first
`main` to `production` release carefully because it reconciles the live and
integration histories.

## Public beta release workflow (future launch)

Normal feature and fix pull requests target `main`. Netlify provides a Deploy
Preview for review and maintains a stable branch-deploy version of `main`, but
the primary domain does not change.

When `main` is ready to publish:

1. Open one release pull request from `main` to `production`.
2. Review the change summary and verify `/`, `/app/signup`, and one additional
   `/app/*` deep link on the release Deploy Preview.
3. Confirm the production-source, security, and Netlify checks pass.
4. Merge the release pull request once. This is the single 15-credit production
   deploy for the release.

Batch non-urgent changes and target no more than five production deploys per
month. An urgent security, authentication, or availability fix can be released
immediately through the same pull-request path.

For a faulty beta release after beta approval, use **Netlify > Deploys > Publish deploy** to restore the
last known-good production deploy. A rollback republishes an existing deploy and
does not consume production-deploy credits. Follow with a corrective change on
`main` so the next release does not reintroduce the fault.

## Build filtering

After its unconditional app-production skip, `scripts/netlify-ignore-build.js` stops a build when every changed path is
in a known non-web area: backend, dashboard, docs, Supabase migrations, GitHub
workflow metadata, or root Markdown documentation. Any web, shared application,
asset, dependency, configuration, mixed, empty, or unresolved change continues
the build. This fail-open behavior prevents an optimization from suppressing a
required site update.

## CDN and startup budgets

Netlify serves static deploy assets from its global CDN. HTML uses
`Cache-Control: public, max-age=0, must-revalidate`; fingerprinted Expo assets
and WOFF2 startup fonts use a one-year immutable browser lifetime. Hosted APIs
return `Cache-Control: no-store` for authenticated and health responses.

The Netlify build runs the configuration validator before exporting. Render
beta builds additionally require the public API URL to match the reviewed
`config/render-beta-release-binding.json` generated from accepted Render
deployment evidence; the tracked pending state blocks a premature build. Run the same
production export and budget gate before a preview:

```bash
npm run web:build:release
npm run web:budget
```

The directly referenced startup scripts must remain below 600 KB after gzip,
and WOFF2 fonts below 200 KB. Lazy native-preview and review chunks are excluded
from startup only when `dist/app/index.html` does not reference them directly.

After deploying without site-wide password protection, verify `/app/`, one
`/app/_expo/static/*` asset, and one `/app/fonts/*` asset. HTML must revalidate;
fingerprinted assets and fonts must be immutable; repeated static requests
should report a Netlify cache hit. Never cache authenticated backend responses,
including the isolated Render beta API.

## Usage baseline and monitoring

For the marketing launch, remain on the existing Free plan. The future-beta
upgrade guidance below is not authorization to purchase an upgrade.

Capture **Usage & billing** values immediately before the optimized release.

| Measurement | Baseline |
| --- | --- |
| Captured at | August 5, 2026 at 02:16 EDT |
| Billing-cycle dates | August 4 through September 3, 2026 |
| Published commit | `83b9a4afc07951332c00e2b2c3ce775d38c527d1` |
| Production deploy credits | 150 credits (10 deploys) |
| Bandwidth credits | 1.1 credits |
| Web request credits | Less than 1 credit (217 requests) |
| Compute credits | 0 credits |
| Total credits | 151.1 of 300 credits used (148.9 remaining) |

Use the first complete billing cycle after the optimized release as the decision
window. Record totals on days 7, 14, and 21 and at cycle end. Project monthly
usage as `credits used / elapsed cycle days * total cycle days`.

- Projected total at or below 225 credits: remain on Netlify Free.
- Projected total from 226 through 750 credits: upgrade to Netlify Personal
  before the Free plan reaches its 300-credit pause point.
- Projected total above 750 credits in two consecutive weekly readings: prepare
  and complete a Vercel Pro migration before approaching the Personal limit.

If a Free-plan pause occurs before a scheduled reading, upgrade to Personal
immediately and continue measuring. Do not use Vercel Hobby for the commercial
beta.

## Conditional Vercel Pro migration

Do not add Vercel configuration before the threshold is met. If it is met:

1. Preserve `production` as the live branch and translate the current build
   command, `dist` output, `/app/*` rewrite, redirect, and cache/security headers
   into `vercel.json`.
2. Copy production and preview environment variables into matching Vercel
   contexts. Use the Standard build machine, disable on-demand concurrency, and
   set a $5 additional-usage hard limit.
3. Validate the marketing page, authentication entry points, app deep links,
   media byte-range responses, and response headers on a Vercel preview.
4. Lower DNS TTL before cutover. Keep Netlify available as rollback for 72
   hours, then stop its builds. Disable the Netlify project after seven stable
   days without deleting it.

## Permanent beta branch isolation

Only `main--peso-webapp.netlify.app` uses the isolated Render beta and the
permanent `peso-staging` Supabase project (`iseqgaewjpjcxrndibep`). Follow the
[Render beta runbook](render-analysis-beta.md) for the branch-specific public
key, API binding, and challenge values. Never copy credentials from production
PesoDatabase (`jfgiydtrskpqxyorvvbc`). The production branch's Netlify values
and hosting remain unchanged. Do not activate the test website until the image
security scan, migration preview, and Render beta runtime acceptance pass.


## September 21 private publication checkpoint

PR 46 automatically published marketing deploy `6ab17428436e50000838783f` at
`d92dfea5334d338cf7af842f0d1b3672ca3d1cc9` privately. Do not trigger a duplicate
production build. Current usage is 32.9/300 credits; remaining 267.1. Domains
still belong to the private app project. Finish authenticated response/network
checks, Cloudflare zone inventory and private domain/TLS cutover before requesting
public confirmation. The [dated evidence](marketing-release-20260920.md) records
project IDs, backend identity, probe results and the unchanged rollback baseline.
