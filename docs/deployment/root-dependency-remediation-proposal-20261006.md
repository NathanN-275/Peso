# Root dependency remediation — bounded proposal

For Nathan, 2026-10-06 America/New_York. **Proposal only; not approved or
implemented. Gate 2/security revalidation remains FAIL.** The research skill
separated primary-source review from the main agent's locked-parent and installed
consumer tracing. Its [primary-source note](root-dependency-primary-source-review-20261006.md)
records official advisories, owning fixes, registry identities, tarball hashes,
integrities, signatures, and compatibility uncertainties.

## Exact baseline and retained failures

Inspected source: `80bab91d42bd79f00086b3453d79497e06c842e7`, tree
`7a5ccd7d31d59195c46a1e698145299516eebe88`, branch
`fix/merged-source-secret-coverage`. No source/dependency change in this chunk.
The five pre-existing untracked deployment notes remain preserved and excluded.
Only these two new research/proposal notes are intended for a local docs commit.

| Unchanged input | SHA-256 |
| --- | --- |
| `package.json` | `b2d4529630721b93c4bc3123828471bd0e0bed9880ac9632b68014529a6b67ff` |
| `package-lock.json` | `0fe09a3b2fff880383d9e6bf098fbf7218145a96c78633db71cc9f89e778fc9c` |
| `scripts/npm-audit-ci.js` | `672b8aa5daa03bf35ed06c8eed761c9a2cd95516c2a9bc3b858e87f093ed7170` |
| `scripts/dependency-patches.js` | `9df792cf971d23fc2500471e93d9b66fb40070f9df441ab45144efea63030ff9` |
| `patches/dependencies/manifest.json` | `1bae92dd0779b9cd026754c599c47508fd49f36a36c2c3decf07325f6728b6b0` |

The main agent recomputed both retained report/decision checksums in this chunk;
they match the commit-bound ignored receipt. No fresh registry audit was run.
Raw reports remain ignored/outside Git, not protected backups or hosted evidence.

| Audit at the baseline SHA | Raw findings / result | Report SHA-256 | Decision SHA-256 |
| --- | --- | --- | --- |
| Root, `artifacts/npm-audit/run-Fcxyt2` | 25 HIGH, 8 MODERATE, 0 CRITICAL; raw/gate exit 1 | `d50bb04c1a745d257b5acf9e17b8c9a955c4735c5974f4491d25f04e6afad6e8` | `0f1e005ee874238e8981752381805260fd01b6484059c2fc87a754219356906b` |
| Web, `artifacts/npm-audit-web/run-yzxH6V` | 7 HIGH, 1 CRITICAL, 1 MODERATE; raw/gate exit 1 | `1d19ca0390c2859f076fb73bcb27e5899559c64d7bab9c7c1eb2ed19aae03a35` | `433dbdf35dc8642a9039d320f6bd536dd442a49fda85dbc2c587f7523d17ec06` |

Earlier root report `run-lJe3VQ` had 27 HIGH/8 MODERATE with identical concrete
advisory tuples; the later registry response omits two propagated parent entries.
Lock bytes did not change. Lower totals do not prove remediation.

Recorded [enforcement checks](marketing-audit-enforcement-stage-a-20261006.md):
targeted suite 16 PASS, zero failures/skips; full policy 343 total, **335 PASS,
8 FAIL, zero skips**. The eight fail at the unchanged scope guard. These tests
were not rerun for this docs-only chunk and do not become acceptance evidence.

## Candidate boundaries from primary sources and locked parents

| Locked root leaf | Exact proposed target | Locked parent edge | Decision |
| --- | --- | --- | --- |
| compression 1.8.1, `node_modules/compression` | 1.8.2 | nested Expo CLI 57.0.16 → `^1.7.4` | Fits existing range; include in proposed R1 |
| source-map-js 1.2.1, `node_modules/source-map-js` | 1.2.2 | PostCSS 8.5.23 → `^1.2.1` | Fits existing range; include in proposed R1 |
| postcss-selector-parser 6.1.2, `node_modules/postcss-selector-parser` | 7.1.6 fixes both recorded causes | postcss-nested 6.2.0 → `^6.1.1`; Tailwind 3.4.19 → `^6.1.2` | Does not fit either range; exclude from R1 |

Official patched-version fields confirm the two HIGH fixes:
[compression GHSA-vc2v-76pw-4v95](https://github.com/advisories/GHSA-vc2v-76pw-4v95),
[source-map-js GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).
The primary-source note verifies their exact fetched registry tarballs, not merely
the npm report's `fixAvailable` field. Compression adds `destroy: 1.2.0`;
that exact package/version already exists in the root lockfile and must remain
byte-identical unless separate review shows a necessary change.

Root direct declarations are Expo `^57.0.9`, NativeWind `^4.1.0`, PostCSS
`^8.4.49` (dev), and Tailwind `^3.4.15` (dev). Tailwind depends on nested
`^6.2.0`. NativeWind 4.2.3 peers on Tailwind `>3.3.0`, while CSS interop 0.2.3
peers on `~3`. A Tailwind major migration therefore is a cross-consumer change,
not a safe transitive patch. No override, forced update, major parent upgrade,
direct dependency addition or Tailwind/NativeWind migration is proposed here.

Selector 6.1.3 fixes the older LOW cause; current legacy-v6 6.1.4 still contains
the quadratic scans and remains within the MODERATE affected range `<7.1.6`.
See [MODERATE advisory](https://github.com/advisories/GHSA-rj75-hqrm-r3gf) and the
[older LOW advisory](https://github.com/advisories/GHSA-w9m9-85wc-3x92).
Neither 6.x version is represented as complete remediation. R1 leaves 6.1.2
and both raw causes recorded. The existing HIGH policy threshold is unchanged;
not failing that threshold would not establish parser safety or launch acceptance.
A parser/parent compatibility proposal, if needed, requires separate review.

## Actual installed consumers; no artifact-exclusion assertion

The main agent read actual installed bytes and resolved nested paths, rather than
assuming top-level Expo CLI paths. All three installed leaf versions match the
root lockfile; one installed/locked path per leaf was found.

- Expo CLI's `build/src/start/server/metro/dev-server/compression.js` imports
  `compression` and invokes it for `.bundle` and `.map` URL paths.
  `createMetroMiddleware.js` registers that wrapper in the Metro middleware chain.
  The root `web` script invokes `scripts/start-dev.js --web`, whose Expo branch
  starts `--web --clear`. This source trace identifies a development consumer;
  it does not prove exclusion from exported, hosted or other runtime paths.
  The starter was not executed: it would start backend/worker/Expo and read env.
- PostCSS `input.js`, `map-generator.js`, and `previous-map.js` import
  `source-map-js`; `PreviousMap.consumer()` constructs its consumer from map
  text. Input processing and map generation reach these paths. Root PostCSS
  configuration uses Tailwind; Metro wraps its configuration with NativeWind.
- Tailwind `util/prefixSelector.js` uses selector-parser `astSync`, class walking
  and serialization. Several other Tailwind utilities import it. Nested
  `index.js` uses parser `processSync` when merging nested selectors. Neither
  parent is treated as unaffected merely because input is repository CSS.

These bounded source traces and the absence of direct leaf imports in searched
app sources are not generated-artifact, execution-path or public-exposure proof.
Forge prebuilt bundles remain unpatched; no bundle is approved by this review.

| Inspected installed/config file | SHA-256 |
| --- | --- |
| `node_modules/expo/node_modules/@expo/cli/build/src/start/server/metro/dev-server/compression.js` | `57a9c35c52c4cd18d2ae2ab5c10cd70e5f7d26497ae60dbadb4a55a5a288eb60` |
| `node_modules/expo/node_modules/@expo/cli/build/src/start/server/metro/dev-server/createMetroMiddleware.js` | `6bd3448ab9c4591fc2355b91a3b144e1f74390cf9d0764b92a69b477674c1d13` |
| `node_modules/postcss/lib/previous-map.js` | `5ff94015422fc77cc8b68428aa4ccf255d57d0d0be18fe81bc52590e3136433e` |
| `node_modules/postcss/lib/map-generator.js` | `feccbc87472d5d1cc660c2bfd4958cbe5442173f03cbfa518808725f684a313c` |
| `node_modules/tailwindcss/lib/util/prefixSelector.js` | `f6ced5eeaaef7b0e366191dc1ff8d3d4a9367f9557755ff1957602200225846f` |
| `node_modules/postcss-nested/index.js` | `2c037b5112bf219221b9b94c5cb4495f52cd694d3252d56ae38a7f5d839e30f9` |
| `metro.config.js` | `ab96801ee9921671cd2e994e5210d707365ff7b44612e167d1cc4c722b6d302c` |
| `postcss.config.js` | `36f25fa065015c5ee75d7f27e115e5f45e89f14804478cb2df8a077738c97028` |
| `tailwind.config.js` | `a07175b8a56360701f5ab73608ff8f28680ea0b4ccbe252ba05778a9731eeb0c` |

## Verification completed in this research chunk

PASS on Node 24.18.0/npm 12.0.2: unchanged `npm run deps:verify`; independent
retained report/decision hashes; installed-version/parent-range inventory.
Main-agent in-memory functional fixture also passed using actual installed
PostCSS 8.5.23, source-map-js 1.2.1 and selector-parser 6.1.2:

```js
const assert = require('node:assert/strict');
const postcss = require('postcss');
const nested = require('postcss-nested');
const selector = require('postcss-selector-parser');
const { SourceMapConsumer } = require('source-map-js');
const prefix = require('tailwindcss/lib/util/prefixSelector').default;
(async () => {
  const result = await postcss([nested]).process(
    '.fixture { color: red; &:hover { color: blue; } }',
    { from: '/synthetic/fixture.css', to: '/synthetic/out.css',
      map: { inline: false, annotation: false } },
  );
  assert.match(result.css, /\.fixture:hover/);
  assert.equal(result.map.toJSON().version, 3);
  const original = new SourceMapConsumer(result.map.toJSON())
    .originalPositionFor({ line: 1, column: 0 });
  assert.equal(original.source, 'fixture.css');
  assert.equal(original.line, 1);
  const input = '.fixture[data-label="value"]:not(.disabled)';
  assert.equal(selector().processSync(input), input);
  assert.equal(prefix('peso-', '.fixture:hover'), '.peso-fixture:hover');
})();
```

The fixture generated maps/ASTs only in memory; no file, external request,
application server or provider changed. This baseline compatibility check is
**not** a patched-candidate test, exploit regression, build or security pass.
The primary-source sidecar inspected upstream security tests but did not execute
them. Official patched-version fields were also independently checked by the
main agent. No candidate install/build, full suite rerun or hosted check ran.

## Proposed approval R1 — two root patches and consumer tests only

Ask Nathan before implementing this scope. If approved:

1. Prepare a credential-free isolated copy of committed source. Do not copy
   env files, existing dependency/output trees, raw provider exports, backups or
   the five unrelated notes. Preserve the original workspace `dist` output.
2. Change only the root lock entries for compression 1.8.1→**1.8.2** and
   source-map-js 1.2.1→**1.2.2**, using the exact reviewed registry metadata/SRI.
   Compression's new dependency edge points at already locked destroy 1.2.0.
   Require a full lock diff with no unrelated version, integrity, package path,
   direct-manifest, lifecycle-permission or peer-range churn. Stop if it cannot
   stay within that boundary; do not use `npm audit fix`, `--force` or overrides.
3. Use a scripts-disabled clean install first, then explicitly run the unchanged
   local patch applier/verifier. No new third-party lifecycle allowance. Record
   any install prerequisite failure rather than forcing past it.
4. Add bounded tests at a new `scripts/root-dependency-consumers.test.js` seam:
   real compression middleware and small local/in-memory HTTP response-close
   behavior; real SourceMapConsumer offset validation plus ordinary PostCSS
   map round trips; existing Tailwind/nested-selector functional compatibility.
   Reproduce the security assertions against the old leaves first using bounded
   inputs/timeouts; never iterate an enormous old source map or send exploit
   traffic to providers. Retest on the candidate one behavior at a time.
5. Verify clean installed patch/consumer bytes, exact dependency versions/SRIs,
   tests on supported Node 20 and 24, typecheck, and the complete policy suite.
   Retain raw complete root audit and guard decisions; no expected count is an
   acceptance pin. The guard must still FAIL for the unchanged reviewed-lock
   pin (and later scope mismatch). Report all failures, including the existing
   eight policy failures; do not rewrite tests to suppress the pin guard.
6. Only if install, lock-diff and bounded compatibility/security tests pass,
   apply the same minimal lock/test changes to the workspace, record exact
   resulting hashes, and make a detailed local commit. Stop after this chunk.
   An install/lock-diff/consumer/typecheck failure or an additional unexplained
   policy failure stops before applying candidate changes. The known pin/scope
   failures remain a release hold, not permission to advance the launch gate.

R1 authorizes neither a security pass nor a build/deploy bypass. Application
code, root `package.json`, web manifest/lock, parent versions, parser 6.1.2,
existing allowances, patch/verifier/consumer pins, root audit implementation,
reviewed-lock pin, frozen-scope pin and expiry remain untouched. Evidence notes
may record results. No push, workflow dispatch, provider change or deployment.
The previously approved web-only Stage A is separate; this proposal does not
broaden its unresolved cache treatment or convert source research to proof.

## Later R2 — separate exact-byte security review, not preauthorized

The root guard pins `package-lock.json` at the baseline hash above. An R1 lock
change will be rejected before the existing frozen-scope check. The approved
149-file scope remains
`6bb00beeef8b04023e9bfe30e042bb7f414a2611f88293b10cce0f489e83a242`;
the current **unapproved intermediate** scope is
`cf27b590dc1be86cd69303207157cb4d6c23f3527ff59d68edf48699a9a0945a`.
Neither pin is refreshed during R1.

After complete root/web candidate dependency, installed consumer and security
evidence is assembled, Nathan must review exact final lock/scope bytes and
approve any reviewed-input/scope pin replacement separately. Record before/after
hashes and the audit-script change if approved. Do not automatically refresh
the root lock pin, scope pin or any other input, even to restore green tests.
Expiry remains **2026-10-12T23:59:59Z**; reaching it stops the temporary treatment,
not permission to renew. Unresolved HIGH/CRITICAL causes still block independently
of any approved pin update. Parser risks remain explicitly recorded.

## Stop: earliest gate and next blocker

Gate 2 remains FAIL; nothing advances to credentials/auth/recovery/migrations
or exposure. No actual generated frontend artifacts or Forge execution paths
were verified. Hosted CI retention, Netlify privacy/API/DB binding and every
later launch gate remain mandatory; historical PR results are not candidate
acceptance. No provider, production database, branch protection or public
visibility changed. No CONTEXT/ADR update is warranted by this research.

- Obtain Nathan's specific **R1 approval** for the two root patches and bounded
  consumer tests above, with both reviewed pins left unchanged.
- If approved, perform one isolated candidate chunk; stop on any failed
  candidate gate and report exact lock/test/install/audit hashes.
- Separately complete the approved web candidate review without suppressing
  unresolved cache findings, then assemble final-byte evidence for R2/Stage B.
- Only after separately approved pin review, rerun every failed security gate
  at the resulting committed SHA; do not skip artifact/Forge/privacy acceptance.
