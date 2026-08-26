# Netlify releases and usage controls

Peso uses Netlify's credit-based Free plan during the commercial beta. Production
deploys cost 15 credits each, while Deploy Previews and branch deploys do not
consume production-deploy credits. Bandwidth and web requests still consume
credits in every deploy context.

## One-time configuration

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
6. Set `EXPO_PUBLIC_PRODUCTION_BACKEND_URL` to the production Render API URL in
   both Preview and Production deploy contexts.
7. Configure these public build variables in every applicable deploy context:
   `EXPO_PUBLIC_SUPABASE_URL`, `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY`,
   `EXPO_PUBLIC_TURNSTILE_SITE_KEY`, `EXPO_PUBLIC_AUTH_CHALLENGE_URL`, and
   `EXPO_PUBLIC_PRODUCTION_BACKEND_URL`. The challenge URL must be the exact
   HTTPS `/auth/turnstile/` page on that deploy's stable origin.
8. Set `PESO_RELEASE_ENV=staging` on the stable staging branch deploy and
   `PESO_RELEASE_ENV=production` in Production. Production builds reject
   Cloudflare test site keys.
9. At beta launch, disable site-wide password protection under **Project
   configuration > Access & security > Visitor access**. Netlify Basic Auth
   disables CDN caching for the whole site; use application authentication for
   `/app` instead.

If the current published commit is not an ancestor of `main`, review the first
`main` to `production` release carefully because it reconciles the live and
integration histories.

## Release workflow

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

For a faulty release, use **Netlify > Deploys > Publish deploy** to restore the
last known-good production deploy. A rollback republishes an existing deploy and
does not consume production-deploy credits. Follow with a corrective change on
`main` so the next release does not reintroduce the fault.

## Build filtering

`scripts/netlify-ignore-build.js` stops a build only when every changed path is
in a known non-web area: backend, dashboard, docs, Supabase migrations, GitHub
workflow metadata, or root Markdown documentation. Any web, shared application,
asset, dependency, configuration, mixed, empty, or unresolved change continues
the build. This fail-open behavior prevents an optimization from suppressing a
required site update.

## CDN and startup budgets

Netlify serves static deploy assets from its global CDN. HTML uses
`Cache-Control: public, max-age=0, must-revalidate`; fingerprinted Expo assets
and WOFF2 startup fonts use a one-year immutable browser lifetime. The Render API
returns `Cache-Control: no-store` for authenticated and health responses.

The Netlify build runs the configuration validator before exporting. Run the
same production export and budget gate before a preview:

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
should report a Netlify cache hit. Never cache authenticated Render responses.

## Usage baseline and monitoring

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
