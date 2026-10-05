# Guarded dependency audit treatment — 2026-10-05

## Authority and result

Nathan approved the [two-advisory proposal](dependency-audit-treatment-proposal-20261005.md)
and its expiry, **2026-10-12T23:59:59Z**, before implementation. Parent source:
`ca1b9cea7296d7baba4313b07b7547d20afdec25`, `feat/combined-public-beta`.

The real audit CLI now accepts the reviewed local backports under project
policy after its own fail-closed preflight. Raw registry findings remain
visible and retained. This is **not a clean registry audit**, official patched
release, package-wide VEX assertion, or acceptance of the public beta.
The expiry is a cutoff: the policy fails at or after that instant, even if a
run crosses it during evaluation. There is no automatic renewal.

No dependency version, lockfile, installed patch, manifest, verifier, npm
script, existing allowance, production input, credential, provider, database,
DNS, PR state, or public visibility changed. No push, merge, workflow dispatch,
or deployment occurred. Unrelated untracked notes were preserved.

## Implemented safeguards

- The CLI retains the complete output of every registry attempt and runs real
  read-only patch verification before considering a backport treatment.
  It independently pins verifier, lockfile, manifest, both patches, and the
  checked Expo certificate/iOS signing and Micromatch consumer files. It
  rejects redirected paths and missing/changed/old/partial/extra installed
  copies rather than trusting a success assertion or prior lifecycle hook.
- Only the exact braces and Forge advisory URLs, source IDs, package names,
  dependency names, high severity, affected ranges, installed paths, and
  versions from the proposal qualify. Existing image-size/brace-expansion
  allowances are not broadened. No parent-package blanket exception exists.
- A module-private capability enables the two new treatments only after the
  CLI preflight. Exported classification helpers cannot enable them with
  `true`, an object, or a separately created Symbol. There is no environment
  variable that asserts patch verification or extends the expiry.
- Iterative graph evaluation requires every reachable relevant branch to
  reach concrete allowed advisory evidence. It preserves justified Metro
  cycles but rejects advisory-free siblings/cycles, dangling causes, malformed
  identities, unknown severities, and severity-masked causes.
- A frozen consumer-scope fingerprint covers 149 source/configuration files:
  code under `src`, `lib`, `web`, `dashboard`, `context`, and `assets`; root
  App platform variants and the listed entry/build configuration files; and
  six web export/release verification scripts. JS/TS variants, JSON, Astro,
  HTML, Vue, Svelte, MDX, and TOML are included. Environment/hidden files,
  dependency trees, and generated `dist` outputs are excluded. Changed or new
  covered files require a scope review, not an automatic hash refresh.
- Decision evidence includes actual audit-script/input hashes, source commit
  and dirty-tree state when available, expiry, scope fingerprint, registry
  metadata, treated advisory leaves, blockers, attempt checksums, and outcome.
  CI refuses missing/invalid Git commit provenance. A standalone source-only
  diagnostic may have null Git metadata; that is not CI/release evidence.

Frozen source-scope SHA-256:
`6bb00beeef8b04023e9bfe30e042bb7f414a2611f88293b10cce0f489e83a242`.
Audit implementation SHA-256:
`672b8aa5daa03bf35ed06c8eed761c9a2cd95516c2a9bc3b858e87f093ed7170`.
All reviewed original input pins remain recorded in the proposal and patch
installation evidence; the CLI also records the actual values on each run.

## Raw evidence and CI retention

Each invocation creates a fresh ignored `artifacts/npm-audit/run-*` directory,
without overwriting another run. It stores `attempt-N.stdout`,
`attempt-N.stderr`, a byte-exact `npm-audit.json` for a usable report, and
`decision.json` on success or evaluation failure. Invalid registry responses
and retries remain available as raw attempt output. Raw error bodies are not
duplicated into console error messages. An unsafe/unwritable evidence location
fails closed and cannot promise a retained file.

The three existing audit workflows now upload attempted audit evidence on
success or failure, using the existing pinned upload-artifact action, unique
workflow/source/run-attempt names, missing-file errors, and 90-day retention.
Earlier failures that prevent audit invocation create no audit report; the
upload condition does not pretend otherwise. YAML parsing passed. These
workflow edits have not been run on hosted Linux CI.

Pre-commit final-code evidence:

| Check | Retained directory | Raw output SHA-256 |
| --- | --- | --- |
| Real checkout, CI provenance enforcement, exit 0 | `artifacts/npm-audit/run-yu8jY2` | `2499bc3a117b9787d1912b479c9454bd52aa9818e09074c68d9e199e65aa5e54` |
| Source-only clean install, local diagnostic, exit 0 | `/private/tmp/peso-audit-policy-install.nwR9EU/artifacts/npm-audit/run-4iogZj` | `26ffb749105190d83b86f039e6cb547e5975ca0959d92ec2e6a6e4389affc561` |

The checkout report retains **25 HIGH, 0 CRITICAL** package entries, while the
standalone snapshot retains 23 HIGH. Both have zero project-policy blockers.
Every cause is evaluated; changing registry/meta-vulnerability counts are not
an acceptance pin. The only newly treated direct leaves are the two reviewed
backports. These runs record the parent Git commit plus dirty source, and the
actual implementation hash above, rather than pretending uncommitted bytes
were already the parent's committed code. Post-commit invocations record the
new commit directly. Reports/artifacts remain outside Git and are not backups.

## TDD and verification

Tests use the approved public evaluator and CLI seams. Red-before-green slices
reproduced the mixed-cycle gap, malformed report acceptance, missing retention,
unverified/redirected patch evidence, expiry boundaries, the absent treatment,
new frontend/root/export consumers, and missing CI commit provenance before
their respective safeguards were added. Further negative/compatibility checks
cover changed advisory metadata, mixed new causes, old installed Forge bytes,
missing/extra copies, caller assertions, registry retries/errors, and exact
raw-output retention. Only external registry, clock, and Git metadata boundaries
are mocked in CLI fixtures; actual patch verification and installed bytes are
used. Synthetic RSA private keys exist only in memory.

| Final check, local macOS x64 | Result |
| --- | --- |
| Audit, installer/verifier, and installed-package tests — Node 20.20.2 | 73 pass, 0 fail, no skips |
| Same combined tests — Node 22.23.3 | 73 pass, 0 fail, no skips |
| Same combined tests — Node 24.18.0 | 73 pass, 0 fail, no skips |
| Workspace policy suite | 279 pass, 0 fail, no skips |
| Source-only clean-install policy suite | 279 pass, 0 fail, no skips |
| Workspace and isolated typecheck / installed-patch verification | exit 0 |
| Real registry audit, final code, checkout and isolated diagnostic | exit 0 under project policy; raw findings retained |

The combined tests comprise 38 audit tests, 18 installer/verifier tests, and
17 installed-package security/compatibility tests. Gitleaks 8.30.1 checked
the seven changed files with redacted output and found no leaks;
`git diff --check` passed. These are changed-file checks, not completion of
full-history secret remediation.

The isolated copy contains 625 tracked regular source files with updated audit
code/tests; environment files, Git metadata, existing dependency trees, ignored
artifacts, and unrelated untracked notes were not copied. It ran the unchanged
lockfile through two actual clean installations on Node 24.18.0 / npm 12.0.2:

1. `npm ci --ignore-scripts --no-audit --no-fund` succeeded; subsequent
   `npm run --ignore-scripts audit:ci` exited 1 for missing patches. Its raw
   failure evidence is retained in `artifacts/npm-audit/run-GUtAXg` there.
2. Ordinary `npm ci --no-audit --no-fund` succeeded and applied/verified both
   patches. The final guarded audit, `deps:verify`, and typecheck passed.

Existing UUID deprecation and blocked fsevents lifecycle warnings were not
suppressed or converted into new lifecycle allowances. No full upstream Forge
suite, production build, native/browser E2E, or provider acceptance was rerun
as part of this policy implementation.

## Release hold and retirement

Forge prebuilt bundles remain **unpatched**. Source freezing and checked
consumer hashes are not complete proof of generated/deployed execution paths.
Production artifact inspection must exclude those bundles and bind evidence
to exact artifact digests. Local macOS checks cannot substitute for Linux CI,
matching release inputs, full acceptance, recovery, or action-time launch approval.

Next chunk: with Nathan's separate authorization, push the reviewed branch for
CI, inspect retained audit evidence and all checks at the exact final commit,
then address remaining production-artifact/release gates. Do not merge, deploy,
or launch based solely on this local policy result. Recheck official patched
releases to retire the backports; remove/update the treatment and its guards
together with compatibility/security verification. Expiry or altered evidence
blocks immediately. No ADR or domain-glossary update is warranted by this
temporary reversible treatment.
