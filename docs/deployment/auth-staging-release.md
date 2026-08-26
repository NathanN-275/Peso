# Authentication staging and release runbook

This runbook is the source of truth for the side-view squat beta release. It
does not authorize provider spend, Azure provisioning, public staging
visibility, or production changes. Follow the cost and approval gates in
`docs/deployment/azure-staging-release.md` before creating Azure resources.

## Staging stack

Create isolated resources in this order:

1. A separate Supabase project in the confirmed organization and region. Apply
   every tracked migration, create the `videos` and avatar buckets, run the RLS
   audit and Supabase security advisor, and create isolated E2E users.
2. The Azure Container Apps staging API and event-driven worker defined in
   `infra/azure/staging`, using only staging Supabase values. Bootstrap them
   disabled, seed secrets locally, and verify `/health/ready` before allowing
   worker executions.
3. A stable Netlify branch deployment wired to the staging API and Supabase
   project. Its `EXPO_PUBLIC_AUTH_CHALLENGE_URL` must point to its own exact
   `https://<staging-host>/auth/turnstile/` page.
4. A real staging-only Turnstile widget restricted to
   `main--peso-webapp.netlify.app`. Put its site key only in the Netlify branch
   context and its secret only in staging Supabase Auth. Cloudflare test keys
   are allowed only in isolated automated challenge tests; never configure them
   on the stable staging or production hosts.
5. EAS `preview` environment values for the same staging URLs and public keys.
   `eas.json` binds development, preview, and production build profiles to the
   matching EAS environments.

The staging E2E process may read `PESO_E2E_SUPABASE_SERVICE_ROLE_KEY` to create
and delete isolated users and generate confirmation/recovery links. That value
exists only in the test runner and must never use an `EXPO_PUBLIC_` prefix.

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
PESO_E2E_WEB_BASE_URL=https://<stable-staging-host>
PESO_E2E_SUPABASE_URL=https://<staging-project>.supabase.co
PESO_E2E_SUPABASE_SERVICE_ROLE_KEY=<runner-secret>
PESO_E2E_SIGNUP_EMAIL=<isolated-test-inbox>
PESO_E2E_SIGNUP_PASSWORD=<isolated-password>
```

Also set the five required `EXPO_PUBLIC_*` variables and
`PESO_RELEASE_ENV=staging`, then run `npm run release:verify`. The gate stops at
the first failure. Real Resend delivery is verified separately with the test
inbox because generated links intentionally bypass email delivery.

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

1. Pass every staging gate.
2. Ship web and the replacement native preview while CAPTCHA is still disabled.
3. Mark older beta builds unsupported.
4. Enable Supabase project-wide CAPTCHA and run login/logout plus one complete
   beta-account side-squat smoke test.
5. If authentication fails, disable CAPTCHA first, then republish the previous
   Netlify deploy while investigating. Roll back API and worker together when
   the failure is backend-related; do not reverse additive queue migrations
   while jobs reference them.

Changing the staging branch deploy from private to public is a separate release
action. Obtain Nathan's action-time confirmation immediately before that change,
then repeat the unauthenticated-route and authentication smoke tests.
