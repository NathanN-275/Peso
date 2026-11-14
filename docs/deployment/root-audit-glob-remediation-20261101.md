# Root npm audit repair research — November 1, 2026

The current failure is an inconsistent registry advisory graph, not a HIGH or
CRITICAL advisory count. The preserved report labels
`@expo/local-build-cache-provider` LOW while its `via: @expo/config` node is
MODERATE. Peso's unchanged `validGraph` intentionally rejects that downward
severity edge, then rejects Expo because it reaches that invalid branch. The raw
npm process exited zero, but the policy correctly exited one. Original report,
policy decision and exact inputs are retained in `original-audit/` and
`original-source/`; do not reinterpret the original run as accepted.

## Locked path and supported alternatives

The exact lock is Expo57.0.14 → local-build-cache-provider57.0.6 → config57.0.8.
Config57.0.8 pulls config-plugins57.0.8, glob13 and deepmerge4.3.1. The plugin path
also pulls xcode3/uuid7. These facts come from the preserved lock and official
published metadata: [Expo57.0.14](https://registry.npmjs.org/expo/57.0.14),
[cache-provider57.0.6](https://registry.npmjs.org/@expo%2flocal-build-cache-provider/57.0.6),
[config57.0.8](https://registry.npmjs.org/@expo%2fconfig/57.0.8), and
[plugins57.0.8](https://registry.npmjs.org/@expo%2fconfig-plugins/57.0.8).

Official registry sdk-57 tags currently resolve Expo57.0.31, cache-provider57.0.9,
config57.0.10 and config-plugins57.0.11. Latest57config still requires glob^13 and
deepmerge^4.3.1; latest57plugins switches to xcode^4.0.0 but still glob^13.
See the preserved `registry/` snapshots and [current Expo metadata](https://registry.npmjs.org/expo),
[config57.0.10](https://registry.npmjs.org/@expo%2fconfig/57.0.10), and
[plugins57.0.11](https://registry.npmjs.org/@expo%2fconfig-plugins/57.0.11).

The current [glob cancellation advisory](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4)
affects9–14.0.1 and lists14.0.2 as patched. The
[deepmerge advisory](https://github.com/advisories/GHSA-gcqx-w48m-w2h4)
still lists no patched release. These lower findings are retained, not hidden.

## Three distinct lockfile-only checks

All npm resolver operations used Node24, `--package-lock-only --ignore-scripts
--no-audit --no-fund`, then one real registry audit per distinct lock. No dependency
code or lifecycle scripts were run, and no `node_modules` was created.

| Candidate | Root Expo | Changes | Raw HIGH/CRITICAL | Unchanged graph predicate |
| --- | --- | --- | --- | --- |
| Original preserved lock |57.0.14|none|0/0|2 blockers |
| `cache57-update` |57.0.14|6 lock entries; supported cache/config/plugins refresh|0/0|same2 blockers |
| `scoped-glob14` |57.0.14|above plus2 scoped patched glob branches|0/0|0 blockers |
| `minimal-scoped-glob14` |57.0.14|only compatible plugins57.0.11 refresh plus2 scoped glob branches|0/0|0 blockers |

The selected smallest prototype keeps config57.0.8 and cache-provider57.0.6. It
updates plugins57.0.8→57.0.11 inside existing~57.0.8 ranges, bringing its supported
xcode4 dependency and removing uuid7. It adds exact glob14.0.3 overrides only under
`@expo/config` and `@expo/config-plugins`; unrelated glob consumers stay intact.
The lock has13 changed/added/removed package entries. Its audit retains4LOW and
7MODERATE findings, with0HIGH/CRITICAL and0 blockers from the ORIGINAL unedited
`findBlockingVulnerabilities`. Config is now LOW via deepmerge, so the cache
provider's LOW edge is consistent. This repairs the actual graph rather than
changing severity validation or adding an exception. No SDK58 migration is needed
to demonstrate this candidate's audit acceptance.

## Installed validation and remaining acceptance

The selected four-file change updates the manifest, lock, this record and ONLY
the exact reviewed lock hash in `npm-audit-ci.js`. Graph validation, severities,
provenance, patch integrity and rejection behavior remain unchanged.

[glob14.0.3 metadata](https://registry.npmjs.org/glob/14.0.3) retains CommonJS/import
entry points plus `sync` and `globSync`, the APIs used by the selected config/plugin
branches. Its own engine declaration includes Node18, but the selected transitive
lru-cache11.5.3 requires Node20 or22+; the whole tree must not be described as Node18
compatible. Integrity-verified official source archives and metadata are retained.

Independent actual Node24.18.0 and offline Linux Node20.20.2 fixtures passed14 real
filesystem glob cases,6 config-loader evaluation/rejection cases, and Xcode PBX
parse/edit/write/roundtrip/UUID checks. Config-plugins57.0.11 JavaScript is byte-
identical to57.0.8; its metadata updates dependencies. The changed require-utils
TypeScript6 path passed real loader fixtures. These checks cover the scoped
matching/configuration APIs, not every possible native project or Node22 execution.

The full candidate installed with `npm ci --ignore-scripts`; only Peso's existing
reviewed dependency patch tool was then applied and verified. All579 policy cases,
TypeScript, SQL audit and15 audit-rejection regressions pass. Actual root audit
accepts4LOW/7MODERATE findings with0HIGH/CRITICAL and0 blockers; the complete lower
findings remain visible. The combined synthetic release build and web audit pass,
with0 web findings. All64 emitted files match the prior session-checkpoint build
byte for byte, and its size budget passes. Expo's prebuild configuration resolves;
no native compilation or device/bridge behavior is claimed.

The earlier failing original audit and the compatible-refresh-only failure remain
preserved; they were not reclassified or ignored. Actual provider/browser/native
acceptance, protected hosted release and all other public-beta gates remain open.
The earlier unexplained intermittent avatar normalizer failure remains a separate
acceptance limitation; this dependency repair does not establish its cause or fix.
No hosted setting, visibility, credential, paid resource or audit exception changed.
