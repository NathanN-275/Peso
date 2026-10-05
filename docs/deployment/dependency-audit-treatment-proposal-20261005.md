# Evidence-bound audit treatment proposal — 2026-10-05

## Decision: conditional implementation candidate, not an active exception

Nathan authorized the separate audit-policy review following supplemental
Forge installation. Reviewed source:
`75e1e31b197397413f3e4254440021ff908b4dbb`, `feat/combined-public-beta`.
The [installed-patch evidence](forge-null-backport-installation-20261005.md)
supports proposing a narrow temporary treatment of two exact advisories.
It does not justify adding two URL-only allowances to the current evaluator.

No audit policy, dependency, installer, application code, workflow, provider,
credential, database, DNS, or release configuration changed in this review.
No push, merge, deploy, or public-visibility action was performed. The current
gate remains **blocked**. Nathan must approve the scope and expiry below before
implementation. Implementation safeguards must pass before treatment activates;
the separate release-acceptance conditions remain mandatory afterward.

## Current primary-source boundary

The research skill's background
[primary-source recheck](dependency-audit-primary-source-recheck-20261005.md)
observed registry maxima `braces@3.0.3` and `node-forge@1.4.0`, with neither
advisory identifying a patched version. Braces proposal #72 is closed without
merge; Forge #1152/#1157 are open and unmerged at that observation. Local
patches are not official releases or demonstrated maintainer acceptance.

Official [npm audit documentation](https://docs.npmjs.com/cli/v11/commands/npm-audit/)
describes package/version advisory matching and derived meta-vulnerabilities.
Continued registry findings are compatible with changed installed bytes; they
do not certify those bytes. The recheck records retrieval times and links to
registry/GitHub APIs. Its VEX discussion informed the artifact exclusions here;
neither note issues a VEX statement or declares the entire package unaffected.

## Local registry evidence

A fresh `npm audit --json --audit-level=high --fetch-retries=0
--fetch-timeout=20000` returned a usable version-2 report, exit 1. Raw metadata:
23 high, 0 critical, 7 moderate, 1 low. The unchanged project evaluator returns
22 blocking high-severity package entries, including both reviewed roots.
All high-severity direct leaves in this snapshot are the two proposed leaves
and the two already-treated image-size leaves. Each currently blocked high
chain reaches braces and/or Forge; no parent-package blanket allowance is needed.

| Proposed leaf | Exact installed path/version | Registry metadata to bind |
| --- | --- | --- |
| [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) | `node_modules/braces`, `3.0.3` | source `1240992`; name/dependency `braces`; severity `high`; range `<=3.0.3` |
| [GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv) | `node_modules/node-forge`, `1.4.0` | source `1240912`; name/dependency `node-forge`; severity `high`; range `<=1.4.0` |

The complete raw report is preserved outside Git at
`/private/tmp/peso-audit-policy-review.NiAsQh/npm-audit.json`, SHA-256
`26ffb749105190d83b86f039e6cb547e5975ca0959d92ec2e6a6e4389affc561`.
This temporary copy is not durable CI evidence or an off-machine backup.
The preceding installation note's 24 blockers and this snapshot's 22 are
different registry observations, not a claim that changing source bytes
automatically clears version-based findings. Never use a finding count as an
allowance condition; inspect every cause in each fresh report.

Reviewed audit-script SHA-256:
`ddbc18bdb29fde1f833883bb56fc9617aca10be2d7e0088e35b1917893761bde`.
Reviewed root lockfile SHA-256:
`0fe09a3b2fff880383d9e6bf098fbf7218145a96c78633db71cc9f89e778fc9c`.
Both remain unchanged. Exact package registry resolution/integrity, patch
hashes, all 69 installed-file pins, and the manifest trust anchor are recorded
in the installation note and `patches/dependencies/manifest.json`.

## Consumer scope and excluded artifacts

Installed JavaScript source search, excluding Forge's own package, found
Forge references only in Expo's certificate consumer, its tests, and the
Expo CLI iOS signing consumer. Their package-relative resolution reaches
`node_modules/node-forge/lib/index.js`. Loading the certificate consumer
loads `lib/rsa.js` and no Forge `dist/` modules. Micromatch explicitly imports
`braces`, resolving to the pinned root copy. Forge package `main` is
`lib/index.js`; its `browser` map does not select the prebuilt bundles.
No direct Forge/braces imports were found in `src`, `lib`, `web`, `dashboard`,
or `metro.config.js` in this source checkpoint.

This is local source/resolution evidence, not complete bundle or deployed
execution-path proof. Forge's `dist/forge.min.js` and `dist/forge.all.min.js`
remain unpatched. All six `dist/` assets are unchanged and hash-pinned; no
package-wide `fixed` or `not_affected` VEX statement is issued. A new Forge
consumer or prebuilt-bundle use invalidates this scope and requires review.
Production artifact inspection must prove that excluded unpatched bundles
are not shipped or executed before release acceptance. Preserve separate
artifact-digest evidence; local tests cannot substitute for it.

## Evaluator gap discovered without changing code

The current recursion returns success when revisiting a node and accumulates
allowed-advisory evidence across sibling paths. A synthetic `parent` with
causes `[allowed-leaf, cycle-a]`, and the detached cycle
`cycle-a -> cycle-b -> cycle-a`, is omitted from blockers. The cycle nodes
themselves remain blocked, so this is **not a reproduced full-CLI bypass**.
A dangling dependency control still blocks. Existing tests reject standalone
advisory-free cycles but do not cover this mixed parent case.

Before expanding treatment, evaluate every relevant graph branch. Cyclic
Metro chains with verified concrete leaves must remain usable, but an
advisory-free strongly connected component must not borrow evidence from a
sibling. Use an explicit graph/SCC or equivalent sound analysis, not a global
counter plus unconditional recursion success. Reject dangling causes and
malformed/unknown metadata, even alongside an allowed leaf.

## Proposed approval scope and expiry

Recommendation: approve an implementation chunk with these strict conditions,
not an immediate scanner suppression. Proposed owner: Nathan. Proposed absolute
expiry: **2026-10-12T23:59:59Z**, with no automatic renewal. If implementation
is not accepted before that time, the treatment cannot activate. Any renewal
requires a fresh review and explicit approval.

1. The audit command itself runs read-only installed-patch verification before
   considering treatment. Do not trust an earlier step, caller boolean, or
   externally supplied assertion. Require the reviewed manifest trust anchor,
   both patch hashes, exact inventory, package paths and registry identities.
   Changed, missing, partial, old, extra, or symlinked copies block.
2. Match only the two exact advisory leaves above, including source ID,
   name/dependency, URL, severity and range, at the reviewed package paths and
   versions. Preserve registry integrity and the reviewed lockfile binding.
   Changed metadata or any new HIGH/CRITICAL cause blocks; do not generalize
   an allowance to a package, title, parent name, or all transitive findings.
3. Harden graph/report handling first. Every relevant cause must be justified;
   unknown severities, malformed nodes/causes, inconsistent package identities,
   dangling references, advisory-free branches/cycles, and expired decisions
   block. Preserve valid reviewed Metro cycles with concrete leaf evidence.
4. Preserve the complete raw audit report as a CI artifact on success and
   failure, with checksum, source commit, manifest/patch hashes, and decision
   expiry. Label the outcome **project policy accepted with verified temporary
   backports**, never “clean registry audit” or “zero HIGH findings.” Existing
   unrelated allowances remain separate and are not broadened.
5. Use TDD at the public audit evaluator and audit CLI boundaries. Reproduce
   the mixed-cycle gap before hardening; cover changed metadata, a new advisory
   alongside an allowed one, disconnected/dangling causes, tampered installs,
   skipped lifecycle hooks, expiry boundary, raw-report retention, and registry
   failure. Rerun clean installs, integrity checks, typecheck, policy tests,
   and installed-public-API security/compatibility checks.
6. Do not accept release until Linux CI runs against the final approved source,
   full builds and artifact exclusions are verified, production inputs match,
   and remaining deployment gates pass. An exception enables evidence collection;
   it does not waive build, auth, recovery, migration, release, or launch gates.

Retire treatment when official patched versions can be installed and verified.
Block immediately on expiry, altered evidence/scope, or a new relevant defect.
Do not silently reclassify unpatched bundles or renew dates to keep CI green.

## Verification and next chunk

`npm run deps:verify` passed. The combined unchanged audit, installer/verifier,
and installed-package suites passed: **52 tests, 0 failures, no skips**.
The graph-gap diagnostic confirmed both the parent omission and continuing
full-report blockers; no source or package bytes were altered for the check.
Gitleaks 8.30.1 checked both new review documents with redacted output and found
no leaks; `git diff --check` passed. This is not a full-history secret scan.

Read-only GitHub inspection found [PR #47](https://github.com/NathanN-275/Peso/pull/47)
open, targeting `main`, at remote head
`50ff89f9a4859fad4be77e5ec28b830d139110bf`. Its frontend-security check failed;
other passing checks at that older head do not validate local source
`75e1e31b197397413f3e4254440021ff908b4dbb`. Skipped production-release-source and
staging-migration checks are not passes. No check was rerun or PR state changed.

Next authority needed: Nathan's approval of the exact scope and expiry before
TDD implementation. Keep the release gate blocked until the implementation's
acceptance conditions pass. This is a reversible proposal, not an accepted
deployment decision; no ADR or `CONTEXT.md` change is warranted.
