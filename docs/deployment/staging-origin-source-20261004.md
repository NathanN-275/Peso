# Same-site staging origin source checkpoint — 2026-10-04

Nathan approved the names `https://main.usepeso.com/app` and
`https://api-staging.usepeso.com`, then authorized preparing/testing the source
changes and pushing `feat/combined-public-beta` to update PR #47. No merge,
provider change, deployment, service resume or public launch is included.

## Source changes

- `netlify.toml` fixes the private `main` branch's backend URL to
  `https://api-staging.usepeso.com` and challenge document to
  `https://main.usepeso.com/auth/turnstile/`.
- `scripts/release-env.js` accepts that exact staging origin pair only with an
  accepted Render beta binding, valid source/Blueprint digests, and the existing
  API/worker IDs `srv-dak9ohfqj5pc73ac2ga0` /
  `srv-dak9ohfqj5pc73ac2g8g`. Pending bindings, wrong service IDs, old cross-site
  URLs, URL credentials/paths/parameters and backend overrides remain rejected.
- `render-beta.yaml` prepares exact CORS origin `https://main.usepeso.com` for
  the existing beta services. Manual deployment, secrets and instance plans are
  unchanged. This file is not synced to Render here; a later provider review
  must preserve the worker's approved live sizing rather than blindly syncing
  unrelated baseline fields.
- Regression tests cover the approved pair and negative cases. The independent
  Azure Student configuration and production Blueprints are unchanged. Netlify
  dispatch still exports the app only on the stable private `main` branch;
  feature PR previews remain marketing-only.

`config/render-beta-release-binding.json` deliberately remains **pending**. A
synthetic accepted binding is used only in unit tests; it is not deployment
evidence. No successful hosted release or same-site cookie transport is claimed.

## Verification

- Focused release/Blueprint policy checks: 17 passing tests. Four expected
  failures were observed before updating the source to the new origins.
- Full policy suite: 223 passing tests.
- App TypeScript check: passed.
- Backend suite: 536 tests completed successfully, 19 skipped; synthetic local
  configuration only, no hosted project or real-user test mutation.
- YAML parse and exact CORS/manual-deploy checks: passed.
- An otherwise complete synthetic staging environment still fails release
  validation against the real tracked pending binding, as required.
- Whitespace check: passed.
- Redacted Gitleaks scans of the staged changes and the previously unpushed
  log-redaction commit: passed. The public service IDs in test fixtures are
  named resource constants; no new scanner exclusions were introduced.

Local Render CLI/schema validation was unavailable (CLI absent and Python
`jsonschema` unavailable). The existing PR workflow performs provider Blueprint
validation and container/runtime checks; those must pass on the pushed source.
This checkpoint does not replace full release verification, hosted auth/media
tests, native Maestro evidence or refreshed image/security acceptance.

## Next blocker

Observe CI/security/Blueprint results on the new PR head before considering a
merge. DNS/TLS setup and the accepted runtime release binding are still pending;
do not merge simply to make the failed `main` build retry. Netlify's external-DNS
branch certificate step also requires a successful protected branch deployment.
Resolve that staged bootstrap order explicitly before provider writes; do not
fabricate an accepted binding or bypass visitor protection to break the loop.

The implementation of revocable media transport/session checks and hosted
authentication acceptance remain separate chunks. Gate 4 remains open.
