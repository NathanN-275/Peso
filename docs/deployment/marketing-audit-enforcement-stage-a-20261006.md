# Marketing audit enforcement — Stage A, second implementation chunk

For Nathan, 2026-10-06 America/New_York. This implements only the approved
build/CI/release wiring in the [Stage A proposal](marketing-security-remediation-proposal-20261005.md).
The prior [guard chunk](marketing-audit-guard-stage-a-20261006.md) is committed at
`139454868d686dc1c84a4d9efa8d2c53407d30f5`, tree
`2fe9cc37b34a92affc38ab1fa45f2e236a6bd890`.
**Gate 2/security revalidation remains FAIL. Stage A is incomplete.**

## What changed and why

- `scripts/build-web.js` executes the independent web audit after its existing
  patch preflight and generated-dist cleanup, inside the existing try/catch,
  before Astro or Expo. A blocked audit leaves no stale or partial output in
  that cleanup path. Only the existing generated `dist` target is cleaned;
  patch-preflight and invalid-mode behavior are unchanged.
- `.github/workflows/security.yml` audits the complete locked web dependency
  tree before all marketing-job builds/exports. A final immutable artifact
  upload runs on success/failure of an attempted audit, retains all wrapper
  audit attempts for a configured 90 days, uses actual execution SHA/run attempt,
  and errors on missing evidence. An earlier install failure does not produce
  an audit pass or pretend an audit ran. Hosted retention remains unverified.
- `scripts/release-verify.js` adds the explicit independent audit immediately
  after unchanged installed-patch and release-configuration gates. Its existing
  serial runner stops before any later export when this audit fails. Root audit,
  secret, runtime, migration and release validators remain independent.

The shared wrapper is reached by both unchanged tracked Netlify commands. No
Netlify context dispatch, config, provider setting, release binding or branch
protection was changed. Source wiring is not proof of live provider enforcement
or privacy. The direct standalone Expo script remains outside this wrapper;
CI reaches its stale-cleanup exercise only after the explicit web audit passes.

## Approved test seams and results

TDD reproduced the missing marketing-build block, missing configured release
stop and missing workflow audit before implementation. Tests use the approved
build-runner, release-runner and workflow-configuration seams. Build subprocess
fixtures run the real patch verifier, real web guard and real marketing-output
verifier with real filesystem state; only external npm/Git are mocked. Astro/Expo
produce synthetic, non-deployable fixture output—not actual frontend artifacts.

PASS on Node 24.18.0:

- Targeted build, release, workflow, Netlify dispatch and dedicated-marketing
  tests: **16 passed, zero failures/skips**.
- Typecheck and unchanged installed braces/Forge patch integrity.
- Changed/new script syntax checks, whitespace checks and redacted stdin
  Gitleaks checks of the six implementation/test/workflow files.

FAIL: full `npm run test:policy`: **343 tests; 335 passed, 8 failed, zero skipped**.
Every failure stops at the unchanged root guard's `Audit consumer scope changed;
a fresh review is required.` These are recorded failures, not passes or skips.
The original fixtures/assertions and pin were not rewritten to hide them.

All failures are in `scripts/npm-audit-ci.test.js`:

| Line | Failing test |
| --- | --- |
| 393 | audit CLI accepts only reviewed backport leaves and labels project-policy acceptance |
| 467 | audit CLI blocks changed advisory metadata and new causes alongside a reviewed leaf |
| 485 | audit CLI does not lend a verified backport to an advisory-free or dangling branch |
| 498 | audit CLI retries a transient registry failure and evaluates the recovered report |
| 554 | audit CLI accepts the final pre-expiry instant but blocks at the approved expiry |
| 561 | audit CLI rechecks expiry before accepting a report evaluated across the boundary |
| 584 | audit CLI blocks real vulnerabilities even after registry recovery |
| 617 | audit CLI retains exact raw output and a decision checksum on success and failure |

## Exact frozen-byte boundary

Only two frozen files changed, both already proposed in Stage A. The scope still
contains 149 files. Approved fingerprint remains
`6bb00beeef8b04023e9bfe30e042bb7f414a2611f88293b10cce0f489e83a242`.
The independently computed **unapproved intermediate** fingerprint is
`cf27b590dc1be86cd69303207157cb4d6c23f3527ff59d68edf48699a9a0945a`.
It was not installed as a pin or represented as a final dependency candidate.

| Frozen file | Before SHA-256 | After SHA-256 |
| --- | --- | --- |
| `scripts/build-web.js` | `e77c8130443d1b2fc80abd6e8fb0535547b414f6ffda13505463d8652b95017a` | `57513037d50b2cb46e2484c2a404ac605c8e0388f836a6bcc6dc45400e9e9234` |
| `scripts/release-verify.js` | `336d1c73e44c26a3a351522a174e29e619589d28e00055b230c8a30b1bcd3b5a` | `5a32309b40ba5d770af96ac6339047e7ff982ffa77b40fe03a3bfa9ec0bd5b03` |

Other tested file hashes:

| File | SHA-256 |
| --- | --- |
| `.github/workflows/security.yml` | `c131d8da50e714c5622afa7d120861b11ae5ef9a6b06cc4d376e4afb02be5c6f` |
| `scripts/build-web.test.js` | `865b670a42e41eec935d57216e447d4188c7b3e22f0f7a0e78f5a1b1ee74644b` |
| `scripts/release-verify.test.js` | `64bfa6eaf4fa2b7b7179f30167f26e835636980fbdc498fb44215026f5d873db` |
| `scripts/marketing-audit-workflow.test.js` | `f9ff0a4e62b8fc8a45b98b5300ad2e61f56a26146eb070d284040afdcaee5da1` |

Root guard remains `672b8aa5daa03bf35ed06c8eed761c9a2cd95516c2a9bc3b858e87f093ed7170`;
web guard remains `6e466e45a912c60bbf2d71a61c704bebe21266a59c2b86f26a123d6d32ee48d2`.
Root/web dependency manifests and lockfiles, patch/verifier/consumer/advisory pins,
and exception expiry were unchanged. Expiry is **2026-10-12T23:59:59Z**.

## Fresh registry failure and newly reported root causes

Read-only root audit evidence: `artifacts/npm-audit/run-lJe3VQ`, source parent
SHA above with tracked dirty state, raw report SHA-256
`f442204c8c25606c5bf4c189773e55de6392283c1dff9d4e0c9dfa4e3847eeec`,
decision SHA-256
`22201e634f48ec05f70f93b974f5c57b0bb03427e702e3e9ef1e6928be8ba581`.
Installed patch verification passed; root guard exit 1 rejected the changed
149-file scope. No temporary treatment acceptance or clean registry audit is claimed.

Raw root totals are **27 HIGH, 8 MODERATE, zero CRITICAL**. Earlier retained
reports had 23 or 25 HIGH, 7 MODERATE and 1 LOW. Root lockfile bytes did not change.
Comparing concrete advisory URLs against both earlier inventories identifies:

| Newly reported root cause | Locked version/path | Raw severity/advisory |
| --- | --- | --- |
| compression | 1.8.1, `node_modules/compression` | HIGH, [GHSA-vc2v-76pw-4v95](https://github.com/advisories/GHSA-vc2v-76pw-4v95) |
| source-map-js | 1.2.1, `node_modules/source-map-js` | HIGH, [GHSA-68fv-2mgg-jv7q](https://github.com/advisories/GHSA-68fv-2mgg-jv7q) |
| postcss-selector-parser | 6.1.2, `node_modules/postcss-selector-parser` | new MODERATE cause, [GHSA-rj75-hqrm-r3gf](https://github.com/advisories/GHSA-rj75-hqrm-r3gf) |

These are findings from the dated npm report, not verified fix targets. They need
a fresh primary-source/locked-consumer review and a separate bounded proposal
before root dependency or root reviewed-input pin changes. The web-only Stage A
approval does not authorize these broader mutations. Scope approval alone cannot
clear these newly reported HIGH causes. No allowance or treatment was broadened.

The prior commit-bound web audit also remains FAIL (7 HIGH, 1 CRITICAL,
1 MODERATE); web dependencies were not changed. Its record is
`artifacts/npm-audit-web/run-qWEZrE/decision.json` at the parent SHA above.
Local ignored evidence is not hosted CI retention or protected backup.

## Stop and next blocker

No actual Astro/Expo candidate build, generated-artifact/Forge execution-path
acceptance, provider/privacy verification, hosted CI, migration/release validation,
push, merge, deployment or public visibility was performed. The root workspace's
existing unbound generated `dist` output was not rebuilt or deleted. The five
pre-existing untracked deployment notes remain excluded and preserved.

- Review the newly reported root causes against primary sources and exact locked
  consumer paths; propose scoped remediation to Nathan before changing root
  dependencies or reviewed-input pins.
- Continue the approved isolated web candidate review without suppressing or
  silently upgrading the unresolved cache dependency.
- Assemble complete dependency/consumer and exact resulting frozen-byte evidence;
  obtain separate Stage B approval only when those bytes are reviewed. Do not
  replace the intermediate fingerprint merely to restore green tests.
- Rerun all failed gates at the eventual reviewed SHA. Hosted enforcement,
  artifact/Forge proof and live privacy remain later mandatory evidence.
