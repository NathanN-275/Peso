# Security Operations

## GitHub Secret Scanning

Enable these repository settings before merging production deployments:

- `Settings > Code security and analysis > Secret scanning`: enabled.
- `Settings > Code security and analysis > Push protection`: enabled.
- `Settings > Code security and analysis > Dependabot alerts`: enabled.
- `Settings > Code security and analysis > Dependabot security updates`: enabled.

The `Security Checks` GitHub Actions workflow also runs Gitleaks on pushes and pull requests. GitHub push protection should still be enabled because it blocks secrets before they enter history.

## Local Security Checks

Run these before deploying backend security-sensitive changes:

```sh
npm run release:verify
```

The gate runs serially and stops at the first failure. It covers app and
dashboard typechecks/tests/builds, the production web export and budget,
staging web auth E2E, the complete backend suite with production-like values,
the migration/RLS audit, dependency audits, Gitleaks, and `git diff --check`.

Run Python dependency auditing when `pip-audit` is available. The protobuf advisory is currently ignored because `mediapipe==0.10.21` requires `protobuf<5`, while the available advisory fix starts at `5.29.6`; revisit this ignore when MediaPipe publishes a compatible release.

```sh
pip-audit -r backend/requirements.txt --ignore-vuln PYSEC-2026-1805
```

## Dependency Review Checklist

Use this checklist for every Python or Node package update:

- Audit result: run `npm audit --audit-level=high` for Node and `pip-audit -r backend/requirements.txt --ignore-vuln PYSEC-2026-1805` for Python when `pip-audit` is available.
- Lockfile diff: review new packages, removed packages, install scripts, native modules, and transitive dependency changes.
- Runtime risk: identify whether the dependency runs in the Expo client, FastAPI backend request path, build tooling, CI only, or local development only.
- Production exposure: note whether the package handles auth, storage paths, media files, request parsing, subprocess execution, or network calls.
- Advisory handling: document any ignored advisory with the package constraint, affected runtime, exploitability in this app, and revisit trigger.

Current tracked advisory exceptions:

- Python: `PYSEC-2026-1805` for protobuf remains ignored only because `mediapipe==0.10.21` requires `protobuf<5` while the available fix starts at `5.29.6`.
- Node: Expo transitive moderate advisories are not ignored in CI because CI fails only on high severity and above. Revisit them on each Expo SDK update and document any advisory that becomes high severity or ships in production runtime code.

## Request Provenance

See [request-inventory.md](/Users/nathan/Downloads/peso-app/docs/request-inventory.md) for the current frontend-to-backend and frontend-to-Supabase request inventory, HTTP policy, and client/server field boundary.

## Public Web Launch Gate

Before enabling open web signup, complete and record these provider settings:

- Supabase Auth: enable Cloudflare Turnstile CAPTCHA, require email confirmation,
  configure the exact production `/app/login`, `/app/reset`,
  `pesoapp://login`, and `pesoapp://reset-password` redirect URLs,
  set the password policy and review Auth rate limits.
- Cloudflare: create a Turnstile widget restricted to the production web origin;
  place only its site key in Netlify as `EXPO_PUBLIC_TURNSTILE_SITE_KEY`, and its
  secret key only in Supabase Auth settings.
- Netlify: verify the deployed CSP and HSTS headers on `/`, `/app/signup`, and a
  deep link. The CSP intentionally permits HTTPS API targets because the backend
  hostname is an environment setting; tighten `connect-src` to the final API and
  Supabase origins once those domains are fixed.
- Resend: use a verified authentication-only sender domain through Supabase
  custom SMTP. Verify SPF, DKIM, and DMARC; keep delivery/bounce/complaint logs;
  and disable click/open tracking so auth links are not rewritten.
- GitHub: protect `production`, require the Security Checks and Deploy Preview
  checks, and enable secret scanning, push protection, Dependabot alerts, and
  Dependabot security updates.

CAPTCHA is enforced project-wide by Supabase. Web and native sign-in, signup,
and password-reset requests now require a fresh challenge token. Enable CAPTCHA
only after the staging web and Maestro suites pass with the matching Cloudflare
test site/secret pair and all older native beta builds are marked unsupported.
The Turnstile secret, Supabase service-role key, and Resend SMTP password must
never appear in `EXPO_PUBLIC_*`, client bundles, test artifacts, or Git.

See [auth-staging-release.md](deployment/auth-staging-release.md) for provider
configuration, rollout, and rollback.
