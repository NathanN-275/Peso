# Dependency audit treatment review — 2026-10-05

## Decision: hold; no policy change recommended yet

Reviewed source: `1a508a132428773ef49bd4c5cb4c58ca1d83067f` on
`feat/combined-public-beta`, [PR #47](https://github.com/NathanN-275/Peso/pull/47).
Nathan requested the next step after verified patch installation: review
evidence-bound audit treatment before any separately approved policy change.

The review reproduced a further Forge malformed-encoding case not rejected by
the installed backport. Do not accept that backport as complete remediation or
add an audit exception now. PR #47 remains unmerged; deployment and DNS remain
paused. No application, patch, manifest, audit policy, workflow, provider,
credential, database, or domain configuration changed during this review.

## Registry and audit facts

`npm view braces version` returned `3.0.3`; `npm view node-forge version`
returned `1.4.0`. Both current advisory pages list no patched version:
[braces GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
and [Forge GHSA-86w9-cpqp-85rv](https://github.com/advisories/GHSA-86w9-cpqp-85rv).
The [brace proposal](https://github.com/micromatch/braces/pull/72) is closed,
while [Forge #1152](https://github.com/digitalbazaar/forge/pull/1152) remains open.
Neither is an official patched release.

npm documents that its bulk advisory request uses package names and versions,
and that it derives parent-package meta-vulnerabilities from dependencies.
Therefore unchanged versions can remain reported even after installed source
bytes change. That explains the audit result; it does not authorize an
exception. [npm audit documentation](https://docs.npmjs.com/cli/v11/commands/npm-audit/).

Current concrete registry advisory leaves:

| Package/path | Advisory | Registry source ID | Leaf severity/range |
| --- | --- | --- | --- |
| `braces` / `node_modules/braces` | GHSA-vfj7-8cjw-p6xm | 1240992 | high / `<=3.0.3` |
| `node-forge` / `node_modules/node-forge` | GHSA-86w9-cpqp-85rv | 1240912 | high / `<=1.4.0` |

`npm run audit:ci` still exited 1 with these roots and dependent chains blocked.
No raw finding was suppressed. The existing audit and installed-patch suites
passed together: 45 tests, 0 failures. These passing tests did not cover the
additional case below.

## New coverage gap and diagnosis

[Forge #1157](https://github.com/digitalbazaar/forge/pull/1157) proposes a
supplement to #1152 for nonempty ASN.1 NULL parameters. It is an unmerged
proposal, not accepted remediation. Its
[runtime diff](https://github.com/digitalbazaar/forge/pull/1157/files) adds a
content check missing from Peso's current `lib/rsa.js` backport.

Independent local diagnostic, Node 24.18.0: NULL contents of 1, 8, and 32 bytes
were accepted by the actual installed RSA public verifier. Absent/empty NULL
controls were accepted, changed digests rejected, and extra child elements
rejected as intended by the existing patch. These are synthetic signatures
made with a fixture private key generated only in memory. They reproduce
malformed-encoding acceptance, **not forgery without a private key**. No new CVE
or deployed exploitability is claimed.

Ranked hypotheses were a missing NULL-content guard, parser normalization of
contents, or the wrong installed copy. ASN.1 roundtrip preserved the invalid
byte. Both Expo certificate and iOS signing consumers resolve the root
`node-forge/lib/index.js`; importing the certificate consumer loads
`lib/rsa.js`, not the prebuilt bundles. Source import searches found no direct
Forge/braces references in `src`, `lib`, `web`, or `dashboard` (excluding locks).
This is current path evidence, not proof of every production/native bundle.

A one-variable in-memory diagnostic added only the NULL-content guard to the
installed RSA source before compiling it inside that short-lived process.
It rejected the one-byte malformed case and retained the empty-NULL control.
Disk bytes were unchanged, and `npm run deps:verify` still passed afterward.
Cause: the current verifier checks the nested element count but not captured
NULL contents. This counterfactual is not an installed fix or compatibility
acceptance; the additional patch still needs an isolated assessment.

### Reproduce without modifying source or writing keys

Run from the repository after `npm run deps:verify`. Expected exit is 1 while
the current backport accepts the three malformed cases.

```sh
node <<'NODE'
const assert = require('node:assert/strict');
const forge = require('node-forge');
const { generateKeyPairSync } = require('node:crypto');
// Deliberately small synthetic regression key, never a production credential.
const keys = generateKeyPairSync('rsa', {
  modulusLength: 1024, publicExponent: 3,
  privateKeyEncoding: { type: 'pkcs1', format: 'pem' },
  publicKeyEncoding: { type: 'pkcs1', format: 'pem' },
});
const priv = forge.pki.privateKeyFromPem(keys.privateKey);
const pub = forge.pki.publicKeyFromPem(keys.publicKey);
const a = forge.asn1, U = a.Class.UNIVERSAL, T = a.Type;
const digest = forge.md.sha256.create().update('Peso NULL review').digest().getBytes();
function signature(parameters, extra = false) {
  const algorithm = [a.create(U, T.OID, false,
    a.oidToDer(forge.pki.oids.sha256).getBytes())];
  if (parameters !== undefined) algorithm.push(a.create(U, T.NULL, false, parameters));
  if (extra) algorithm.push(a.create(U, T.OCTETSTRING, false, 'extra'));
  const info = a.create(U, T.SEQUENCE, true, [
    a.create(U, T.SEQUENCE, true, algorithm),
    a.create(U, T.OCTETSTRING, false, digest),
  ]);
  return priv.sign(a.toDer(info).getBytes(), 'NONE');
}
let failures = 0;
for (const length of [0, 1, 8, 32]) {
  const sig = signature('x'.repeat(length));
  let accepted = false;
  try { accepted = pub.verify(digest, sig); } catch {}
  console.log(`NULL bytes=${length} accepted=${accepted} expected=${length === 0}`);
  if (accepted !== (length === 0)) failures++;
  assert.equal(pub.verify('y'.repeat(digest.length), sig), false);
}
assert.equal(pub.verify(digest, signature(undefined)), true);
assert.throws(() => pub.verify(digest, signature('', true)),
  /valid RSASSA-PKCS1-v1_5 DigestInfo/);
console.log(`Malformed NULL cases still accepted: ${failures}; controls passed.`);
process.exitCode = failures ? 1 : 0;
NODE
```

## Requirements for a later policy proposal, not implemented approval

After complete backport assessment, any proposed temporary treatment must:

- Verify exact installed bytes, manifest/patch pins, package identities and paths
  within the audit invocation itself, not trust a prior step or caller boolean.
- Match only reviewed advisory leaves and metadata; fail closed for other
  HIGH/CRITICAL causes, missing evidence, changed packages, malformed reports,
  dangling/cyclic chains without concrete evidence, and expired decisions.
- Evaluate every relevant cause in parent chains; never blanket-allow Expo,
  Metro, or other parent names merely because one dependency is mitigated.
- Retain the complete raw registry report and distinguish a project-policy
  decision from a clean registry audit. Never claim that upstream versions are
  patched, all HIGH findings disappeared, or scanners agree automatically.
- Have Nathan approve exact scope, expiry, and retirement conditions before
  policy implementation. Prefer a short, explicit review window and official
  releases for retirement; do not silently renew.
- Keep unpatched Forge `dist/` artifacts outside any fixed-artifact claim and
  verify consumer/build paths. Linux CI, full builds, native/browser acceptance,
  and production release bindings remain independent mandatory checks.

The research skill produced a separate
[VEX scope note](dependency-backport-vex-research-20261005.md). It clarifies
artifact-specific claims, but issues no VEX statement or release approval.
This review records an unresolved remediation gap and does not rely on a
`not_affected` claim to clear it.

Next requested authority: assess the supplemental Forge guard in isolation,
then propose its regression tests and compatibility evidence. Do not implement
an audit exception as the next action. No ADR or glossary edit is needed for
this diagnostic note; no deployment decision has been accepted.
