# Marketing audit guard — Stage A, first implementation chunk

For Nathan, 2026-10-06 America/New_York. Nathan approved Stage A of the
[bounded proposal](marketing-security-remediation-proposal-20261005.md), including
the audit CLI/evidence and build-runner test seams. This chunk implements only
the independent CLI/evidence boundary and records the cache research. **Stage A
is incomplete; Gate 2/security revalidation remains FAIL.** No later deployment
gate is advanced.

## Changes and purpose

`scripts/npm-audit-web-ci.js` audits the explicit repository `web` tree rather
than caller cwd. It has no root policy imports, allowances or backports. Every
HIGH/CRITICAL finding blocks. Lower findings remain in the full raw report.

The CLI verifies regular, nonsymbolic package/lock paths, matching manifest/lock
declarations, and before/after input hashes. It records commit, tree, dirty state
and executed program hash; CI rejects missing provenance, uncommitted program
bytes, dirty source or a mismatching supplied GitHub execution SHA. It rechecks
source provenance after execution. Dirty local execution is explicitly labeled,
not represented as bytes from its parent commit.

The locked audit explicitly includes prod/dev/optional/peer dependencies. Valid
v2 records require known identities/severities, locked paths, consistent severity
counts, complete dependency totals and grounded advisory identities. Masked
severities, invalid exits, malformed/unknown reports and registry errors fail
closed. Transient failures have at most three attempts, a 45-second process
timeout per attempt, 20-second npm fetch timeout and bounded retry delays.

Unique ignored `artifacts/npm-audit-web/run-*` directories retain each attempt's
exact stdout/stderr bytes and hashes, the final parseable report/hash, and a
separate success/failure decision. Creation is exclusive; redirected, missing or
unwritable evidence cannot pass. Raw registry bodies are not printed to console.
These local ignored files are not durable hosted retention or recovery backups.

TDD exercised the approved public CLI/evidence seam, using real filesystem
fixtures and mocks only for external npm/Git/process boundaries. Red-before-green
slices covered the acceptance path, blocking findings, metadata/identity/path
validation, input/source drift, CI provenance, retries and advisory-free cycles.
Regression fixtures cover every existing root exception's actual package,
version and path; none is accepted by this guard.

The separate [cache review](marketing-cache-applicability-review-20261005.md)
binds the locked source and its Astro consumer and preserves the unresolved HIGH.
The main agent independently reran its embedded locked-library/consumer fixture
with exit 0. Its narrower consumer result is not generated-artifact exclusion,
hosted runtime acceptance, an approved applicability exception or an upstream fix.

## Byte and verification checkpoint

Implementation and verification began at parent source
`3ad4c2a52389849077e8df1458ea5daee3f84ae7`, tree
`8046af6d4000c54c77031c1222d11c6a9ca98984`, with the new files uncommitted.
The final handoff commit identifies the retained implementation, not a claim that
the earlier dirty execution happened at that new commit.

| Final tested file | SHA-256 |
| --- | --- |
| `scripts/npm-audit-web-ci.js` | `6e466e45a912c60bbf2d71a61c704bebe21266a59c2b86f26a123d6d32ee48d2` |
| `scripts/npm-audit-web-ci.test.js` | `5f48f2a666c4b04f65af95d9efaf450a49c6cb63ecf25e87f421b86403ab4a3a` |
| cache research note | `7c7ae2e53b7920752ed16c458a624106b13c2b217fbc03dbdae969da2336b507` |

PASS on Node 24.18.0: `npm run test:policy` **334 passed, zero failed/skipped**,
including 50 new CLI test/subtest entries. `npm run typecheck`, installed patch
verification, both new scripts' syntax checks and whitespace checks passed.
Redacted stdin Gitleaks checks of the two new scripts and research note passed.
These targeted checks do not replace a committed-source/history scan or hosted CI.

The 149-file root frozen scope was independently recomputed unchanged:
`6bb00beeef8b04023e9bfe30e042bb7f414a2611f88293b10cce0f489e83a242`.
Root audit implementation remains
`672b8aa5daa03bf35ed06c8eed761c9a2cd95516c2a9bc3b858e87f093ed7170`.
Root dependency, lock, patch, consumer, advisory and expiry pins were not changed.
Temporary treatment still expires **2026-10-12T23:59:59Z**.

FAIL, as required: registry-enabled read-only execution retained **7 HIGH,
1 CRITICAL, 1 MODERATE**, raw npm exit 1 and guard exit 1. Pre-format execution
evidence is in `artifacts/npm-audit-web/run-nncWFL`, parent SHA/tree above,
`dirty: true`, `scriptMatchesCommit: false`, executed script SHA-256
`a0bcc20a04779716dc2384a0b955ff1543b270e5b50316a0cb3a1c06da7f659f`.
Its raw report SHA-256 is
`1d19ca0390c2859f076fb73bcb27e5899559c64d7bab9c7c1eb2ed19aae03a35`;
decision SHA-256 is
`0a97d7d75ea4c871e32d31ae77d9da6ecde85de4fdc1c58f9a765e6c5ece3cbd`.
This earlier program hash is intentionally distinct from the final formatted
program above. Do not transfer execution identity between them. The initial
sandboxed registry-error attempt also failed and remains separately retained in
`artifacts/npm-audit-web/run-m0DpU4`; it is not vulnerability acceptance evidence.

NOT RUN in this chunk: candidate resolution/install, marketing or combined build,
exact generated-artifact/Forge execution-path analysis, provider/privacy checks,
hosted CI, migration validation, production release or deployment acceptance.
There were no skips in the executed policy suite; unrun gates are not passes.

## Remaining blocker and bounded plan

The guard is **not yet wired into build, CI or release commands**, and unchanged
marketing dependencies still have blocking findings. Cache treatment remains
unresolved even if a future registry report becomes green.

- Continue the approved Stage A build/CI/release enforcement with red-before-green
  tests and retained 90-day CI evidence; keep provider settings unchanged.
- Resolve the approved isolated patched candidate with minimal reviewed lockfile
  changes. Preserve the cache version/blocker; no unapproved lifecycle, override
  or applicability exception is authorized.
- Obtain exact candidate consumer and generated-artifact evidence and, if needed,
  submit a separate cache-resolution proposal to Nathan.
- Stop with exact changed frozen bytes and verification; request separate Stage B
  approval before replacing the current fingerprint. No automatic pin refresh.

The five pre-existing untracked deployment notes remain outside this commit.
No CONTEXT/ADR changes, push, merge, dispatch, provider mutation or public exposure
were performed or authorized by this chunk.
