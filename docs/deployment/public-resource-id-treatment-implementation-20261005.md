# Byte-bound public resource-ID classification — 2026-10-05

Nathan approved the exact [two-occurrence proposal](public-resource-id-treatment-proposal-20261005.md)
before implementation. Parent source: `bc1ff33ff22a096318c8b6545462d1287a883934`,
branch `fix/merged-source-secret-coverage`.

Status: implemented locally; hosted acceptance and the release checkpoint remain
blocked. No push, merge, deployment, provider change or public exposure occurred.
The five pre-existing untracked deployment notes remain untouched.

## Implemented boundary

The source scanner still runs unmodified default Gitleaks 8.30.1 rules, with
empty source-scan ignores and inline allowances disabled. Classification occurs
only after nonempty, valid raw scanner/report evidence is established.

Only the two approved occurrences can qualify. The private classifier requires
the exact rule, path, line and column metadata, redacted finding shape, empty
tags/symlink metadata, approved complete-file hash and source-line hash. It reads
these bytes from the exact-SHA archive, never mutable local files. The approved
pins are unchanged, module-private constants, not caller arguments or environment
assertions. New, changed, decoded, missing, malformed, multiline, ambiguous or
duplicate occurrences cannot inherit classification. Every finding is handled
independently, and one classified ID cannot excuse a blocking sibling.

Any byte change to either approved file invalidates its classification. Intended
release-binding edits and scanner upgrades therefore require a new review.
No prefix, field-name, path-wide or rule-wide exception exists. The history
scanner and its historical ignores remain independent and unchanged.

## Raw-versus-policy evidence

`coverage.json` schema version 2 retains original scanner exit/counts and raw
outcome, nonempty byte coverage, source/tree/archive/script hashes, and hashes
of the transient redacted report, sanitized pre-classification report and
separate policy decision. Existing raw evidence keys are retained.

`findings.json` adds end-line and column metadata to sanitized rule/path/start-line
identifiers. Secret/Match values, raw console output and provider exports are
not retained in uploaded artifacts. Malformed finding records fail closed while
preserving the parsed array's raw finding count and report checksum.

`policy.json` independently records approval reference, exact reviewed pins,
scanner version, per-finding classification, classified/blocking counts and
policy exit. Acceptance with findings is explicitly labeled
`accepted-with-reviewed-nonsecret-findings`, never a clean scan. The CLI prints
both raw and policy results and exits according to policy; errors remain exit 1.
Only a genuinely finding-free raw scan is labeled clean.

The existing always-retain 90-day CI upload includes all three files. The
secret-scan job now exercises the real CLI integration controls after the
existing pinned Gitleaks action installs the scanner. Failure of the independent
history job still fails the job; policy acceptance does not override it.

## TDD and verification

The agreed seams were the scanner CLI and retained evidence. Red-before-green
reproduced raw-only rejection of the approved baseline. A second red case caught
missing raw-count retention on malformed finding metadata; a third caught
acceptance of an unsafe integer byte count. Both now fail closed without losing
known raw evidence or changing approved pins.

Real CLI tests use disposable Git repositories, actual archive extraction and
real Gitleaks 8.30.1. Unissued credential-shaped controls are generated privately
at runtime. Report-corruption tests intercept only the external scanner boundary,
run the real scanner and alter its redacted report; production has no test flag.
Evidence-file assertions use the CLI's documented output seam, not private
classification helpers. Local working-file mutation confirms classification
uses committed archive bytes. A clean fixture confirms no classification is
needed for genuinely zero findings.

Final checks, local macOS:

| Check | Result |
| --- | --- |
| Full policy suite, Node 24.18.0 | 284 pass, 0 fail, no skips |
| Real scanner CLI integration, Node 24.18.0 | 14 pass, 0 fail, no skips |
| Combined scanner controls, Node 22.23.3 | 19 pass, 0 fail, no skips |
| Typecheck / installed dependency verification | exit 0 |
| Frozen scope / audit implementation hashes | unchanged |
| Changed-file secret checks / workflow YAML parse / diff checks | pass |

The 19 scanner controls comprise 14 real CLI tests plus five existing boundary
tests; those five are also included in the policy suite, not additional unique
policy tests. Hosted Linux/Node 20 execution is not yet verified. No new registry
audit, backend/container build, hosted authentication/recovery, migration or
combined frontend artifact acceptance was performed in this focused chunk.

## Pre-commit diagnostic evidence

The final scanner code was run against exact parent source, while implementation
was still uncommitted: 8,098,209 scanned bytes, raw exit 1 / two findings, policy
exit 0 / two reviewed non-secret classifications / zero blockers. This is not
evidence that the parent's committed program contained the new implementation.
Actual scanner implementation SHA-256:
`a66a13009560b10d31d410128d88d65cd9e33e0400b88940382949e7cf586fed`.

Ignored local evidence: `artifacts/source-secret-scan/run-b6yEBo/`.

| Retained file | SHA-256 |
| --- | --- |
| `coverage.json` | `c4b9cdea20bd8ae49e905ca0bc663dc48c845be0ddba9288db7c886cedbfed19` |
| `policy.json` | `562bf45c9d661804556664d84ff44a72c78bb64b78e17ad25c55c6d70cba7ede` |
| `findings.json` | `d528f5b1acb0396abaaf07870b83661f883c6ce433b167b253bf18beaa103fef` |

The post-commit scan must bind the actual resulting source SHA and its archive
to this implementation. Local ignored evidence is not durable backup or hosted
Linux/Node 20 acceptance.

## Unchanged constraints and next blocker

The 149-file frontend consumer scope remains
`6bb00beeef8b04023e9bfe30e042bb7f414a2611f88293b10cce0f489e83a242`.
Audit implementation remains
`672b8aa5daa03bf35ed06c8eed761c9a2cd95516c2a9bc3b858e87f093ed7170`.
No dependency, lockfile, patch, historical ignore or approved occurrence file
changed. Braces/Forge treatment still expires at `2026-10-12T23:59:59Z` with no
automatic renewal. Raw registry HIGH findings and unpatched Forge bundles remain.
No domain terms or hard-to-reverse architecture decision changed.

Next blocker: hosted Linux/Node 20 CI and retained artifacts at the new exact SHA.

- Obtain Nathan's separate approval for a branch push and main-targeted PR to
  run hosted checks. This implementation approval does not authorize a push,
  merge, production deployment or public visibility.
- Inspect every check, failure/skip and raw-versus-policy artifact at that SHA;
  policy acceptance is not full-history purge or GitGuardian evidence.
- Keep the checkpoint blocked until combined frontend/Forge artifact/execution
  evidence and the other applicable release gates are complete. Do not advance
  credential-history or deployment gates based on this local result.
