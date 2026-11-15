# Merged-source secret coverage — 2026-10-05

Status: local coverage fix verified; release checkpoint remains blocked.
Parent source: `98bad175cf2025741632244f4dd2da6b9866f87f` (main after PR #47).
This is a local change only, not deployed or hosted-CI acceptance.

## Reproduced failure

Security Checks run 37391108299 passed its secret-scan job, but reported zero
commits and zero bytes. The pinned Gitleaks action constructs:

```text
--no-merges --first-parent 3d0271bfe89cf2436682984ffbbbbe7b1ca3ceaa^..98bad175cf2025741632244f4dd2da6b9866f87f
```

The exact command reproduced locally with Gitleaks 8.30.1: exit 0, zero commits,
zero bytes. The range contains 19 commits when fully traversed. First-parent
selection contains only the merge; excluding merges leaves none. The upstream
action's pinned `src/gitleaks.js` confirms these options for push events.
No repository history was missing for this reproduction.

## Targeted correction

Keep the existing history scan and its exact historical fingerprints. Pin
Gitleaks 8.30.1 and add an independent mandatory committed-source snapshot scan.
The new script archives an exact SHA, records tree/archive/script hashes and
input file/byte counts, and checks extraction against tracked regular files.
It runs from a disposable directory, excluding untracked notes, local secrets,
dependency trees and ignored build outputs.

The snapshot scanner uses explicit default rules, an empty ignore file and
ignores inline allowance comments. It does not inherit local configuration,
historical fingerprints or a baseline. Findings, scanner errors, zero-byte
coverage, invalid/missing reports and inconsistent exit/report results fail
closed. CI checkout must match the selected SHA.

Retained CI evidence contains coverage/provenance and sanitized rule, file and
line identifiers only. Secret/Match values and raw scanner output are not
uploaded. Evidence is retained for 90 days on success or failure; absent files
fail upload. Scanner-reported bytes describe eligible scanned content, not a
claim that every input binary byte was inspected.

This supplements rather than repairs the upstream action's history traversal.
It prevents an empty history scan from being sufficient for this job to pass.
It does not prove coverage of deleted historical secrets, credential rotation,
GitHub cached/retained refs, or Support-ticket completion.

## Verification

- Five focused tests pass on Node 22 and 24, zero failures/skips. Real Git merge/archive fixtures
  exercise merge-only content; scanner-boundary test doubles cover zero/error/
  missing/malformed/contradictory reports and safe evidence retention.
- Separate real Gitleaks integration: old command misses a merge-only synthetic
  token; new snapshot scan detects one finding in 64 scanned bytes and exits 1.
  A clean committed fixture scans 13 bytes and exits 0. Synthetic token is
  generated privately at runtime and is not an issued credential.
- Full frontend policy suite: 284 passed, zero failures/skips, local Node 24.
- Installed dependency verification and `git diff --check` pass; workflow YAML
  parses. Changed scanner/test/evidence-document secret checks are clean.
  Hosted Linux execution (including the configured Node 20 runtime) is pending.
- Frozen consumer scope remains 149 files, SHA-256
  `6bb00beeef8b04023e9bfe30e042bb7f414a2611f88293b10cce0f489e83a242`.
  Audit implementation remains
  `672b8aa5daa03bf35ed06c8eed761c9a2cd95516c2a9bc3b858e87f093ed7170`.
  No audit pin, patch, dependency, exception or expiry changed.

The new scanner against exact merged source scans 8,060,932 bytes, exits 1 and
retains two `generic-api-key` findings: the already-reviewed public Render ID in
`config/combined-web-release-binding.json:7` and
`scripts/release-env.test.js:214`. Neither is an authentication credential, but
the raw failure is not converted into acceptance. No new suppression was added.
Source archive SHA-256:
`4b0e88233069e1965dea3c8648aaffa92541a691a1433cf0d0676e45fc28c67a`.
Sanitized findings SHA-256:
`b89b1b766f499b8682f2a8e2a3d20a9cd254af7bd1351e4ec85932a0e827d378`.
Local evidence is ignored under `artifacts/source-secret-scan/`, not a backup.

## Next blocker and resolution plan

Secret coverage is fixed locally, but scanner acceptance remains blocked by
the two non-secret findings and missing hosted evidence at the new source SHA.

- Review an exact, field/path/value-specific public-ID treatment with real
  credential negative controls; do not add a package-wide or rule-wide ignore.
- Obtain separate authorization to push for hosted checks; inspect nonempty
  coverage and retained evidence at that exact commit. No push occurs here.
- Keep the release checkpoint blocked until combined frontend artifact/Forge
  execution evidence and all other applicable checks are complete.

No provider, database, production binding, dependency, domain terminology or
public visibility changed. The five pre-existing untracked notes are preserved.
