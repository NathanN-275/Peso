# Public Render-ID finding classification proposal — 2026-10-05

Status: **reviewed prototype only; approval required before implementation**.
Reviewed source: `13f12fcb0caeec57be95d9f822004bd5dc6bae82`, branch
`fix/merged-source-secret-coverage`. The active scanner remains unchanged and
fails on the two findings. This proposal does not advance a deployment gate.

## Recommendation and authority boundary

Nathan requested the next review chunk. Recommend a two-occurrence post-scan
classification, not a scanner allowlist or new `.gitleaksignore` fingerprint.
Preserve the scanner's raw exit/counts and sanitized original finding metadata,
then separately record which findings are reviewed non-secret resource IDs and
which remain blocking. A policy acceptance must not be labeled a clean scan.

Render's API addresses resources by `serviceId`; authentication instead uses a
Bearer API key. This establishes different roles, not a blanket safe prefix.
The reviewed ID's exact resource-reference occurrences are the classification
scope; the same text under an authentication field is not in scope.
[Render service API](https://api-docs.render.com/reference/retrieve-service),
[Render authentication](https://api-docs.render.com/reference/authentication).

Gitleaks' report redaction replaces the extracted value. Its fingerprints omit
columns and value identity; a line-level allowance can cover another finding
on that line. Therefore filename, field name, prefix, fingerprint, or redacted
match alone is insufficient. These risks informed the full-file pins below.
See the separate [pinned primary-source review](public-resource-id-primary-source-review-20261005.md)
and [Gitleaks v8.30.1 finding source](https://github.com/gitleaks/gitleaks/blob/v8.30.1/report/finding.go).

No active policy, scanner, workflow, baseline, dependency, expiry, release input,
provider or public visibility changed. No implementation or push is authorized
by the prototype's success. No ADR or domain-glossary change is warranted.

## Exact proposed scope

Only Gitleaks **8.30.1**, `generic-api-key`, exact value
`srv-dak9ohfqj5pc73ac2ga0`, in these committed files and resource-reference
assignments may qualify:

| Path | Line / reported columns | SHA-256 of complete reviewed file |
| --- | --- | --- |
| `config/combined-web-release-binding.json` | 7 / 5–47 | `d2c36edc9d6a72297fec9dce2ea4ff73459dd99f66b7d3f5d28d7ba908f0e822` |
| `scripts/release-env.test.js` | 214 / 6–47 | `ef2d8ba079e855743266032e54a7204141f273adcbe866884e731e4f5bc60fe4` |

The complete source lines must equal the reviewed assignments, including
indentation, quoting and comma. Their UTF-8 SHA-256 hashes, without the line
terminator, are recorded instead of duplicating assignment literals in this note:

| Source line | SHA-256 |
| --- | --- |
| JSON resource reference, line 7 | `989652b57f02f72f851a492ef9a6ac494c797ef2a24c9df55a64c8fdb1ca3f35` |
| Test resource reference, line 214 | `3057af47f29c1e45a9b0f25135916d359468fdaad7ea6d96721d3d51deebc36a` |

Require exact start/end line, reported start/end column, rule, source path,
complete-file hash, source line, `Secret == REDACTED`, and the observed redacted
assignment match. The prototype's observed match strings are
`api_service_id": "REDACTED"` and `api_service_id: 'REDACTED'` respectively.
Do not reinterpret the column values as JavaScript source-string slice offsets:
the upstream coordinates describe the full match in its own byte arithmetic.
The full-file hash and exact source line independently establish value identity.

Implementation must obtain these bytes from the already-verified exact-SHA
archive, never a mutable local file or provider assertion. Keep existing archive
regular-file/symlink guards and fail-closed scanner/report/coverage validation.
Missing, changed, decoded, multiline, malformed or ambiguous evidence does not
qualify. Unsupported report shapes remain blocking, not silently discarded.

Classify every finding independently. No new HIGH/CRITICAL dependency treatment
is involved. Never refresh pins automatically, accept every `srv-*` value,
disable a rule, ignore a file/line, or use an environment assertion to qualify.
Any change to either pinned file requires a new review before its findings can
qualify, including otherwise intended release-binding edits. A scanner upgrade
also requires review. These are byte-bound non-secret classifications, not a
renewal or extension of the braces/Forge dependency treatment; its existing
`2026-10-12T23:59:59Z` expiry remains untouched.

## Evidence requirements for implementation

- Preserve original scanner exit, raw finding count, nonempty byte coverage,
  source/tree/archive/script identities and a sanitized pre-classification
  finding report hash. Retain rule/path/line/columns, not Secret/Match values,
  raw console output, credentials or provider exports.
- Record a separate policy decision, per-finding classification, classified and
  blocking counts, exact reviewed pins and scanner version. A recognized ID
  cannot excuse a sibling finding. Label acceptance as policy acceptance with
  reviewed non-secret findings; raw scanner exit 1 remains recorded.
- Do not alter the independent history job or its existing historical ignores.
  Do not claim credential rotation, GitGuardian, GitHub retained-ref purge,
  combined frontend/Forge exclusion, or release acceptance from this result.
- Turn the reviewed prototype controls into regression tests at the real scanner
  CLI boundary before implementation acceptance. Repeat hosted Linux/Node 20
  verification and retained-evidence inspection on the resulting exact SHA.

## Verification in this review

Private review harness, not loaded by any Peso script/workflow:
`/private/tmp/peso-public-id-treatment-review.KZhP2c/`.
The harness retrieves both pinned files using `git show` at the reviewed SHA,
uses real Gitleaks 8.30.1 with explicit default rules and empty ignores, and
generates unissued synthetic credentials privately at runtime. No credential
bytes or raw provider exports are committed or printed.

Final result: **13 tests passed, 0 failed, no skips**, local Node 24.
The exact two-file baseline scans 12,000 bytes; raw exit 1 / two findings remains
visible, with both classifiable only in the private prototype. Credential-shaped
substitutions (GitHub PAT and generic token), a different `srv-` value, an appended
credential in either file, and a same-line credential all remain blocking.
The same ID under another field or path and even an unrelated byte change also
remain blocking. Changed rule/line/column/match, unredacted metadata, path escape,
invalid/missing reports, another scanner version, zero coverage and a mixed
unresolved finding are rejected by prototype controls.

The first harness run had 12 passes / 1 failed assertion: it incorrectly required
the generic-token substitution's **redacted** Match to differ. Its policy decision
was already blocking because the file hash changed. The assertion was corrected
to require a real generic-rule detection at the modified path. Both attempts are
retained; no active scanner or pin was changed to obtain the final result.

| Retained review evidence | SHA-256 |
| --- | --- |
| `prototype.cjs` | `f9fb0422bfe9a30933d66e3ab09d51975700e27b1141835cb9be96482aa2d5f5` |
| `review.test.cjs` | `388eecbaed2b02110850d93420ff2dcc2f7bc1c2f06398b9be6d4c484fade978` |
| `results.json` | `dfc26b3900a740737bf6bddcb49b5e07786e8f0584428820ded0293f6ea868bb` |
| `results-first-attempt.json` | `993ceba32ee2989dd190aa991de865b8a567c3734ce2f35dd96065f0f9cd37e5` |

The unchanged active scanner was rerun on exact source
`13f12fcb0caeec57be95d9f822004bd5dc6bae82`: **8,080,974 bytes**, exit 1,
two findings, no acceptance. Its archive digest remains
`10d539bf64ce3fff5fa15578c43e901ec6d7494e1c8d11d85c1f392f36103256`;
sanitized findings digest remains
`b89b1b766f499b8682f2a8e2a3d20a9cd254af7bd1351e4ec85932a0e827d378`.
Active scanner SHA-256 remains
`b97c6a8f29c250ca5f3c87f2f48b7699a4d2b7542559888f433abe3363f623fc`.
Temporary evidence is not durable backup or hosted acceptance.

The initial proposal's changed-file secret check also reported two public-ID
findings from literal source-assignment examples copied into the document.
Those examples were replaced by the line hashes above, rather than expanding
the classification to documentation. The initial draft is preserved privately
as `proposal-literal-draft.md`; no ignore or scanner setting changed.

## Next blocker and resolution plan

Nathan's approval of this exact two-occurrence classification is required before
changing the active scanner's policy result.

- Approve or reject this byte-bound, per-finding implementation scope; the raw
  scan stays failed until an approved implementation passes its controls.
- If approved, implement one local chunk with real CLI regression tests and
  retained raw-versus-policy evidence; do not push in that chunk without approval.
- Separately authorize a hosted-check push, then verify the exact SHA's Linux
  results and artifacts. Remaining frontend/Forge and deployment gates still apply.
