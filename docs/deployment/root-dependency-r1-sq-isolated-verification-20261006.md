# R1-SQ isolated verification — Gate 2 remains FAIL

For Nathan, 2026-10-06 America/New_York. Nathan approved the
[isolated R1-SQ proposal](shell-quote-remediation-proposal-20261006.md) in this
chat. This completes that bounded candidate-verification chunk, **not security
acceptance or authority to apply the candidate to the workspace**. No later
launch gate advanced. The TDD skill influenced the public quote/parse seams,
first failing tracer test and regression controls; no private module-ID test or
shell execution was used.

## Source, authority and exact candidate

Source archive: `67269d1684cb39a546f89a61d082bd5b2103c3f5`, tree
`096c762e4b70cc3631bd65db0476c8a778e2292b`. Tracked workspace source was clean
at start; five original untracked deployment notes remained outside the copy.
Separate archive-only trees at `/private/tmp/peso-r1-sq.bsT0rf/node24`, `node20`
and `red` have **no Git metadata**. Receipts explicitly report null candidate
Git metadata; no fake commit/CI provenance was supplied.

The preserved [R1 candidate](root-dependency-r1-candidate-hold-20261006.md) was
not changed. Only its held compression/source-map lock entries and five-test
consumer fixture were reused. No existing workspace or held-candidate
`node_modules`/dist tree, active env, credentials, provider exports, backups or
five notes were copied. Committed sanitized `.env.example` templates are inert
source fixtures. Child commands use an allowlisted, credential-free environment
with dotenv disabled.

Strict whole-lock comparison passed on both runtimes: identical package paths,
top-level fields and all other entries. Exactly three leaf entries differ from
the workspace baseline: compression 1.8.1→1.8.2, source-map-js 1.2.1→1.2.2,
shell-quote 1.9.0→1.11.0. The held compression edge to already locked destroy
1.2.0 is unchanged. No manifest, parent, peer, override, package-path or
lifecycle-permission change. All 649 archived tracked source files were checked
against the clean source baseline, except the explicitly changed root lock;
the added consumer-test bytes are bound separately.

| Source/candidate/evidence | SHA-256 |
| --- | --- |
| Workspace root lock, unchanged | `0fe09a3b2fff880383d9e6bf098fbf7218145a96c78633db71cc9f89e778fc9c` |
| Isolated three-leaf lock; **not a reviewed security pin** | `4cedd8e60ddf78842e2a1365b077e8642e1788591178a0e13984c3336a607ad3` |
| Final isolated `scripts/root-dependency-consumers.test.js` | `a6803c7aa6a9a880aef99e4f957a0c3c7c93c00bb8eeae96053855cc5f292042` |
| 649-file baseline source inventory | `078125c2e3a3cb026d0f58aa3f7e9584757345b062d7a1695ff0b2473289169e` |
| Retained 91-file evidence inventory | `b9d02fd9f9076b1e28638db5bc2fc749abceec2833b3181e8a35929a75016313` |
| 24-check verification summary | `49eb30b8256f5c24c4aec4817f07b93471b23e59dca51ff95dc167bd42245ba8` |
| Raw audit comparison, not classification authorization | `7936055b78bf1798c070b677548f97fd6dc14d5e184cf423f4ccc9c62a96104d` |

Ignored retained evidence:
`/Users/nathan/Downloads/peso-app/artifacts/root-r1-sq/run-BJgixm`.
It includes candidate lock/test bytes, original/corrected diagnostic utilities,
complete stdout/stderr/receipts, both raw audit attempts/decisions, package/source
inventories and summaries. Every retained receipt stream and raw audit attempt
checksum was reverified. Disposable npm cache and the inventory itself are
excluded explicitly; this is local evidence, not hosted CI or protected backup.

## Candidate tests and separate clean runtimes

The first tracer security assertion was RED against clean-installed 1.9.0:
`quote()` accepted LF after a comment instead of throwing. After the sole
shell-quote identity update, the same assertion was GREEN on 1.11.0.
Six final security assertions also failed on the separate old-leaf `red` tree:
LF, CR, U+2028, U+2029, a non-adjacent later token, and appended multiline input
after a parse-produced comment. All six are GREEN in the final candidate.
The initial tracer preceded the upgrade; extended regression controls were
added afterward, with a separate old-leaf sensitivity run. Neither returned
command text nor any upstream shell-execution test was executed.

New controls cover ordinary editor arguments without launching an editor,
newline-before-comment/later ordinary tokens, apostrophe/exclamation quoting,
empty/tilde glob text, ANSI-C quoting/NUL truncation/no environment expansion,
literal/escaped backslashes, underscore variables/nested substitutions and
opt-in unquoted field splitting. Expected literals were checked against the
[immutable upstream public regression examples](https://github.com/ljharb/shell-quote/tree/88241f8fa324a85da03b40fc69443c069837b472/test);
the upstream suite itself was not run. The existing five real compression,
source-map, PostCSS, Tailwind and Expo consumer tests were preserved.

PASS on **each** independently clean-installed candidate:

- Node **24.18.0 / npm 12.0.2** and Node **20.20.2 / npm 10.8.2**:
  `npm ci --ignore-scripts --no-audit --no-fund`; no third-party hooks ran.
- Explicit unchanged local braces/Forge patch apply and verification; typecheck.
- **19 consumer tests, 19 PASS, 0 FAIL/cancelled/skipped** on each runtime.
- Strict lock/source/checked-consumer and registry/installed-byte verification.

Existing UUID deprecation and the initial npm update notice were retained, not
fixed outside scope. No global runtime/npm installation changed. The preserved
official Node-20 archive was rehashed to
`8be6f5e4bb128c82774f8a0b8d7a1cc1365a7977d9657cece0ca647b3fe04e61`;
its prior official-checksum verification is linked in the R1 hold.

## Installed bytes and the unchanged vendor boundary

On both runtimes, reviewed tarball SHA-256 and locked SHA-512 SRI matched for
compression, source-map-js, shell-quote and react-devtools-core. Every shipped
regular file matched installed bytes: respectively **4, 18, 11 and 15 files**.
There were no extra/missing own-package files. Compression's unchanged nested
debug 2.6.9, ms 2.0.0 and negotiator 0.6.4 paths also matched the baseline lock
and their separate locked-SRI tarballs (17, 4 and 9 files). Those are existing
dependencies, not newly authorized upgrades.

Shell-quote 1.11.0 tarball SHA-256 remains
`028be526afacb2bf5c6c008a95d5435b5d205135f68bb48afd0bb947610393f1`;
its 11-file installed inventory digest is
`56095321479443abe3194f915cbc180e53845efc2d737570acfe459f7e691da9`.
The exact target SRI/registry gitHead/source/signature review remains in the
[primary review](shell-quote-primary-source-review-20261006.md); signatures
were not freshly reverified in this installation chunk.

The checked Forge/braces consumers, React Native setup source and all inspected
DevTools bundle/map bytes remained unchanged. DevTools' supplier inventory
digest remains `c9840bf9d490eca773431728472a2e9babb814c26c9cb6f15ad800447323456d`.
Its actual standalone bundle remains
`83ee56e2e867720123418336f83f1aea6c40a5d8c582da22f09e07d58d8bbce0`.
Thus the root update did not rewrite parent prebuilt bundles. No supplier-wide
fixed/unaffected assertion, VEX or new exception is issued. Actual Peso-generated
frontend/deploy execution paths, including excluded unpatched Forge bundles,
remain unverified; the prior installed-module trace is not deployment proof.

## Failed full policy and complete raw audits

Full `npm run test:policy` on **both** runtimes: **362 total; 349 PASS,
13 FAIL, zero cancelled/skipped**. All 13 locations match the prior R1 failure
set in unchanged `scripts/npm-audit-ci.test.js`: 393, 400, 409, 419, 436, 467,
485, 498, 505, 554, 561, 584, 617. The unchanged reviewed-lock pin stops those
CLI fixtures before their intended assertions. No assertion, guard, pin or
scope was rewritten; these remain failures, not exclusions or acceptance.
Complete policy stdout SHA-256: Node 24
`536c0675f3c7842325aa3936fde4175404593fd0bea87f97ff35deb7d382ddb0`;
Node 20 `2ebae1a2792903cc88f6b77d71b3d38471222b6e3a7480e5d3f1827f1ebb07d8`.

Both real complete root audits retained valid JSON and raw exit **1**. Both
unchanged guards exited **1** at `Audit reviewed evidence mismatch:
package-lock.json`, before project-policy classification. Source-only audit
metadata is null; external receipts bind the actual source/candidate bytes.

| Runtime / audit start UTC | Raw findings | Report SHA-256 | Decision SHA-256 |
| --- | --- | --- | --- |
| Node 24 / 2026-10-06T18:11:06.796Z | **25 HIGH, 8 MODERATE, 0 CRITICAL**, total 33 | `6337562400adccfcd03c621ff986c704ad71e26c48a195fb6f97b6585b0532f3` | `f700840e9c721f70eccf83bb6cf9de2e5c25c7767ae61c568bae346c8994e2f5` |
| Node 20 / 2026-10-06T18:11:02.437Z | **23 HIGH, 8 MODERATE, 0 CRITICAL**, total 31 | `c41a637e02eee07c9a9ef7d946efc2c50efbff013aaa423059f76efff771e799` | `cb1e7017b444e3ffabef1820739d378578c54afb1d53ccc2741d9ab615b83f0c` |

Compression, source-map-js and shell-quote entries are absent in both reports.
Compared with the retained R1 audit, the sole removed independent advisory cause
is shell-quote source 1241332. **No new/changed independent advisory object**
appears; every remaining object's metadata exactly matches that retained raw
report. This is historical-cause comparison, not policy classification.

The npm-12 report adds two indirect HIGH entries absent in npm-10 and the old
report: nativewind → react-native-css-interop → tailwindcss. Their locked package
entries and existing descendant advisory objects are unchanged. The difference
is retained as graph/report variation; its precise npm/service cause was not
diagnosed. Neither report's propagated HIGH entries were dismissed or newly
allowlisted. Raw braces/Forge/image-size HIGH and selector-parser/UUID MODERATE
remain. Zero CRITICAL here is **not a clean registry audit**.

## Diagnostic/setup failures, preserved rather than counted as passes

- Evidence-directory creation initially lacked its parent; created the narrow
  parent and retried. Web retrieval of two immutable source files returned cache
  misses; approved read-only HTTPS fallback supplied the regression examples.
- The initial Node-24 typecheck invocation omitted `run`; npm rejected the
  command before typecheck. Correct `npm run typecheck` passed separately.
- The new byte helper initially counted compression's nested dependencies as
  extra compression tarball files. Candidate work paused: read-only checks
  confirmed all three paths/entries exactly matched the unchanged lock. The
  corrected diagnostic separates own-package files and verifies those nested
  packages against their own locked tarballs. Both original helper bytes and
  its failed receipt remain retained. **No authoritative validator changed.**
- An optional process-list diagnostic was sandbox-denied; final command receipts
  supplied completion evidence instead. It is not a passed check.

The failed attempts are not installation/type/security acceptance. Early receipts
bind candidate inputs; later receipts additionally hash runner/command scripts.
The retained initial/corrected utilities are inventory-bound; no retrospective
runtime/CI provenance is claimed.

## Stop, unchanged boundaries and next blocker

**Gate 2/security remains FAIL.** Only this sanitized record is intended for a
local documentation commit. Workspace root/web locks, dependencies, test files,
installed trees, existing dist, audit guards, patch manifest and five notes are
untouched. Root guard remains
`672b8aa5daa03bf35ed06c8eed761c9a2cd95516c2a9bc3b858e87f093ed7170`;
reviewed root-lock pin remains the baseline hash; frozen frontend-scope pin
remains `6bb00beeef8b04023e9bfe30e042bb7f414a2611f88293b10cce0f489e83a242`.
All existing allowances and expiry **2026-10-12T23:59:59Z** are unchanged.

No workspace application, pin refresh, build/budget/generated-artifact check,
fresh web audit, hosted CI/retention/privacy/binding check, push, dispatch, merge,
provider/database/credential change, paid resumption or public exposure occurred.
Unrun checks are not acceptance skips. The last web audit remains historical
7 HIGH/1 CRITICAL/1 MODERATE at `80bab91d42bd79f00086b3453d79497e06c842e7`;
no later gate is assumed complete. CONTEXT/ADR terms/decisions did not change.

Next blocker: remaining **Gate-2 root/web security and final-byte review holds**,
not the now-tested shell-quote candidate behavior.

- Next small chunk: read-only reconciliation of remaining root/web findings,
  approved treatment boundaries and exact outstanding evidence, then a bounded
  remediation/verification proposal for Nathan. No blanket audit fix or new
  allowance is authorized.
- Resolve approved remedies and actual generated frontend/Forge execution-path
  evidence before proposing final exact-byte R2/Stage-B pin review.
- Seek separate explicit authority before any workspace candidate application,
  reviewed-pin change or provider/deployment action; rerun every failed gate
  before progressing beyond security. This approval is not transferable.
