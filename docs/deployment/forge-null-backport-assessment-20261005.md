# Supplemental Forge backport assessment — 2026-10-05

## Outcome and scope

Nathan approved assessing the supplemental Forge fix in isolation, not installing
it into the app or changing audit policy. Source checkpoint:
`d03103619d5473911ea6db095d2df065bd571d3e`, `feat/combined-public-beta`,
[PR #47](https://github.com/NathanN-275/Peso/pull/47).

The candidate rejects every exercised nonempty NULL case and preserves the
tested valid behavior. This supports a separate installation review. It does
not establish safety for every hostile input or clear the release gate.
The app's installed backport, patch manifest, installer, lockfile, package
scripts, audit policy, and workflows remain unchanged. No provider, credential,
database, DNS, push, merge, or deployment operation occurred.

The [preceding review](dependency-audit-treatment-review-20261005.md) reproduced
malformed-encoding acceptance. This assessment independently evaluates the
supplement to the already assessed element-count fix. Only this report and a
reusable assessment harness are added to the repository.

## Immutable provenance and narrow change

- [Forge proposal #1157](https://github.com/digitalbazaar/forge/pull/1157) is open
  and unmerged. It is not an official release or maintainer acceptance.
- Candidate: `itsalexfer/forge` commit
  `683ab3344899cc08a581e4d5675a33e87aff7b04`.
- Parent: `9daa7a6a5542e6e8c82a636ff4d8266117678fc7`;
  queried PR base: `723240415b25120d47146f982809fa69344ab890`.
- The immutable supplemental commit changes `lib/rsa.js` and its RSA tests.
  Its runtime delta is a NULL-content check plus one explanatory comment.
  Compared with the app's current backport, all other 48 library files match.
  The assessed `rsa.js` bytes match the candidate exactly.
- Temporary candidate packages retain published package metadata/version
  `1.4.0`. The upstream source tree's `1.4.1-0` metadata is not adopted or
  represented as a published fix.
- The combined patch was generated against pristine published runtime bytes
  from `forge` source `7a43db987bd0ecdc5b41f6d73f58ba6ca5bf9ae1`. Their hash
  matches the registry-original pin already reviewed in the app manifest.

Temporary working area: `/private/tmp/peso-forge-null-assessment.IIU161`.
It contains isolated baseline/candidate packages, downloaded immutable source,
the exact supplemental and combined patches, and test-only tools. No app
environment files or provider credentials were copied. Fixture RSA private
keys used by the assessment harness exist only in memory and are never saved
or printed. Upstream synthetic fixtures remain outside Git in the temporary
downloaded sources.

## Red-to-green verification

The baseline is the app's currently installed element-count backport, not
unmodified Forge 1.4.0. The original three-case reproducer exited 1 again.
The broader focused harness returned **54 pass, 42 fail** before applying the
supplement. Those failures were missing rejection of nonempty NULL parameters,
not unrelated setup failures. Empty/absent NULL, wrong-digest, extra-child,
native-signature, PSS, and NONE controls passed.

The isolated runtime change then produced:

| Check | Node 20.20.2 | Node 22.23.3 | Node 24.18.0 |
| --- | --- | --- | --- |
| Focused security/compatibility and Expo consumer checks | 102 pass, 0 fail | 102 pass, 0 fail | 102 pass, 0 fail |
| Complete upstream Forge suite against assessed installed-library bytes | 837 pass, 4 pending | 837 pass, 4 pending | 837 pass, 4 pending |

The 102 checks comprise 96 direct RSA checks and six Expo consumer checks:
RSA exponents 3/65537; SHA-1/256/384/512; absent/empty NULL; invalid contents of
1/8/32 bytes including binary zero and `0xff`; extra children; wrong digests;
legacy BER; native-generated signatures; PSS; NONE; actual isolated Forge
resolution by Expo's certificate consumer; certificate creation, validation,
and PEM roundtrip; buffer signing/verification; and wrong-key rejection.
SHA-1 here is a compatibility case, not a recommended signing algorithm.

The same full upstream suite on the baseline returned **836 pass, 4 pending,
1 fail** for nonempty NULL rejection. The candidate's standalone RSA suite
returned **109 pass, 4 pending** on Node 24. All four pending tests concern
deterministic 512-bit key generation across PRNG/sync/async combinations, not
the new NULL tests. No test-focus marker or upstream test was altered.

Full suites used pinned Mocha 11.7.5 with
`--no-config --no-package --forbid-only --reporter dot --timeout 30000` and
`tests/unit/index.js`. Tools were installed only in the temporary directory
with lifecycle scripts disabled. A Mocha dependency emitted a deprecated-glob
warning; it is an isolated test tool, not an app dependency change. Node 22's
suite also emitted an upstream deprecated-Buffer warning.

All runs were local macOS x64. The downloaded Node 20 archive matched the
official Node distribution checksum. Node 22/24 used existing local runtimes.
These results do not claim Linux CI, browser/native E2E, or a production build.

These synthetic signed structures demonstrate invalid-encoding acceptance and
rejection, **not a forgery constructed without a private key**. The causal
finding remains missing captured NULL-content validation. A minimal one-byte
case and the broader original cases go green with the supplement.

## Patch and artifact verification

The full combined patch passed a dry run with `--fuzz=0` against pristine
`lib/rsa.js`, then applied in another temporary copy. Its resulting bytes and
all 49 library files match the tested candidate. The reconstructed copy passed
all 96 direct RSA checks. No hash-pin or verifier bypass was added to the app.

| Artifact | SHA-256 |
| --- | --- |
| Immutable candidate source archive | `38cb03e0722c06946ee55b1597d9c3ffb7c11ea118d2fb08d1da6159aff01762` |
| Current installed `lib/rsa.js` (unchanged) | `acc22e5d36e27832c34e02dd3933aad7977d45b047eead5016520735efedc9c5` |
| Assessed supplemental `lib/rsa.js` | `22cdfb3220439533211cf00ff7c7e6605607761d77a2c3c263411d4c70798c4f` |
| Temporary `forge-supplement.patch` | `4d0c04d4b9a8b7a2828af5f582001583ced63bcde5783d1409737a35718b6de9` |
| Temporary `forge-combined.patch` | `be39d6da41ca04aed6ae697f65000184083b8a4c1b9874ab759fd2cfd4dc70fe` |
| Durable assessment harness | `4f923cedd9a04de3993847837e8845cb949666a9aee6532001e0b74b1db8d191` |
| Isolated test-tool lockfile | `384a19052385595a6be8610f8a53037a5146774c76f28e58de46a85d8a88238a` |
| Node 20.20.2 darwin-x64 archive | `8be6f5e4bb128c82774f8a0b8d7a1cc1365a7977d9657cece0ca647b3fe04e61` |
| Temporary `assessment-inputs.tar.gz` | `8c20ec732b9df5fcc62b2c65989d7d2be288c866bd6cc9afb43442b759fb9a6d` |

The temporary bundle preserves the harness, both patch artifacts, immutable
source archive, Node checksum list, and pinned tool manifests. It is not a
production backup, off-machine copy, or permanent artifact-store claim. The
assessment harness is also committed as
[`evidence/forge-null-assessment.cjs`](evidence/forge-null-assessment.cjs).

From the repository, rerun the saved candidate checks with:

```sh
node docs/deployment/evidence/forge-null-assessment.cjs \
  /private/tmp/peso-forge-null-assessment.IIU161/candidate \
  /private/tmp/peso-forge-null-assessment.IIU161/candidate/node_modules/@expo/code-signing-certificates
```

Omit the consumer argument to run the 96 direct checks. Point the package
argument at `baseline` to reproduce its 42 failures. These temporary paths may
eventually expire; reconstruct packages from the recorded source and patch
inputs rather than assuming a missing directory contains accepted evidence.

## Remaining authority and acceptance

After assessment, app `npm run deps:verify` still passes its original pins,
and unchanged `npm run audit:ci` still exits 1. The supplemental guard is
**not installed** in the app. Forge prebuilt `dist/` bundles remain unpatched
and outside any fixed-artifact claim. Other malformed ASN.1 forms and every
possible hostile input have not been exhaustively proven safe.

Recommend a separate, narrow implementation chunk: replace the existing
Forge patch with the assessed combined patch, update its reviewed file/patch
pins and manifest trust anchor, add installed-public-API NULL regressions, and
repeat installer/verifier tamper tests, clean installs, typecheck, and policy
tests. Retain package identity, fail-closed verification, and the current audit
policy. Nathan's approval is needed before that implementation.

Only afterward reconsider a separately approved, evidence-bound audit-policy
proposal. Linux CI and all deployment gates remain mandatory. This assessment
does not authorize a policy exception, PR merge, deployment, or public launch.
No ADR or glossary edit is warranted by an isolated reversible assessment.
