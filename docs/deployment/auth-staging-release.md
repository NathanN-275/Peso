# Authentication staging and release runbook

This runbook prepares authentication acceptance for the Public Web Beta.
The approved deployment plan defines the release gates and action-time approvals.
The active MVP uses Render and Supabase. Follow the current runtime boundary and
the existing gate tracker when preparing a hosted test.

[Approved deployment plan](public-beta-launch-plan.md) ·
[Current runtime boundary](web-mvp-runtime.md) ·
[Live release gates](public-beta-acceleration-plan-20261105.md)

## Staging test boundary

Prepare the existing isolated staging boundary in this order.

1. Verify `peso-staging` (`iseqgaewjpjcxrndibep`) and its reviewed migration
   history, grants, geography dataset and Before User Created hook. Preserve
   existing users, rows and media. The live tracker records the current saved
   settings and the separate approvals required for any hosted test changes.
2. Verify the fresh staging Render pair and save its provider-assigned HTTPS
   `onrender.com` API origin, two service IDs, source commit and Blueprint hash
   in the reviewed binding. Verify the API allows
   `https://main--peso-webapp.netlify.app` for the Web App.
3. Verify the exact private candidate at `https://main--peso-webapp.netlify.app` and its
   Supabase binding before providing fixture credentials. The dispatcher uses
   `PESO_RELEASE_ENV=render-beta` and requires an accepted
   `config/render-beta-release-binding.json`. A pending binding stops the build.
4. Verify the real staging Turnstile widget, provider CAPTCHA settings and
   token acceptance for `https://main--peso-webapp.netlify.app/auth/turnstile/`. Verify the
   widget hostname restrictions and use the source validator to check these
   values. Restrict Cloudflare test keys to isolated synthetic challenge tests.
5. Configure the native preview with the same verified staging Auth, API and
   challenge bindings. Verify native callbacks and the required Maestro flows
   on the supported Xcode/device toolchain.

[Candidate binding](public-beta-candidate-binding.md) ·
[US admission requirements](us-ip-admission.md)

For the initial smoke test, record the Render deploy commit for both services
and the Netlify deploy ID and commit. Confirm that the API's `/health/ready`
reports ready, that the Netlify login URL returns 401 without a visitor session,
and that the API allows the exact Netlify origin on a CORS preflight to
`/videos/capabilities`. Confirm that the same API route returns 401 without an
app session. In the approved staging browser session, log in through Supabase
and verify that the app's authenticated capabilities request returns 200 from
the bound Render endpoint. Record statuses and origins without credentials.

Enter only the staging Supabase service-role credential and the two staging-only
cleanup and budget tokens in Render. The backend verifies user tokens through
Supabase Auth and does not read a local Supabase JWT signing secret.

The staging E2E process uses `PESO_E2E_SUPABASE_SERVICE_ROLE_KEY` to create
isolated users and generate confirmation and recovery links during an approved
test. Keep that value in the runner under its exact variable name.

## Private-media configuration

The staging Blueprint and Netlify dispatcher explicitly disable private media
for the initial login and backend smoke test. The current private-media routes
accept only `usepeso.com` origins and use `SameSite=Strict` cookies. The selected
Netlify address needs a compatible media transport before enabling that gate.

That window requires the approved backend flag `PRIVATE_MEDIA_ENABLED=true`,
the reviewed database provider-policy activation, and
`EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED=true` in the exact private frontend build.
Record these values with the runtime source and artifact identities. The
earlier local browser fixture built with that frontend flag false and covers
the upload interface and recorder. Managed private media needs its own
two-owner acceptance against the activated candidate.

## Exact redirects

Allow only these production destinations in Supabase Auth, plus the exact
staging equivalents:

- `https://<web-host>/app/login`
- `https://<web-host>/app/reset`
- `pesoapp://login`
- `pesoapp://reset-password`

The client rejects unknown native schemes, hosts, path suffixes, credentials,
and ports. Signup confirmation and password recovery are separate destinations;
auth URL credentials are redacted from logs.

Native callbacks use Supabase PKCE codes only. Before enabling this version,
expire or reissue any outstanding implicit-flow email links: token-pair callbacks
are rejected rather than installed as a session.

## Resend and Supabase Auth

Use a verified auth-only sender domain and configure Resend as Supabase custom
SMTP. Keep the SMTP password in Supabase only. Verify SPF, DKIM, and DMARC;
retain delivery, bounce, and complaint events; and disable email click/open
tracking because rewritten authentication links can fail. Enable email
confirmation, the eight-character password policy, reviewed Auth rate limits,
and CAPTCHA only after both clients can produce tokens.

## Automated release gate

Install Playwright's Chromium browser once on the release runner, then provide:

```text
PESO_E2E_ENV=staging
PESO_E2E_ALLOW_ADMIN_FIXTURES=true
PESO_E2E_WEB_BASE_URL=https://main--peso-webapp.netlify.app
PESO_E2E_SUPABASE_URL=https://iseqgaewjpjcxrndibep.supabase.co
PESO_E2E_SUPABASE_SERVICE_ROLE_KEY=<runner-secret>
PESO_E2E_SIGNUP_EMAIL=<isolated-test-inbox>
PESO_E2E_SIGNUP_PASSWORD=<isolated-password>
PESO_E2E_RECEIPT_DIR=<absolute-private-directory>
```

Verify the private Netlify artifact and its staging Supabase binding before
providing fixture credentials. Create a private directory outside the checkout
with mode `0700` for the receipts. Each account creation attempt writes an
intent first and records the account ID once observed. Keep those files and
Playwright artifacts private. Reconcile intent-only entries against the
approved test identities and run window. Review the exact IDs and obtain
separate cleanup approval before deleting accounts.

Set the required public Supabase URL/key, real staging Turnstile site key,
bound Auth challenge URL, accepted Render API URL and
`EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED=false`. Use
`PESO_RELEASE_ENV=render-beta` for the staging website validation. Run
`npm run release:env` before the separately approved hosted test window.
The current pending Render binding must be resolved through its acceptance
gate before this validation can pass.

During the approved window, `npm run release:verify` runs the local helper
chain and invokes the staging Playwright suite. The helper stops when a
command fails; Playwright also stops at its first failed test. A failed worker
can otherwise run account-creation hooks again. Keep the fixture receipts even
when a run stops early.

The suite covers five browser Auth cases and fake-camera recording through
upload review. It creates a login account, a recording account and the
supplied signup identity during a successful run. Its generated links verify
callback behavior. Verify real Resend delivery separately with the test inbox.
The complete upload-to-analysis, save/export/deletion/recovery, two-owner,
geography, native and production-artifact gates retain their own acceptance
evidence. Use the exact Web MVP Linux image checks for Gate 2 alongside the
helper's local backend checks.

Run `npm run maestro:auth` and `npm run maestro:release` against an installed
iOS preview/development build after Xcode 26.4 or newer and Maestro are
available. Required Maestro values are described in `.maestro/README.md`.

## Failure scenarios

Record evidence for all of the following before production rollout:

- challenge success, load failure/retry, expiry, always-fail, duplicate token,
  reload, and wrong-action/untrusted-message rejection;
- signup, confirmation, login, session restore, background/foreground refresh,
  logout, reset request, expired reset, and password update;
- upload validation and side-view quality preflight;
- durable queue recovery, worker restart, timeout, failed analysis, and retry;
- playback, overlays, pins, gaps, limited results, save/edit/delete/export, and
  the same saved lift on web and native;
- ownership isolation, signed URL expiry, quota enforcement, exact CORS, and
  expired-session behavior.

## Production rollout and rollback

The approved deployment plan and the concrete rollback packet determine the
hosted sequence and action-time approvals. Required Auth rollout checks follow.

1. Pass every prerequisite staging gate. Bind the verified web/native artifacts,
   callback URLs and Turnstile configuration to the release SHA.
2. Ship the verified web and replacement native preview during the approved
   rollout while CAPTCHA is disabled. Verify supported clients produce tokens
   and mark older beta builds unsupported before CAPTCHA activation.
3. Enable project-wide CAPTCHA during the separately approved hosted step, then
   verify login/logout and one complete beta-account side-squat smoke test.
4. If authentication fails, execute the approved rollback packet. Identify its
   previous artifacts and Auth settings before applying it. Coordinate API and
   worker rollback and retain additive migrations while jobs reference them.
5. Obtain Nathan's action-time confirmation before exposing the combined public
   candidate after the prerequisite release gates pass. Verify staging, previews
   and historical deploy access controls during the public smoke checks.

[Launch and approval gates](public-beta-launch-plan.md) ·
[Combined candidate and provider binding](public-beta-candidate-binding.md)
