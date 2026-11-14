# Exact public-identifier occurrence review — October 30, 2026

Status: Nathan approved this exact local three-file update on October 30, 2026.
The raw scanner findings remain visible under the separate policy decision. Source reviewed: ccb5719d49e817582b0728d5251da7b2c8666907. No runtime,
migration, provider setting or active scanner has been changed by this review.

## Findings and recommendation

The current exact committed-source scan returns four generic-api-key findings.
The existing byte-bound policy accepts one and blocks three. The same four
findings occur at the previous source f8aa291, so the avatar change introduced
none. One formerly approved Render resource occurrence moved from line214 to215
because release environment tests now exercise build dispatch. Its assignment
line is unchanged, but the complete file changed and its old review correctly
fails closed. The new diff strengthens pending/missing/mismatched release checks.

The other two values are the exact public supabase/auth commit for release2.197.0,
used as an equality comparison in the provider session predicate and as its
synthetic PostgreSQL fixture input. GitHub's primary commit page and authenticated
connector both resolve that exact public revision:
[Supabase Auth release commit](https://github.com/supabase/auth/commit/4eee58f296d9698a1c2c0ae14d7a0b379c7622d3).
It identifies reviewed source. It is not a credential, and its publication does
not prove the managed Auth image/configuration matches it. Keep hosted binding
verification separate. Render resource authentication distinctions are documented
in the [original review](public-resource-id-treatment-proposal-20261005.md).

Recommend retaining the unchanged binding-file occurrence, reviewing the changed
release-test file, and adding only the two exact public-source occurrences. Do
not edit immutable migrations or weaken security assertions to silence a scan.
The prototype has four total pins, two resource IDs and two source revisions.

## Exact proposed bytes

| Path | Line / scanner columns | Complete file SHA-256 | Source line SHA-256 |
| --- | --- | --- | --- |
| backend/tests/test_private_media_grants_postgres.py | 60 / 8–68 | `361c516ab904bf421895eb9804be1b0e3dc70cd618dc216675ddaac38b629909` | `87e743f3b762d33561da389bc8a07b156f36fd23058ec688e851f198a180a262` |
| config/combined-web-release-binding.json | 7 / 5–47 | `d2c36edc9d6a72297fec9dce2ea4ff73459dd99f66b7d3f5d28d7ba908f0e822` | `989652b57f02f72f851a492ef9a6ac494c797ef2a24c9df55a64c8fdb1ca3f35` |
| scripts/release-env.test.js | 215 / 6–47 | `29aed5fca15c211beeedc0e6256e9001d661c577cb66ad6508fd1292fee044a8` | `3057af47f29c1e45a9b0f25135916d359468fdaad7ea6d96721d3d51deebc36a` |
| supabase/migrations/20261026173152_private_media_provider_session_decision.sql | 48 / 12–76 | `fd7e09a635b9e1e4c5cff76f85036077b7bfbfd4cc49e77577e8927bc6152840` | `ed234739ade209f79d29d0794625a67fabffeb8b4810e1f691ad6e95665389a1` |

Only Gitleaks8.30.1 generic-api-key findings qualify. Every finding must match its
path, complete archived file hash, line hash, exact start/end line and columns,
redacted assignment match, empty tags and symlink field, and Secret=REDACTED.
Classification must be one of the two explicit supported values. Unsupported or
missing classification constants fail closed too. No prefix, whole-file ignore,
environment assertion, expiry extension or automatic pin refresh is introduced.
Any changed reviewed file/scanner/coordinates require another review. A public
value copied elsewhere, used in a credential field, replaced with another value,
or accompanied by a credential remains blocking when reported by the scanner.

Raw scanner exit1 and all four original sanitized finding records remain in
evidence. Policy acceptance is separately labeled
accepted-with-reviewed-nonsecret-findings; it is never a clean scan. Other findings,
malformed/missing reports, contradictory exit/counts, zero coverage, unsafe paths,
decoded tags, duplicate occurrences and merge-only secrets retain existing denial.
No historical ignore, rule, workflow permission, dependency or release gate changes.

## Review and validation

An independent reviewer verified public provenance and all four archived file/line
pins. Review found that counting any nonblocking classification could silently
accept an unsupported constant in a later edit. The prototype now validates the
explicit classes at matching and counting, with real-CLI private-script fault
injection confirming missing/unknown classes stay blocking. No production test
flag was added. The initial randomized alternate service ID was not detected by
Gitleaks in one run, so that test now uses a deterministic syntactically identical
alternate value; hash/matcher guards were not loosened. Generated unissued
credential controls remain separate. Initial failed evidence is preserved. Linux tests also exposed a fixture issue:
Docker mounted the generated executable-wrapper directory noexec and PATH fell
through to the real scanner. The isolated trusted test tmpfs now explicitly
allows execution and the helper asserts that the wrapper's scan invocation ran.
This changes no host/provider protection or production scanner setting.

Final test results and exact source/patch hashes are recorded in the adjacent
sealed evidence packet before any approval request. Tests use actual Git archives
and Gitleaks, plus controlled redacted-report corruption at the executable boundary.
Hosted CI results and human release acceptance are not inferred from local checks.

## Authority and rollout

The original approved proposal says: “Any change to either pinned file requires a
new review before its findings can qualify.” Its exact two-occurrence authority
does not automatically cover these additional bytes. Nathan approved
this concrete scanner/integration-test/document update, including its approval
record, for local application and commit. The reviewed prototype evidence is
sealed separately. Install only those files, commit with verification details,
then rerun the exact committed snapshot and retain raw-versus-policy evidence. A later code change to
a pinned file must still block pending another review.

This local policy decision does not authorize a push, production merge, hosted
mutation, public exposure, credential/history purge, paid resume or additional
support message. Gate3 and the full public-beta goal remain open until their
separate credential/provider/retained-ref and release requirements are verified.
