# Supplemental Forge backport installation — 2026-10-05

## Outcome and authority

Nathan approved installing the assessed supplemental Forge fix and updating
its integrity pins, **keeping audit policy unchanged**. Source checkpoint:
`a8a2be1e9978693ab965cdf0dcd70d1b660b016f`, branch
`feat/combined-public-beta`, [PR #47](https://github.com/NathanN-275/Peso/pull/47).

The installed Forge library now rejects nonempty ASN.1 NULL parameters while
preserving the tested valid RSA behavior. Clean installs, integrity checks,
typecheck, and policy tests pass. The unchanged npm audit still exits 1:
**the release security gate remains blocked**. This chunk does not approve
an audit exception, merge, deployment, or public launch.

No package identity, version, lockfile, npm script, audit policy, workflow,
credential, provider, database, DNS, or public-visibility setting changed.
Unrelated deployment notes were preserved. No push or merge was performed.

## Exact implementation

The Forge patch is byte-for-byte the combined artifact evaluated in the
[supplemental assessment](forge-null-backport-assessment-20261005.md). It keeps
the nested DigestAlgorithm element-count validation from proposal
[#1152](https://github.com/digitalbazaar/forge/pull/1152) and adds the NULL-content
guard from proposal [#1157](https://github.com/digitalbazaar/forge/pull/1157),
at assessed commit `683ab3344899cc08a581e4d5675a33e87aff7b04`.
This remains a Peso-maintained backport, not an official patched release.

Only Forge provenance, the patch hash, and the patched `lib/rsa.js` hash changed
in the manifest. Its installer trust anchor was updated accordingly; installer
and verifier behavior were not weakened. All other manifest entries, including
registry resolution/integrity and original file hashes, are unchanged. The
braces patch is unchanged. Verification still covers all 69 installed files.

| Artifact | SHA-256 |
| --- | --- |
| Combined Forge patch | `be39d6da41ca04aed6ae697f65000184083b8a4c1b9874ab759fd2cfd4dc70fe` |
| Installed Forge `lib/rsa.js` | `22cdfb3220439533211cf00ff7c7e6605607761d77a2c3c263411d4c70798c4f` |
| Manifest and installer trust anchor | `1bae92dd0779b9cd026754c599c47508fd49f36a36c2c3decf07325f6728b6b0` |
| Unchanged braces patch | `e07abe26dbd330daea0e448ca1382327322dd5eccc08c5dd1a9b9f7bf5a6d699` |
| Former element-count-only Forge `lib/rsa.js` | `acc22e5d36e27832c34e02dd3933aad7977d45b047eead5016520735efedc9c5` |

All 49 installed Forge library files match the assessed candidate. Its prebuilt
`dist/` bundles remain original, hash-pinned **unpatched** bytes; they are not
fixed artifacts. Package metadata remains `node-forge@1.4.0`.

## Red-to-green and integrity evidence

TDD used Nathan's approved installer CLI, verifier CLI, and installed public
RSA interfaces. The nonempty-NULL regression was run before replacing the
patch: exit 1, missing expected rejection. After updating the pins, verification
of the old installed patch also failed as intended. A clean root `npm ci`
applied both verified patches; the RSA regression then passed.

The durable installed-package suite now has 17 checks, including absent/empty
NULL, nonempty 1/8/32-byte and binary contents, exponents 3/65537, legacy BER,
native signatures, wrong digests, PSS, NONE, and existing brace protections.
The 18 installer/verifier checks include a new fault-injection regression
reconstructing the exact former Forge bytes. Both CLI modes reject those bytes
without rewriting them. Existing tamper, inventory, symlink, partial-install,
lockfile, lifecycle, and explicit preflight checks remain passing.

Do not layer this update onto the old installed backport. Run `npm ci` from
the unchanged lockfile; refusal of old bytes is intentional fail-closed behavior.

## Verification results

All checks below ran on local macOS x64 against actual installed packages:

| Check | Node 20.20.2 | Node 22.23.3 | Node 24.18.0 |
| --- | --- | --- | --- |
| Installer/verifier and installed-package tests | 35 pass, 0 fail | 35 pass, 0 fail | 35 pass, 0 fail |
| Saved RSA/Expo assessment harness | 102 pass, 0 fail | 102 pass, 0 fail | 102 pass, 0 fail |

The 102 checks use the committed
[`evidence/forge-null-assessment.cjs`](evidence/forge-null-assessment.cjs) and
the app's actual installed Forge and Expo certificate consumer. Synthetic
private keys exist only in memory. These demonstrate malformed-encoding
rejection, **not a forgery constructed without a private key**.

The workspace and a separate source-only clean installation both passed on
Node 24.18.0 / npm 12.0.2:

- `npm ci --no-audit --no-fund`: exit 0, 610 packages; postinstall applied both
  patches and verified their bytes.
- `npm run deps:verify`: exit 0.
- `npm run typecheck`: exit 0.
- `npm run test:policy`: 258 pass, 0 fail, no skipped tests.

The isolated copy at `/private/tmp/peso-forge-supplement-install.5v11e3` contains
622 tracked regular source files with current changes. Git metadata, environment
files, existing `node_modules`, and untracked deployment notes were not copied.
Its fresh install used the unchanged lockfile and a temporary npm download cache.
Existing UUID deprecation and blocked `fsevents@2.3.2` lifecycle warnings remain;
no lifecycle allowance was broadened. Temporary files are not a production
backup or a permanent off-machine evidence store.

`git diff --check` passed. Gitleaks 8.30.1 scanned each of this chunk's seven
changed files with redacted output: all exited 0 with no leaks found. This is
a changed-file check, not a full-history secret-remediation claim.

The prior isolated assessment's full upstream suite results remain recorded
in that report; they were not rerun as full suites in this installation chunk.
No Linux CI, browser/native E2E, or production-build acceptance is claimed here.
The production release binding and remaining deployment gates stay mandatory.

## Remaining blocker and next chunk

`npm run audit:ci` returned a usable advisory report and exited 1, listing 24
blocking high-severity package entries, including braces, Forge, and dependent
Expo/Metro/React Native/Tailwind chains. Backported bytes do not change npm's
version-based advisory classification. Existing allowances are untouched.

Next: separately review whether evidence-bound audit treatment is justified,
including the unpatched Forge bundles and consumer scope. Nathan's explicit
approval is required before any policy change. Do not treat successful local
tests as a release-gate pass or proceed to deployment on this evidence alone.
No domain-term change or hard-to-reverse deployment decision was made, so
neither `CONTEXT.md` nor an ADR was changed.
