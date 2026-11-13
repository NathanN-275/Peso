# Combined candidate binding

The fresh production API and analysis worker use `render-public-beta.yaml`,
`Dockerfile.mvp`, Supabase video Storage and PesoDatabase. The fresh staging
pair uses `render-public-beta-staging.yaml` and `peso-staging`. Each pair has
one Starter API and one 1 CPU / 2 GB worker with automatic deployment off.
The historical pair stays suspended. The
[deployment plan](public-beta-launch-plan.md) defines provisioning approvals and
the exact source verification. The
[MVP runtime boundary](web-mvp-runtime.md) covers Azure exclusion.

Configure distinct credentials for each Supabase project. Set production
`BACKEND_CORS_ORIGINS` to the verified private site origin. The
[US-IP signup hook](us-ip-admission.md) runs in Supabase Auth. The Blueprints
require secret inputs for cleanup and budget controls. Billing collection,
alert delivery and cleanup schedules have their own acceptance gates.

## Web build gate

`config/combined-web-release-binding.json` remains pending. Before marking it
`private-candidate-verified`, record the new project's exact site ID/origin,
verified beta API URL, fresh API and worker IDs, backend source commit and
reviewed Blueprint SHA-256. Replace the historical service ID pins in the
validator and follow the exact-occurrence review for the source scanner.
Verify provider access controls on production, previews and branches. This
status describes private candidate infrastructure evidence only; it is not
Nathan's human acceptance or launch authorization.

The shared root Netlify configuration has no branch-wide staging environment.
The dispatcher applies the four historical staging values only to project
`230da8eb-f00e-45d4-ba54-95f2e26f21c4`, `CONTEXT=branch-deploy`, `BRANCH=main`.
This avoids overriding the combined project's independently configured database,
API and challenge origin when it builds from `main`. Existing historical keys
remain provider inputs; no key is copied between projects. Outside that tuple,
the dispatcher preserves provider inputs except for forcing the combined release
scope. Release validation must reject missing/mismatched combined values rather
than silently repair them.

For the bound new Netlify project, build dispatch forces
`PESO_RELEASE_ENV=public-beta` in every context. Release validation requires the
selected database, reviewed service IDs, exact bound API/challenge origin, a
real Turnstile key and no overriding `EXPO_PUBLIC_BACKEND_URL`. It rejects the
historical app site ID and a pending binding. Local fixture builds do not prove
these provider controls or runtime acceptance.

Before activation, capture the current environment references without exposing
secret values. Rehearse migration/restore and verify backend compatibility with
the selected database. A code rollback must retain migrations needed by the
previously accepted version; changing the Supabase URL is not a data rollback.

## Historical provider and schema verification — September 22

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

## October 28 provider observation

Authenticated browser readback found only the historical `peso-marketing`
(`19cbad85-dd2d-4d3b-a24a-242de78d30af`) and `peso-webapp`
(`230da8eb-f00e-45d4-ba54-95f2e26f21c4`) projects in the selected team list.
Both have private production and preview visibility. Team default is Private for
new projects. This is a bounded observation of that team, not proof of another
team's inventory or every historical deploy URL's effective protection.

The app's build-log setting was Public and was changed to Private; reload
confirmed the saved value. Build command/base/package/publish/functions settings,
active-build status, branch selection and Node 24.x remained unchanged in the
readback. No deploy, repository link, credential, project visibility, domain or
billing setting was changed. The Free-plan period shown is October 4–November 3,
with 1.8 credits used and 298.2 remaining; this is a dated baseline, not a future
cost approval. Provider readback and source guard checks do not satisfy Gate 11.
The new project/binding, real environment verification and protected deploy remain
pending; do not fill the binding from historical projects or synthetic fixtures.

## October 30 private project preparation

Nathan authorized connecting only `NathanN-275/Peso` through the existing GitHub
integration. A new `peso-public-beta` project was created, site ID
`76ffb7be-b126-4ae0-a972-ca5a244895fa`, with origin
`https://peso-public-beta.netlify.app`. The repository chooser listed only Peso;
no broader permission or new credential was requested. Production and Deploy
Preview visibility both read Private. Deploy logs defaulted Public and were
changed to Private, with saved readback. Cookie-free anonymous requests to the
root and exact bootstrap deploy permalink returned HTTP 401 login redirects.
These are bounded observations of those URLs, not every future route or preview.

The initial deployment `6ae4cd378e43ceb38bb9a222` succeeded privately from remote
main `98bad175cf2025741632244f4dd2da6b9866f87f`. It is the old marketing bootstrap,
not the current combined candidate. Main is the current production branch;
automatic builds and PR previews remain enabled, with no branch deploys. The
selected team is Free ($0), with no saved payment card and no overage charges
shown before creation. No paid upgrade, public transition, custom domain or
Supabase migration was performed.

Keep `config/combined-web-release-binding.json` pending. The actual combined
source/artifact, server/API/blueprint binding, environment, protected source and
check identity, all required access controls and browser/native acceptance still
need verification. This private bootstrap is infrastructure progress and does
not satisfy Gate 11 or Nathan's final public-launch approval.
