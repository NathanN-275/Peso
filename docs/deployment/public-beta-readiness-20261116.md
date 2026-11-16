# Public Web Beta readiness refresh — November 16, 2026

Nathan selected repository-enforced CI and full raw reports as the Gate 2
source instead of the inaccessible Daybreak portal. This changes evidence
collection, not security thresholds. The [live tracker](public-beta-acceleration-plan-20261105.md#current-gate-tracker--november-16-2026)
records all 14 statuses. Public launch remains blocked.

## Source and fresh evidence

The starting checkout was stale branch `fix/merged-source-secret-coverage` at
`f6a9f68637ccc01fbc218fefc36c9e0be12913fd`, with pre-existing local edits.
Its audits failed: root scope mismatch and web 8 HIGH/1 CRITICAL. Those results
are not the current main candidate. They remain in that checkout's ignored
artifacts. Existing edits in that checkout and `public-web-beta` were preserved.

Refreshed GitHub main is `e9370d9f6675be3fe5567043b458ab51afae0933`.
[Security Checks run 43968645784](https://github.com/NathanN-275/Peso/actions/runs/43968645784)
completed successfully: 22 jobs passed; production-release-source was correctly
skipped for a main push. Frontend typecheck/policy/audit, marketing build/audit,
Python audit, secret scanning, private-media SQL matrix, reservation isolation,
container scan and offline runtime all passed. Passing jobs are evidence for
this exact source, not deployed production acceptance.

Downloaded audit ZIP SHA-256 values match GitHub's artifact digests. Root report:
zero HIGH/CRITICAL, seven MODERATE; each of three web reports: zero findings.
Decisions identify the same candidate SHA and exit zero. Input and artifact
hashes are in [the sanitized receipt](evidence/release-readiness-20261116.json).
Raw ZIPs, CI job inventory and full container log are retained locally in
`/private/tmp/peso-beta-readiness-20261116`; this temporary folder is not a
protected backup. GitHub audit artifacts expire February 14, 2027.

The container log records config image ID
`sha256:95cdd6db467287226853e5dacc114e08f743a2a39f6b2ca2ffa6a3f50cc568ff`,
Trivy v0.74.0, 90 Wolfi packages, HIGH/CRITICAL filtering and zero blocking
findings. Offline UID/GID 10001 verification passed API/worker imports, three
pose models, inference, quality preflight, H.264/ffprobe/rotation/thumbnail,
analyzed export and MOV/MKV/WebM checks. This build was not published; its image
identity does not establish equivalence to a later Render rebuild.

## Implemented evidence collection

Security CI now retains Python's raw JSON audit plus runtime/scanner versions,
and container HIGH/CRITICAL JSON report, inspected image identity, source SHA
and offline runtime log. Uploads run after attempted success/failure, use the
source SHA/run attempt, require evidence and retain it for 90 days. Bash
pipefail preserves the runtime failure status through tee. Existing HIGH and
CRITICAL blocking, unfixed findings and pinned Trivy action remain enforced.
Container JSON is filtered to the existing blocking severities; it does not
claim an all-severity clean scan. Node/web retention remains in place.

Four focused workflow tests and whitespace validation passed locally. YAML was
parsed with the existing checkout's installed yaml package via NODE_PATH; no
candidate dependencies were installed. Hosted execution of the changed workflow
is still required. Local Docker is not running, so no local container rebuild
or new runtime acceptance is claimed.

## Provider reconciliation and next work

Read-only Supabase inventory confirms production and staging ACTIVE_HEALTHY,
November recovery INACTIVE. Production has 21 migrations ending 202608270001;
staging has 52 ending 20261103022851. Inventory does not prove RLS, Auth,
Storage-byte recovery or production migration acceptance. The November hosted
restore and isolated migration rehearsal supply Gate 5's historical scoped pass.

Next: run this retention change in hosted CI and inspect its raw packet; resolve
Gate 3's private provider/history disposition; revalidate the accepted staging
binding and complete Gate 4/12 on the current private candidate. Preserve queue
wait separately from analysis-stage time for the two longest supported clips.
Then obtain a fresh cutover recovery point and review production migration,
production service binding, guardrails and private-build acceptance in order.
Provider-only credential verification and the private GitHub Support response
cannot be inferred from clean scanners. No credentials, hosted data, domains,
service plans, visibility or production deployment were changed here.
