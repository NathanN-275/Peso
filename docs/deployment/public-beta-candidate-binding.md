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
