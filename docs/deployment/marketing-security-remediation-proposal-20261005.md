# Marketing dependency security remediation proposal — 2026-10-05

## Status and boundary

**Proposed, not approved or implemented.** Nathan requested the next small chunk
after the separate marketing dependency audit failed. Reviewed source:
`8f7094c71bc4b17774ce147e6fbe14c2825b2350`, branch
`fix/merged-source-secret-coverage`, PR #48. Main remains
`98bad175cf2025741632244f4dd2da6b9866f87f`.

This proposal addresses the current dependency/security failure only. It does
not advance credential, authentication, recovery, migration, admission, Render,
Netlify privacy, cross-surface or release gates. No dependency, lockfile, source
scope pin, exception, expiry, provider or visibility was changed in this review.
The five pre-existing untracked deployment notes are excluded and preserved.
No push, merge, workflow dispatch or deployment is authorized by this note.

## Before-state and coverage gap

Exact Netlify deploy `6ac44710452c6d000912db09`, build
`6ac44710452c6d000912db07`, is a marketing-only PR preview at the reviewed head.
Its actual build log installs `web` dependencies and reports six HIGH / one
CRITICAL, but the build succeeds. It is not a combined authenticated app artifact.

The subsequent read-only `npm --prefix web audit --json --audit-level=high`
returned exit 1 and seven HIGH / one CRITICAL / one MODERATE package entries.
These are different registry observations, not an allowance based on counts.
Each cause requires fresh examination. Preserved failing report, outside Git:
`/private/tmp/peso-marketing-audit.tAAcB5/npm-audit.json`, SHA-256
`1d19ca0390c2859f076fb73bcb27e5899559c64d7bab9c7c1eb2ed19aae03a35`.
Temporary evidence is not durable backup or hosted retention.

The root `audit:ci` reads root `package-lock.json` and invokes the reviewed
braces/Forge treatment. It does not audit the separate marketing lockfile.
`marketing-build` installs/builds `web` but has no blocking marketing audit.
Root/container successes do not excuse this gap or imply exploitability of
the static output. Registry findings remain blockers pending remediation.

## Dependency proposal

Use official patched packages, not new backports or advisory suppressions.
Proposed direct Astro target is **exact 7.2.8**, replacing `^7.1.6` in the
marketing package only. This is the first version listed as patched for the
[critical AVIF advisory](https://github.com/advisories/GHSA-26w7-cxv4-gfx2);
its [release](https://github.com/withastro/astro/releases/tag/astro%407.2.8)
raises the Sharp minimum to 0.35.4. The advisory also limits applicability to
processing attacker-controlled AVIF images; no claim that Peso's static site is
publicly exploitable or automatically unaffected is made.

[Published Astro metadata](https://registry.npmjs.org/astro/7.2.8), checked with
read-only npm view, declares Node >=22.12.0 / npm >=9.6.5 and optional Sharp
`^0.35.4`. The old locked Astro already has that Node floor. Marketing CI uses
Node 24; other build hosts still need their actual runtime verified during
candidate testing. Version existence and semver compatibility are not clean
install/build or complete current-audit acceptance.

Astro 7.2.8 npm integrity:
`sha512-19nfgzl1IHNYzIfamUIr4dYSQcovWfMO5JGlN7Ahlg6Q6R+nzSPWAh+VO/mSg0hhcea35JHY0wL5ADZUi0WiYQ==`.

The [separate primary-source review](marketing-dependency-primary-source-review-20261005.md)
records patched floors and parent ranges for the remaining seven HIGH packages
and smol-toml MODERATE, with one important unresolved cause:

| Package | Proposed minimum / hold |
| --- | --- |
| devalue | 5.9.3 (all seven recorded causes) |
| http-cache-semantics | **No verified patched target**; 4.3.0 is only a published candidate |
| js-yaml | 4.3.2 |
| nanoid | 3.3.18 |
| sharp | 0.35.4 plus matching native binary/libvips inventory |
| source-map-js | 1.2.2 |
| svgo | 4.1.0 (both recorded causes; stricter input parsing needs tests) |
| smol-toml | 1.9.0 |

The [cache advisory](https://github.com/advisories/GHSA-ch52-4w7c-c8xp) remains in
the failed report and lists **no patched version** at this review. Its owner
disputes the issue, and 4.3.0's published source
does not establish a security fix in the reviewed branch. Merely leaving the
registry's affected range is not patch evidence. Preserve this blocker even
if a candidate's raw audit turns green. No cache version change or applicability
exception is approved here. A focused source/consumer review must resolve it
before gate acceptance; if it requires a patch, treatment or other material
scope change, return to Nathan for a separate proposal.

Include the moderate fix if it resolves compatibly without
unrelated changes. Regenerate only `web/package-lock.json`, retaining all unrelated
locked entries where possible and recording every required transitive change.
No root dependency, root lockfile, Forge/braces patch, registry integrity or
historical ignore change is proposed. Prefer compatible parent resolutions;
do not add blanket overrides, use force, approve lifecycle scripts, or perform
a blind audit fix. If minimal compatible resolution leaves a blocker or introduces
a new relevant finding, stop and revise the proposal.

## Separate fail-closed web audit

Proposed new module/CLI: `scripts/npm-audit-web-ci.js`, invoked directly so root
package.json need not change. It must not import or inherit the root policy's
allowances. There are **no marketing advisory exceptions** in this proposal.

Required public boundary:

- Always audit the explicit repository `web` tree and its regular package/lock
  files, independent of caller cwd. Reject missing, redirected/symlinked or
  concurrently changed inputs; record both file hashes before and after audit.
- Use a locked, complete dependency report without omit/no-package-lock settings
  that hide build, optional or development dependencies. Record npm version,
  actual source SHA/tree/dirty state and executed script hash; missing CI
  provenance fails. Do not claim uncommitted implementation is in its parent SHA.
- Require a usable supported JSON report, sane metadata consistent with records,
  known severities/identities/paths, and a valid subprocess outcome. Any HIGH or
  CRITICAL finding fails without graph-derived exemptions. Unknown/malformed
  records, inconsistent counts, invalid exits, registry errors/timeouts and
  missing evidence fail closed rather than being treated as clean.
- Keep bounded transient retries. Retain full reports and each attempt's stdout/
  stderr outside Git, with hashes and a separate decision on pass and fail.
  Do not duplicate raw failure bodies or credentials into console summaries.
- Use unique ignored `artifacts/npm-audit-web/run-*` directories, safe regular
  evidence paths and no overwrites. A missing/unwritable evidence destination
  cannot produce an accepted decision. Report raw and gate status distinctly.
- Continue the existing HIGH/CRITICAL failure threshold; retain and report all
  lower severities rather than hiding them. No temporary marketing allowance,
  expiry extension, exception-count pin or registry-clean label with raw findings.

The [npm audit documentation](https://docs.npmjs.com/cli/v12/commands/npm-audit/)
confirms that audit-level controls failure threshold rather than report filtering
and that `audit fix` installs changes. The new guard must validate evidence, not
merely rely on a green install or a command configured to omit packages.

## Build, CI and release enforcement

Proposed changes, after implementation approval:

1. Add the web audit and always-retain 90-day evidence upload to the existing
   Security Checks marketing job, before any generated build. Keep upload action
   immutable and identify artifact by actual execution SHA/run attempt. Missing
   attempted evidence is an error; earlier install failure is not an audit pass.
2. Enforce the same web audit in `scripts/build-web.js` before invoking Astro or
   Expo, for both marketing and private-beta modes. Put it inside the existing
   safe output-cleanup/failure path: a blocked audit must leave no publishable
   partial or stale output. Restrict cleanup to the existing generated dist
   target; do not introduce new destructive scopes.
3. This shared wrapper covers both tracked Netlify build commands without
   changing either Netlify configuration, build-context dispatch or provider
   settings. Provider environment overrides and direct external commands are
   still live verification requirements, not assumed controlled by source.
4. Add an explicit web-audit entry to `scripts/release-verify.js`, with serial
   stop-on-failure semantics. Do not change its release-environment validator,
   pending production binding or earlier gates to make it run.

No extra dependency for the guard is proposed. Existing root audit/history scan,
GitGuardian, runtime/container, required production-source and staging migration
checks remain independent. No branch protection or provider change is authorized.
Netlify retention must be verified at the provider; this note does not promise
that GitHub artifact upload runs within Netlify.

## Frozen scope: mandatory two-stage review

The current 149-file scope was independently recomputed unchanged:
`6bb00beeef8b04023e9bfe30e042bb7f414a2611f88293b10cce0f489e83a242`.
Root audit implementation remains
`672b8aa5daa03bf35ed06c8eed761c9a2cd95516c2a9bc3b858e87f093ed7170`.

These proposed edits affect currently frozen inputs:

| File | Before SHA-256 |
| --- | --- |
| web/package.json | `91ef9fa6dd1231e9331627ea48a621bbf6b798443747503a407b2d68cb543137` |
| web/package-lock.json | `af4b8931f67be644bbe14c5cf73600d1d9e44e43e6dc171486169c7d01f3ab91` |
| scripts/build-web.js | `e77c8130443d1b2fc80abd6e8fb0535547b414f6ffda13505463d8652b95017a` |
| scripts/release-verify.js | `336d1c73e44c26a3a351522a174e29e619589d28e00055b230c8a30b1bcd3b5a` |

Stage A approval permits isolated candidate resolution, tests and the bounded
implementation above, **not** replacing the current frozen fingerprint. Keep the
root guard blocked on changed scope. Provide Nathan the complete before/after
dependency and consumer-path diff, exact candidate hashes, file inventory and
provenance, and install/patch/consumer verification results. Stop that chunk.

Stage B requires Nathan's explicit review/approval of those exact resulting
bytes/fingerprint before updating the single approved scope pin. Do not compute
and silently install a new pin, widen covered paths, remove guards, enable a
caller assertion, or treat this proposal as approval of unknown future bytes.
Any broader edit requires a fresh proposal. Approved advisory/manifest/consumer
pins remain unchanged, and expiry stays **2026-10-12T23:59:59Z**, with no renewal.
After any approved update, rerun all applicable checks at the resulting SHA.

## Agreed verification boundary proposed for approval

Use red-before-green tests at the new audit CLI/evidence and build-runner seams.
Cover clean, moderate-only, HIGH and CRITICAL; existing root-exception URLs must
still fail in the web guard. Cover malformed/unknown/empty-error reports, masked
severity/counts, invalid exit, timeout/retry exhaustion, missing/changed/symlinked
inputs and evidence, source provenance, and retained checksums on success/failure.
Mock only external npm/Git/clock/process boundaries; use real filesystem fixtures.

Build tests must demonstrate that audit failure prevents Astro/Expo execution
and removes generated output, while clean execution preserves the existing
marketing cleanup and combined dispatch. Workflow/release tests verify enforced
ordering and retention. Lifecycle approval is a separate reviewed question.

Candidate acceptance requires clean isolated installs on supported build runtimes,
web audit with zero HIGH/CRITICAL and valid retained evidence, unchanged root
patch/consumer verification, policy/typechecks, marketing builds/stale cleanup,
and a non-deployable combined fixture with dotenv disabled. After Stage B and
separate push authority, inspect hosted results and artifacts at their actual
SHAs. Production artifact/Forge execution-path proof and live privacy/bindings
remain unresolved and must follow before any release approval.

## Review verification and next blocker

This is research/documentation, not remediation acceptance. Existing boundary
tests passed on local Node 24.18.0: **45 pass, zero failures/skips** (root audit,
Netlify dispatch, dedicated marketing policy and release serial-stop tests).
`npm run deps:verify` passed. The scope/hash probe passed with 149 unchanged files.
No new web-audit guard, candidate install, lockfile regeneration, corrected audit,
full frontend build, hosted check or generated artifact acceptance was performed.
The retained before-state web audit remains **FAIL**; deployment gate stays blocked.

Next blockers: the unresolved cache finding and Nathan's Stage A approval of
the bounded remediation/test seams. Neither a green candidate registry report
nor this proposal resolves the cache finding.

- Resolve and verify an isolated patched marketing candidate; review every changed
  transitive entry against primary fixes and integrity metadata.
- Resolve the cache finding through a focused primary-source/consumer review;
  do not install 4.3.0 merely to escape its reported range or borrow an exception.
- Implement/test the independent web guard and CI/build/release enforcement.
- Stop with exact candidate/scope evidence while the old root scope guard blocks.
- Obtain separate Stage B approval before any scope-pin replacement, then rerun
  fresh checks. No push, merge, production deploy or exposure is authorized here.
