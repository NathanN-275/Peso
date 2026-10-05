# Combined candidate binding

Nathan selected existing PesoDatabase on September 22, 2026. The public beta
candidate uses `render-public-beta.yaml`, which records the existing beta service
names, Starter sizing, manual deployment, production database discriminator,
explicit PesoDatabase URL, 72-hour retention and $50 projected intake stop.
The historical `render-beta.yaml` and its staging validation workflow remain
historical staging artifacts. Do not use them for the combined public candidate.

This new blueprint is a review artifact, not an instruction to provision or
sync resources. Use existing API `srv-dak9ohfqj5pc73ac2ga0` and worker
`srv-dak9ohfqj5pc73ac2g8g`. Verify service IDs, repository, region, current
configuration and costs immediately before any approved operation. Resuming paid
services and public launch each require Nathan's separate approval.

Configure only the selected project's server credentials; never copy the staging
service-role key. Resolve `BACKEND_CORS_ORIGINS` to the verified new private site.
Keep the geographic flag true in the candidate configuration, but do not deploy
until the dataset, Auth hook and incoming proxy contract in `us-ip-admission.md`
are ready. `TRUSTED_PROXY_CIDRS` remains unset pending provider verification.
Budget token and cleanup token remain secret-store inputs. The blueprint does
not install a billing collector, notification delivery or cleanup schedule.

## Web build gate

`config/combined-web-release-binding.json` remains pending. Before marking it
`private-candidate-verified`, record the new project's exact site ID/origin,
verified beta API URL, backend source commit and reviewed blueprint SHA-256.
Verify provider access controls on production, previews and branches. This
status describes private candidate infrastructure evidence only; it is not
Nathan's human acceptance or launch authorization.

For the bound new Netlify project, build dispatch forces
`PESO_RELEASE_ENV=public-beta` in every context. Release validation requires the
selected database, existing service IDs, exact bound API/challenge origin, a
real Turnstile key and no overriding `EXPO_PUBLIC_BACKEND_URL`. It rejects the
historical app site ID and a pending binding. Local fixture builds do not prove
these provider controls or runtime acceptance.

Before activation, capture the current environment references without exposing
secret values. Rehearse migration/restore and verify backend compatibility with
the selected database. A code rollback must retain migrations needed by the
previously accepted version; changing the Supabase URL is not a data rollback.

## Read-only provider and schema verification — September 22

Fresh Render connector reads of both service IDs confirm the API and worker are
still suspended, each has one Starter instance in Oregon, both use repository
`NathanN-275/Peso` on `main`, and automatic deployment and previews are off.
The API reports `https://peso-beta-api.onrender.com`, `/health/ready`, root Docker
context and no command override. The worker reports
`python -m app.jobs.analysis_worker` with 300-second shutdown grace. No service
was changed or resumed. These reads do not verify secret bindings or runtime
health while suspended.

The candidate blueprint passed Render's official JSON schema with zero errors,
using `jsonschema 4.26.0` installed in a temporary directory. Evidence digests:

- Schema URL: `https://render.com/schema/render.yaml.json`
- Schema SHA-256: `57aa0a1ff9c3b2d0fcb91b790b7b285aef6397adb0c92930e6e601054444cfe5`
- Blueprint SHA-256: `c42fe2583fb1b252d47603e9066703ce9723049a541939f4435cf121db3552f3`

This is structural validation, not Render's authenticated semantic validation
or a dry-run of updating existing services. The Render CLI is not installed;
the protected CI validation remains required. GitHub CLI reports the stored
NathanN-275 token invalid, so authenticated PR creation is still unavailable
through that path. The combined release binding stays pending.

## GitHub protection readback — September 22

The authenticated browser session can read repository settings even though CLI
authentication is invalid. No settings were changed. Classic branch protection
is absent; repository rulesets show `Nathan` disabled and `Protect production`
active. Active ruleset ID `22210122` targets only `production`, with an empty
bypass list. It requires pull requests and status checks, requires branches to
be up to date, restricts deletion and blocks force pushes. Review approval count
was not established by the available readback; do not infer human approval.

Required status checks observed:

- `backend-security`
- `frontend-security`
- `secret-scan`
- `production-release-source`
- `netlify/peso-webapp/deploy-preview`
- `container-security`
- `reservation-database-security`
- `marketing-build`
- `netlify/peso-marketing/deploy-preview`

These Netlify checks refer to historical projects. They do not prove that the
new combined candidate was built or remains private. Capture the new project's
actual check identity before proposing a ruleset change; retain existing
protections until the reviewed replacement is configured. No push, PR, merge,
rule modification or publication occurred during this inspection.
