# Dependency security blocker — 2026-10-04

This records the investigation and isolated assessment, not current release
approval. On the 2026-10-05 recheck, braces PR #72 was closed without merging;
forge PR #1152 remained open. Nathan subsequently authorized implementation
without changing audit policy. See the separate
[installation evidence](dependency-patch-installation-20261005.md) for that work.

## Source and result

- Source checkpoint: `50ff89f9a4859fad4be77e5ec28b830d139110bf` on `feat/combined-public-beta`.
- Pull request: https://github.com/NathanN-275/Peso/pull/47
- `npm run audit:ci` reproduced the frontend security failure locally twice, both with exit code 1.
- Local runtime: Node `24.18.0`, npm `12.0.2`. The frontend-security workflow uses Node 20; staging workflows use Node 22. Reproducing locally rules out a CI-only failure.
- No dependency, lockfile, audit policy, provider configuration, or DNS change was made during this investigation. No merge or deployment was performed.

## Root findings

| Package | Installed / latest published version checked | Blocking advisory | Published patched version |
| --- | --- | --- | --- |
| `braces` | `3.0.3` | https://github.com/advisories/GHSA-vfj7-8cjw-p6xm | None listed |
| `node-forge` | `1.4.0` | https://github.com/advisories/GHSA-86w9-cpqp-85rv | None listed |

Read-only `npm view` checks confirmed both installed versions are the latest published versions. `npm ls braces node-forge micromatch --all` exited successfully and showed one deduplicated installed copy of each affected root package. This is not an outdated nested-copy problem.

`braces` is reached through Tailwind, file watching, and Metro tooling. `node-forge` is reached through Expo CLI and its code-signing certificates dependency. Audit output also flags their dependent packages; those names are not separate independent root vulnerabilities.

The audit's suggested resolutions include Tailwind `4.3.3` (a major upgrade) and Expo `44.0.6` (a downgrade from SDK 57). Neither was applied. These are not narrow, verified compatibility fixes.

Existing `image-size` findings and their existing policy treatment were not changed. No additional vulnerability allowance was added.

## Upstream proposals inspected

- `braces`: https://github.com/micromatch/braces/pull/72 — open; proposes bounded nesting and AST traversal checks. Contributor-reported regression results were not independently verified here.
- `node-forge`: https://github.com/digitalbazaar/forge/pull/1152 — open; proposes stricter nested DigestAlgorithm validation. Contributor-reported regression results were not independently verified here.

An open proposal is not a published fix or proof of maintainer acceptance. No third-party fork or unreviewed patch was installed.

## Next decision

The security gate remains failed. Keep PR #47 unmerged and provider changes paused.

Options are to wait for official patched releases, or separately assess reproducible local backports. A backport assessment must establish provenance, independently reproduce each vulnerability, test the fix and compatibility, and determine honest audit treatment before any implementation or release decision. A local patch alone must not be represented as a passing registry audit.

## Authorized isolated backport assessment

Nathan authorized assessment of the proposed fixes. No permission to install them into the application, weaken the audit policy, merge, deploy, or change DNS was inferred.

Assessment result: both candidates address the tested defects and preserve the tested valid behavior. This is evidence supporting a future implementation review, not security-gate or release acceptance.

### Immutable inputs

- Published `braces` 3.0.3 source tag: `74b2db2938fad48a2ea54a9c8bf27a37a62c350d`. Its `lib/` directory matches the installed package byte-for-byte.
- `braces` PR #72 candidate: `28d440b5dd449dbf1fe6f3506cf94ecca4d02660`; comparison base: `e53730e6f935498326c72d768889ac194eedc0e0`.
- The tested narrow brace backport applies only that proposal's five `lib/` file diffs to published 3.0.3. It excludes the base branch's unreleased quote handling and comma-invalidity changes. It retains the proposal's corrected stringify parent handling and parent-cycle guard.
- `node-forge` PR #1152 candidate: `ceba34402e329f0365134f23fe19898756527d65`; base: `7a43db987bd0ecdc5b41f6d73f58ba6ca5bf9ae1`. The base's entire `lib/` directory matches the installed 1.4.0 package byte-for-byte. The runtime patch changes only the nested DigestAlgorithm element-count check in `lib/rsa.js`.
- Both pull requests remain open; no official patched release was found. Registry rechecks still returned `braces` 3.0.3 and `node-forge` 1.4.0.

### Reproduction and verification

The baseline harness exercises depth guards and RSA nested-child rejection. Before the patches it returned 16 passes and 31 failures (exit 1); the two additional parent-cycle cases were added only to the candidate run, with bounded VM timeouts to avoid hanging on the baseline.

`braces.compile` with a 3,000-level pattern reproduced `RangeError: Maximum call stack size exceeded` under `node --stack_size=256`. The same candidate invocation returned the deliberate `SyntaxError: Input depth (101), exceeds max depth (100)` instead. This pattern did not crash Node 24 under its default stack; no default-stack crash on that runtime is claimed.

The locally generated RSA fixtures reproduce acceptance of an extra nested DigestAlgorithm child in the baseline, and rejection by the candidate. They test exponents 3 and 65537, valid structures with and without the optional NULL, and changed digests. These tests exercise malformed-signature acceptance, not a complete signature-forgery construction without access to a private key. Generated fixture private keys were never written or printed.

| Check | Node 20.20.2 | Node 22.23.3 | Node 24.18.0 |
| --- | --- | --- | --- |
| Candidate targeted security harness | 49 pass | 49 pass | 49 pass |
| Brace compatibility comparisons | 12,066 pass | 12,066 pass | 12,066 pass |
| Consumer checks | 6 pass | 6 pass | 6 pass |
| Published brace release suite against narrow backport | 764 pass | 764 pass | 764 pass |
| Full forge suite with test-focus correction | 829 pass, 4 pending | 829 pass, 4 pending | 829 pass, 4 pending |

Consumer checks cover ordinary matching, brace expansion, hostile-pattern rejection through the actual `micromatch.braceExpand` seam, `fast-glob` normal and hostile patterns, and Expo code-signing certificate creation/validation and signature generation/verification. An initial `micromatch.makeRe` rejection assertion failed because that API uses picomatch rather than braces; it was replaced with the correct brace-expansion seam, not treated as proof of a patch failure or success.

The unmodified forge full-suite entry point ran only five tests because the pinned upstream source contains `describe.only` in `tests/unit/jsbn.js`. `--forbid-only` correctly failed. Only in the temporary test copy, that marker was changed to `describe`, and the suite was rerun with `--forbid-only`. No runtime library change resulted from that test correction. The unmodified candidate's standalone RSA suite separately passed 101 tests, with four pending.

The full upstream brace candidate separately passed 904 tests on Node 24. That result is distinct from the published-release/narrow-backport result above.

All runtime compatibility tests ran locally on macOS x64. Official Node 20 and 22 archives were checksum-verified against their published SHASUMS before execution. These results do not claim Linux CI, browser/native end-to-end acceptance, or a full application build.

The unchanged audit policy's own 17 tests passed. A final `npm run audit:ci` still exited 1 with both root packages and their dependent chains blocked. No new allowance, invented package version, renamed fork, or bypass was added.

### Assessment artifacts and reproduction

The clearly labeled temporary assessment directory is `/private/tmp/peso-backport-assessment.DVzzxH`. It contains downloaded immutable sources, isolated test tools, checksum-verified Node runtimes, and a small `tested-assessment.tar.gz` bundle containing the harness and the two security-only patch files. Nothing from that area is installed into Peso. Both patch files passed `patch --dry-run -p1` against their stated pristine baselines.

SHA-256 evidence:

| Artifact | SHA-256 |
| --- | --- |
| `braces-release.tar.gz` | `697311aa470de468a1e5cac70ab227262dce9e38f5a4e0eef306d515b71222af` |
| `braces-candidate.tar.gz` | `746542c72b9108f70c19147b6afa2ae382469450d2590118d3dd5b97887cc53c` |
| `forge-candidate.tar.gz` | `9825224607d9eefa205125d563301951291b5ab21f05c29da8fb3083864eb982` |
| `braces-security-only.patch` | `e07abe26dbd330daea0e448ca1382327322dd5eccc08c5dd1a9b9f7bf5a6d699` |
| `node-forge-rsa.patch` | `f4ab98b30a7b6997e80c810a8f2fd90dad534c734228ad9273199b382d5fbda2` |
| `assessment.cjs` | `75057eac1fbe5e0631053bc20edb7421b07f92a458ecf96c8a9cd8f3edac28ca` |
| `tested-assessment.tar.gz` | `242e20713c78dd86230e963f7a1842be569b89c80c73e99e244003b01a5df75d` |

Harness invocations accept `security`, `compatibility`, or `consumers`, followed by the brace candidate path, forge candidate path, and original brace package path. Example:

```sh
NODE_PATH=/Users/nathan/Downloads/peso-app/node_modules node \
  /private/tmp/peso-backport-assessment.DVzzxH/assessment.cjs security \
  /private/tmp/peso-backport-assessment.DVzzxH/braces-backport \
  /private/tmp/peso-backport-assessment.DVzzxH/forge-ceba34402e329f0365134f23fe19898756527d65 \
  /Users/nathan/Downloads/peso-app/node_modules/braces
```

Upstream suites used isolated Mocha 11.7.5 with `--no-config --no-package --forbid-only --reporter dot --timeout 30000`, and the source package's `test/*.js` (braces) or `tests/unit/index.js` (forge). Their test tools were installed outside the app with lifecycle scripts disabled.

### Remaining acceptance requirements

Recommend reviewing a reproducible, fail-closed patch installation and verification design before installing either candidate. It must pin provenance and expected originals, reject missing or altered patches and unexpected package paths/versions, run regression tests after clean installs, and retain the raw audit findings. Avoid adopting the entire brace fork or downgrading Expo.

Any evidence-bound change to release audit treatment is a separate security-policy decision requiring Nathan's approval. Hash verification and passing regressions could support review; they do not by themselves satisfy the currently unchanged gate. A plain advisory/version allowlist would not prove patches are installed.

Linux CI and full application build/native tooling compatibility remain unverified. Arbitrary AST width, expansion cardinality, unrelated cryptographic flaws, and all hostile inputs are not proven safe by these bounded checks. Official patch releases remain the preferred retirement path for temporary backports.

No tracked application source or lockfile changed, no commit or push was made, and no provider change occurred during the assessment. PR #47 remains unmerged; deployment and DNS work stay paused.
