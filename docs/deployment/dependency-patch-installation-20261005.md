# Verified dependency patch installation — 2026-10-05

## Outcome and authority

Nathan authorized implementation of the assessed backports without changing
the npm audit policy, and confirmed all three TDD interfaces: installer CLI,
read-only verifier CLI, and installed braces/RSA public APIs.

Source checkpoint: `50ff89f9a4859fad4be77e5ec28b830d139110bf` on
`feat/combined-public-beta`, [PR #47](https://github.com/NathanN-275/Peso/pull/47).
This document is committed with the implementation; the resulting Git commit
identifies its exact source. No push, merge, deployment, provider configuration,
credential, database, or DNS change is part of this chunk.

Implementation checks pass locally. **The security gate still fails.**
`npm run audit:ci` exited 1, retaining braces and node-forge and their dependent
chains as unapproved HIGH findings. Versions, registry resolutions, and package
integrities remain unchanged. The lockfile changes only the root install-script
marker. Audit policy, audit tests, security workflow, and secret-scan rules are
unchanged. Keep PR #47 unmerged and deployment/DNS work paused.

## Exact patch inputs

The [prior assessment](dependency-security-blocker-20261004.md) records source
commits, baseline reproduction, and upstream-suite compatibility results.
The repository assets are Peso-maintained backports, not upstream releases.

| Input | SHA-256 |
| --- | --- |
| `patches/dependencies/braces-3.0.3.patch` | `e07abe26dbd330daea0e448ca1382327322dd5eccc08c5dd1a9b9f7bf5a6d699` |
| `patches/dependencies/node-forge-1.4.0.patch` | `f4ab98b30a7b6997e80c810a8f2fd90dad534c734228ad9273199b382d5fbda2` |
| `patches/dependencies/manifest.json` | `c3e2975b689679011555bbbc1c2025412369c4218d9b16790891b51fd1af93c3` |

The manifest pins the exact package locations, versions, resolution/integrity,
patch hashes, and original/patched hashes of all 69 installed package files.
Its trust anchor is embedded in `scripts/dependency-patches.js`. Both packages
are validated and their diffs computed before any package write. Application
uses exact patch context and verifies the resulting bytes, without downloading
patches or depending on an external patch executable.

Root postinstall applies the patches. `npm run deps:verify` verifies read-only.
App start/export/typecheck/policy commands verify explicitly; the combined web
builder and release checker also verify first. Fully patched installs are
idempotent. Missing assets/files, altered bytes or manifest, unexpected package
inventory or nested copies, symlinks, lockfile identity changes, and partial
patches fail closed. A partial installation requires a fresh install.

## Verification evidence

TDD first reproduced missing installer/verifier behavior and the two installed
public-API defects, then verified the implementation. Security fixtures generate
RSA keys only in memory. They test malformed DigestAlgorithm acceptance, not a
complete no-private-key forgery. Brace checks cover bounded nesting, direct AST
walkers, parent cycles with VM timeouts, and ordinary published behavior.

| Check | Result |
| --- | --- |
| Workspace patch verification and typecheck | Pass |
| Workspace policy suite | 251 pass, 0 fail |
| New installer/verifier CLI tests | 17 pass |
| New installed braces/RSA API tests | 11 pass |
| Fresh ordinary install, Node 24.18.0 / npm 12.0.2 | 610 packages; automatic apply and readback verification pass |
| Fresh-install verification, typecheck, policy suite on Node 24 | Pass; 251 tests, 0 fail |
| Fresh `npm ci --ignore-scripts` | Installs original packages, as expected |
| Verifier, lifecycle-disabled typecheck, direct web builder, direct release checker after skipped scripts | Each exits 1 for missing patch before proceeding |
| Ordinary `npm ci` after skipped-script installation | Reapplies both patches and verifies successfully |
| Unchanged `npm run audit:ci` | Exit 1; security gate remains blocked |
| Gitleaks 8.30.1: patch assets and each new script | Pass, no findings |
| Git source whitespace check | Pass; patch-context treatment described below |

Clean installs used `/private/tmp/peso-clean-install.VkT70D`, a source-only copy
without environment files, ignored credentials, existing dependencies, or Git
data. An initial incomplete source copy failed before installation; that test
setup was corrected. A Node 22.12.0 / npm 10.9.0 install and suite also passed,
but produced dependency engine warnings; the supported Node 24 rerun above is
the accepted local clean-install result. npm 12 reported an existing blocked
`fsevents@2.3.2` install script; no permission was broadened and root postinstall
still ran successfully.

A broader `gitleaks dir scripts` scan exited 1 for the existing Render API
service ID fixture at `scripts/release-env.test.js:214`. Inspection confirmed a
provider identifier, not a credential, in unchanged code. This is not a clean
full-directory scan claim; no scanner suppression was added. Changed files and
both evidence documents are scanned separately before committing.

The exact upstream diff artifacts include a space on blank context lines,
which an unscoped Git whitespace check flags. `.gitattributes` disables only
blank-at-end-of-line checks for these two hash-pinned patch paths. It preserves
their assessed bytes and leaves normal source checks and all security rules
unchanged. The staged diff is checked with these narrowly scoped attributes.

## Remaining release requirements

Forge prebuilt `dist/` bundles remain original, pinned upstream bytes and are
not fixed artifacts; only the assessed `lib/rsa.js` path is patched. Direct tool
invocations outside guarded commands are not covered. These tests do not prove
all hostile inputs safe, Linux CI, browser/native E2E, or a full production build.
Production-build acceptance and release bindings remain mandatory later.

Next: separately review evidence-bound audit treatment with Nathan before any
policy change, then run Linux CI and required application acceptance. Passing
patch verification does not authorize suppressing the registry findings or
advancing the failed deployment gate. Prefer official patched releases to
retire the temporary backports after security and compatibility verification.
