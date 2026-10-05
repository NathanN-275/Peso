# Pinned dependency backports

These are Peso-maintained security-only backports, not upstream releases.
Package names and versions remain unchanged. This directory does not grant
an npm audit allowance or release approval.

- `braces-3.0.3.patch`: five security-only library diffs from upstream proposal
  [#72](https://github.com/micromatch/braces/pull/72), pinned to
  `28d440b5dd449dbf1fe6f3506cf94ecca4d02660`. Unreleased parser behavior from
  the proposal's base is excluded. The proposal was closed without merging
  by the 2026-10-05 recheck.
- `node-forge-1.4.0.patch`: the combined nested DigestAlgorithm element-count
  and NULL-content validation changes from proposals
  [#1152](https://github.com/digitalbazaar/forge/pull/1152) and
  [#1157](https://github.com/digitalbazaar/forge/pull/1157), pinned to the
  assessed combined runtime at `683ab3344899cc08a581e4d5675a33e87aff7b04`.

The brace patch hash matches the
[initial assessment](../../docs/deployment/dependency-security-blocker-20261004.md);
the combined Forge patch hash matches the
[supplemental assessment](../../docs/deployment/forge-null-backport-assessment-20261005.md).
`manifest.json`
pins the registry resolution and integrity, expected package path/version,
patch hashes, and original/patched hashes of every installed package file.

## Installation and verification

Root `npm ci` runs `scripts/dependency-patches.js apply` through postinstall.
The installer uses only Node built-ins and repository patch assets; it does
not download patches or invoke an external patch executable. It verifies
both packages before writing either, applies exact-context diffs, and checks
the resulting bytes. Reapplying fully verified patches changes no bytes.

`npm run deps:verify` performs read-only verification. Both commands check
the manifest against the SHA-256 trust anchor in the installer, the lockfile's
version/resolution/integrity and package locations, patch hashes, and the exact
inventory and bytes of all 69 installed files. Missing, altered, partially
patched, symlinked, or unexpected copies fail. An interrupted partial install
must be repaired with a clean install, not automatically accepted. The prior
element-count-only Forge backport is also rejected; run `npm ci` after this
patch update rather than attempting to layer a new patch on old installed bytes.

App start/export/typecheck/policy-test commands verify explicitly, including
when npm lifecycle hooks are disabled. The combined web builder and release
checker also verify before their other work. Directly invoking unrelated tools
outside these commands is not protected by this integration.

Regression tests cover the installer CLI, verifier CLI, and actual installed
brace/RSA public APIs. See the dated
[initial implementation evidence](../../docs/deployment/dependency-patch-installation-20261005.md)
and [supplemental installation evidence](../../docs/deployment/forge-null-backport-installation-20261005.md).

## Limits and retirement

Forge's prebuilt `dist/` bundles remain original, hash-pinned upstream bytes;
only its `lib/rsa.js` consumer path is patched. Do not use those prebuilt
bundles as fixed artifacts. These checks do not establish Linux CI, native or
browser end-to-end acceptance, complete application-build compatibility, or
safety for every hostile input. The original upstream licenses remain in the
installed packages (braces MIT, forge BSD-3-Clause OR GPL-2.0).

The release audit and its existing policy remain unchanged and blocking.
Any evidence-bound audit treatment needs separate review and Nathan's
approval. Replace these temporary backports with official patched releases
when available, updating/removing the manifest, installer hooks, and related
tests together after compatibility and security verification.
