# Root dependencies — primary-source review

For Nathan, 2026-10-06 America/New_York; workspace HEAD
`80bab91d42bd79f00086b3453d79497e06c842e7`. Research only. Minimum
advisory-patched targets are **compression 1.8.2, source-map-js 1.2.2,
postcss-selector-parser 7.1.6**. These are review candidates, not an approved
root remediation or exemption. Local parent edges and installed consumer traces
remain the main agent's independent work; this sidecar does not reproduce them.

## Dated baseline and authority

Read the [Stage A enforcement record](marketing-audit-enforcement-stage-a-20261006.md)
and [raw root report](../../artifacts/npm-audit/run-Fcxyt2/npm-audit.json).
Their respective SHA-256 values are
`2245c1197cdf2e837bb322362cd015fbad0ad1f7a5692c339f1358bf7b83b65e` and
`d50bb04c1a745d257b5acf9e17b8c9a955c4735c5974f4491d25f04e6afad6e8`.
The latter has **25 HIGH, 8 MODERATE, zero CRITICAL**, versus the record's
earlier 27 HIGH/8 MODERATE. Both identify the same three concrete causes below;
the LOW selector advisory remains a `via` cause under the MODERATE package.
Neither totals nor `fixAvailable: true` establish acceptance.
[Raw report](../../artifacts/npm-audit/run-Fcxyt2/npm-audit.json),
[earlier record](marketing-audit-enforcement-stage-a-20261006.md)

Stage A covers the isolated web candidate, not root dependencies or the root
reviewed-lock/input pin. Gate 2 remains FAIL. Existing braces 3.0.3/Forge 1.4.0
treatment and **2026-10-12T23:59:59Z** expiry remain unchanged; generated
artifact/bundle and Forge-path applicability remain unproven. Root mutations
require a separate bounded proposal and authority. [Stage A record](marketing-audit-enforcement-stage-a-20261006.md)

## Verified targets and owning patches

| Root report version / cause | Official affected range | Minimum patched release |
| --- | --- | --- |
| compression 1.8.1, HIGH | `<1.8.2` | [1.8.2; GHSA-vc2v-76pw-4v95](https://github.com/advisories/GHSA-vc2v-76pw-4v95) |
| source-map-js 1.2.1, HIGH | `>=1.0.0 <1.2.2` | [1.2.2; GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q) |
| selector-parser 6.1.2, MODERATE | `<7.1.6` | [7.1.6; GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf) |
| Same selector-parser, existing LOW | `>=6.1.0 <6.1.3`; `>=7.1.0 <7.1.3` | [6.1.3 / 7.1.3; GHSA-w9m9-85wc-3x92](https://github.com/advisories/GHSA-w9m9-85wc-3x92) |

**Compression:** the owning [151f63e patch](https://github.com/expressjs/compression/commit/151f63e91e1b64f8fb0b064e19321a4f28db6bff)
registers response-close cleanup before headers, destroys the zlib stream, and
handles a stream created after close. It adds `destroy: 1.2.0`; tests cover
gzip/deflate/Brotli and late stream creation. The [1.8.2 release](https://github.com/expressjs/compression/releases/tag/v1.8.2)
also changes `Cache-Control: no-transform` matching to case-insensitive.
Fetched `index.js` matches the registry `gitHead` source byte-for-byte. Middleware
and `.filter` exports persist; declared Node `>=0.8.0` is unchanged. The new
[destroy dependency](https://registry.npmjs.org/destroy/1.2.0) declares Node
`>=0.8` and npm `1.2.8000 || >=1.4.16`. These declarations and source comparisons
do not prove consumer behavior. [Old metadata](https://registry.npmjs.org/compression/1.8.1),
[target metadata](https://registry.npmjs.org/compression/1.8.2),
[target implementation](https://github.com/expressjs/compression/blob/0f9707417bd53d41a319fce8bdb80dfa08b435c8/index.js)

**Source-map-js:** the owning [cf76580 patch](https://github.com/7rulnik/source-map-js/commit/cf7658058ceeaa8619d5ae0ec90be6905209d016)
validates non-negative safe-integer section offsets, caps individual and summed
nested line offsets at 10,000,000, caches nested `sources` reads, skips exhausted
generated code, and serializes line gaps with `String.prototype.repeat`.
Malformed/oversized maps now throw. The [1.2.2 release](https://github.com/7rulnik/source-map-js/releases/tag/v1.2.2)
also fixes browser CSP/unsafe-eval behavior. Compared with 1.2.1, all shipped
declarations and `source-map.js` exports are byte-identical; three runtime files
change. Consumer, generator and source-node target bytes match the owning
`gitHead`. Declared Node `>=0.10.0`, CommonJS entry `./source-map.js`, and absence
of runtime dependencies persist. **Compatibility uncertainty:** the new
[`repeat` call](https://github.com/7rulnik/source-map-js/blob/0a1d334fd1e55a47df97fcd60a7915d46df3b08a/lib/source-map-generator.js#L355)
requires that builtin or a polyfill; the unchanged legacy engine declaration
alone cannot prove compatibility. No legacy-runtime or browser test was run.
[Old metadata](https://registry.npmjs.org/source-map-js/1.2.1),
[target metadata](https://registry.npmjs.org/source-map-js/1.2.2)

**Selector-parser:** the owning [62b1917 patch](https://github.com/postcss/postcss-selector-parser/commit/62b191792df0a0bc56062e5a875bc74aae2a51cd)
replaces quadratic deduplication, class/id membership and Sass-interpolation
scans with Set membership; regression tests cover those paths. The fetched
7.1.6 `dist/parser.js` contains those changes, consistent with the
[`gitHead` source](https://github.com/postcss/postcss-selector-parser/blob/4eb3468e754f9f94d2092d103767bae98aa41438/src/parser.js)
and [7.1.6 release](https://github.com/postcss/postcss-selector-parser/releases/tag/7.1.6).
The advisory's differential-corpus claim was not independently reproduced.
Depth limits do not fix this flat-selector cause. [MODERATE advisory](https://github.com/advisories/GHSA-rj75-hqrm-r3gf)

The older LOW fix adds parsing/stringifying depth limits and clone/walk guards
(default 256): [e37c5b0](https://github.com/postcss/postcss-selector-parser/commit/e37c5b0b785b165e27508d2489fdec8e0f18b10a),
[5bc698c](https://github.com/postcss/postcss-selector-parser/commit/5bc698cef66f8abd12610dc623e5d67cbc0f869d),
[6.1.3 backport release](https://github.com/postcss/postcss-selector-parser/releases/tag/6.1.3).
Use the LOW advisory's patched-version fields (6.1.3/7.1.3); its prose still
mentions 7.1.1 and is inconsistent with those fields. [LOW advisory](https://github.com/advisories/GHSA-w9m9-85wc-3x92)

The current [registry packument](https://registry.npmjs.org/postcss-selector-parser)
has `latest: 7.1.6` and `legacy-v6: 6.1.4`. Neither 6.1.3 nor 6.1.4 clears
the MODERATE range. The fetched 6.1.4 parser still uses all three quadratic
`indexOf` scans; its [release](https://github.com/postcss/postcss-selector-parser/releases/tag/6.1.4)
only records tolerance for non-node children during serialization.
[6.1.4 registry bytes](https://registry.npmjs.org/postcss-selector-parser/6.1.4)

Across 6.1.2→7.1.6, declared Node `>=4`, `dist/index.js`, bundled declarations,
`cssesc ^3.0.0` and `util-deprecate ^1.0.2` remain. However, [major 7 changes
insertion during iteration](https://github.com/postcss/postcss-selector-parser/blob/4eb3468e754f9f94d2092d103767bae98aa41438/CHANGELOG.md);
7.1 adds multi-node insertions and subsequent security fixes reject excessive
depth. **7.1.6 cannot satisfy a major-6-only parent range.** Main-agent evidence
must resolve those locked parents and test their API/output behavior before any
parent upgrade or override proposal. This is an incompatibility to resolve,
not grounds for exemption. [6.1.2 metadata](https://registry.npmjs.org/postcss-selector-parser/6.1.2),
[7.1.6 metadata](https://registry.npmjs.org/postcss-selector-parser/7.1.6)

## Registry byte binding and verification

HTTPS metadata and tarballs were fetched **into memory only**, parsed as data,
and compared without install, lifecycle scripts or package execution. For all
ten inspected releases (compression 1.8.1/1.8.2; source-map-js 1.2.1/1.2.2;
selector-parser 6.1.2/6.1.3/6.1.4/7.0.0/7.1.3/7.1.6), computed SHA-512 and
SHA-1 matched `dist.integrity`/`dist.shasum`, tarball manifests matched package
identity, and listed ECDSA signatures verified over `name@version:integrity`
using [npm's published keys](https://registry.npmjs.org/-/npm/v1/keys) and
[signature format](https://docs.npmjs.com/about-registry-signatures/).
Old releases use the retained expired historical key; patched targets use
`SHA256:DhQ8wR5APBvFHLF/+Tc+AYvPOdTpcIDqOhxsBHRwC7U`, with null expiry.
This verifies registry binding, not publisher provenance or application safety;
compression's advertised provenance attestation was not verified.

Each target's metadata links to its expected owning GitHub repository and the
tarball under the same `registry.npmjs.org` package identity. Observed bytes:

| Target / official metadata | Tarball bytes / SHA-256 | Registry `gitHead` |
| --- | --- | --- |
| [compression 1.8.2](https://registry.npmjs.org/compression/1.8.2) | 7297 / `15e46c301ad6468d3838cfc0dbfca3024220ef12f8a43b8156846691011537a6` | `0f9707417bd53d41a319fce8bdb80dfa08b435c8` |
| [source-map-js 1.2.2](https://registry.npmjs.org/source-map-js/1.2.2) | 36349 / `05c8cf8e7c3a6b56cada7668fe9342b10f4b625efc92aba9ba05b9e8fe4d71a3` | `0a1d334fd1e55a47df97fcd60a7915d46df3b08a` |
| [selector-parser 7.1.6](https://registry.npmjs.org/postcss-selector-parser/7.1.6) | 46652 / `48c903f98c5591d8d26f16f389d5cb3435459474c645209a79f6241bf4b657b6` | `4eb3468e754f9f94d2092d103767bae98aa41438` |

Exact matched target integrity strings, in table order:

```text
sha512-o8vI5RE5A6EVVOd9o41jKp41aJom+QTEO/Bx8MYNjexMo/Bv2WOjUfZr+aL0WnYSgymUy6zeguqLTsIhV0gMvQ==
sha512-KGj/8Y43x35aZVDtt+J4mK1hoLGHULMYfSkODJNQjNDC3oW1PqPoxMwo0pLUsWM/UEGzON/NxeHywEfNXNP3Vw==
sha512-7qASPzhKF2l2KLboRZux8CCTRMdGiV08vWmyKzPz22qZ7ZjQBOeY7rNzNoCLSUiftJ7HUq0GERHmxw/t0dCdMw==
```

Inspected 6.x comparison bytes, **not MODERATE-patched candidates**:

| Official metadata | Tarball bytes / SHA-256 | Matched integrity |
| --- | --- | --- |
| [selector-parser 6.1.3](https://registry.npmjs.org/postcss-selector-parser/6.1.3) | 44817 / `d5716311b9d55b70862dd46e50a4d8163854d6ab61331948f9cbb27727b9c081` | `sha512-cDoO18VWCIWRsSaws3C23b0HXRxlUknttfdNcbXnf3IGHAPRNLlXPHc6dYiatOkxW0W4uZh524Plaaw5a7WEtQ==` |
| [selector-parser 6.1.4](https://registry.npmjs.org/postcss-selector-parser/6.1.4) | 45101 / `d0e20cd70b1be34f5f45d256986e6a372c35cc6a4643046b0de35035cfc61d66` | `sha512-bIoJLOmjCO1S9XdY/DcnR5hJxvrDir1PbGChrzXG3vw0/FOliy/fA3dmdhQ441kah4gKv+TwckGzex6wNS5cnQ==` |

Current advisory API response SHA-256 bindings (remote responses were not saved):

| Official API | SHA-256 |
| --- | --- |
| [vc2v-76pw-4v95](https://api.github.com/advisories/GHSA-vc2v-76pw-4v95) | `e5e754dbaa61327f48cc2f74d82aa3d070a9e4dbdb0c7e27a041876edfaf2144` |
| [68fv-2mgg-jv7q](https://api.github.com/advisories/GHSA-68fv-2mgg-jv7q) | `d1d6d52530049a7bf189b054779e9a3f7cab5848c8566f9d4efc5cb152c4ac05` |
| [rj75-hqrm-r3gf](https://api.github.com/advisories/GHSA-rj75-hqrm-r3gf) | `e98ee683abb4f138fd18d98ec3fd60cee989bebf6f48d280e321947597b3146b` |
| [w9m9-85wc-3x92](https://api.github.com/advisories/GHSA-w9m9-85wc-3x92) | `0e9caac8247ae00f3522bf4bfc8e3b9bdbf3473645e9d3f78339fc6b97c77f3b` |

## Remaining evidence

The main agent supplied completed local tracing: Expo nested CLI 57.0.16
uses compression `^1.7.4`; PostCSS 8.5.23 uses source-map-js `^1.2.1`;
parser parents nested 6.2.0 / Tailwind 3.4.19 use `^6.1.1` / `^6.1.2`.
These supplied ranges admit the first two patch targets and exclude parser
7.1.6. The main agent reports the baseline real PostCSS nesting/source-map/selector and
Tailwind prefix fixture PASS, explicitly functional evidence, not security
proof. This sidecar did not rerun or independently verify that local evidence;
the main proposal must bind it to its actual trace/fixture artifacts.

Main-agent parent-range and installed-consumer evidence must establish actual
reachability, runtime compatibility and resulting artifacts; this note makes
no exposure/exemption decision. Then obtain separate authority for exact root
dependency/lock and reviewed-input-pin changes, validate any authorized candidate
against concrete advisories and all required gates, and bind resulting bytes
to a reviewed SHA. [Stage A requirements](marketing-audit-enforcement-stage-a-20261006.md)

No install, audit fix, code/dependency/lock/pin/exception change, commit, push,
provider action or other-thread message was performed. Only this note was
written. The five original untracked deployment notes were preserved. Upstream
tests were inspected, not executed; no root build or acceptance gate was run.
