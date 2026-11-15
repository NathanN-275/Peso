# Pinned dependency security and compatibility patches

Braces retains its reviewed Peso security backport. Metro has one
API compatibility adapter so it can use the official fixed image-size release.
This directory grants no npm audit allowance or release approval.

- `braces-3.0.3.patch`: five library diffs from upstream proposal
  [#72](https://github.com/micromatch/braces/pull/72), commit
  `28d440b5dd449dbf1fe6f3506cf94ecca4d02660`. Unreleased parser behavior
  is excluded; the proposal was closed without merging by the October 5 recheck.
- `metro-0.84.4-image-size-2.patch`: one-file compatibility adapter in
  `src/Assets.js`. Synchronous `getAssetSize` and zip-marked input keep the
  image-size buffer API. Asynchronous regular filenames use the official
  `image-size/fromFile` `imageSizeFromFile` API, including its 512 KiB prefix cap.
  The scoped `metro -> image-size:2.0.4` override deliberately crosses Metro's
  declared 1.x range. It changes no other Metro behavior or package version.

The old image-size 1.2.1 local parser backport is retired. Official image-size
2.0.4 is installed without local package edits; unused queue 6.0.2 leaves the
lock. The scoped Expo CLI Zod override remains unchanged.

## Installation and verification

Root `npm ci` applies these patches through `scripts/dependency-patches.js`
postinstall. Its Node-builtins-only installer validates every package before
writing any patch and applies exact-context diffs. Reapplying fully verified
patches changes no bytes. `npm run deps:verify` verifies without writes.

The manifest SHA256 anchor, registry lock version/resolution/SRI, expected
package locations, patch hashes and every original/patched file are checked.
The remaining patch inventory is **533 files**: Braces 10 and Metro 523. Only
Metro `src/Assets.js` changes in the compatibility adapter. Missing, altered,
partial, symlinked or unexpected package copies fail. Scoped package names
are compared in full, so `@expo/metro` is distinct from `metro`; a nested
unscoped Metro copy remains rejected. Interrupted partial installation and the
retired Forge backport require a clean reinstall.

App start/export/typecheck/policy-test and release checks retain explicit
verification boundaries. Direct unrelated tool invocation is outside those
boundaries. Installer regressions cover the remaining Braces and Metro patches, including
corrupted applied bytes, partial installation, all-before-write validation and
scoped-name/nested-copy cases.
Eight Metro API regressions cover sync buffers, async filenames, bounded file
reads, scale/platform metadata, zip-marked buffer paths, malformed inputs and
asset plugins. The zip-marked fixture exercises Metro's branch in an owned
ordinary directory; it does not emulate a zip virtual filesystem.

## Limits and retirement

Official node-forge 1.4.2 replaces the local Forge backport. The maintainer
[advisory](https://github.com/digitalbazaar/forge/security/advisories/GHSA-2g46-22mc-6gwp)
lists 1.4.1 as the fix for CVE-2026-85393; 1.4.2 also restores PEM Buffer-input
compatibility. Its canonical DER comparison intentionally rejects noncanonical
BER DigestInfo encodings. No Forge package file is locally patched; npm's
lockfile pins the official package URL and SRI. Exact installed-package hashes
against the official tarball and compatibility/security results are captured
in the release evidence. These checks do not establish hosted, browser, native
or public launch acceptance. Original upstream licenses remain included.

The historical root treatment expired at `2026-10-12T23:59:59Z` and was never
renewed. After official dependency remediation produced a fresh raw audit with
zero HIGH and CRITICAL findings, the root guard retired every allowance and
backport capability, its expiry and its consumer-scope freeze. Both root and
web guards reject every HIGH or CRITICAL, including former exact exception
records. Valid lower findings remain visible below the unchanged HIGH threshold.

Root audit pins the current lock, verifier, manifest and both remaining patch
artifacts, then verifies the physical installed patch tree. Malformed report,
identity, cause, severity or graph data fail closed. Bounded retries, source
provenance, symlink protections and retained raw/decision evidence remain.
See [root audit retirement](../../docs/deployment/root-audit-retirement-20261027.md)
for the scope and limits. This directory still grants no release approval.

Replace remaining temporary backports with compatible official fixed releases
when established. Retire the Metro adapter when upstream Metro supports the
2.x file API, after equivalent buffer/file/zip/export checks.
