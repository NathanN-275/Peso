# Public beta candidate CI — September 23, 2026

Candidate: `901358063ab16c438ee246805bcaac740272b3c5`.
[PR #47](https://github.com/NathanN-275/Peso/pull/47) is open as a draft against
`main`. GitHub CLI authentication and branch push succeeded. Earlier reports
that CLI authentication prevented PR creation are superseded by this checkpoint.
No merge, public launch, paid service resumption or hosted migration occurred.

## Completed checks

[Security Checks run 35912588527](https://github.com/NathanN-275/Peso/actions/runs/35912588527)
completed successfully:

- Backend: 528 tests run, 20 skipped; Python dependency audit reported no known
  vulnerabilities; static Supabase migration/RLS audit passed. Skipped tests are
  not evidence of live acceptance.
- PostgreSQL integration: 18 tests passed in the separate database job.
- Frontend: typecheck and all 222 policy tests passed; configured Node dependency
  audit passed, subject to the repository's existing documented exceptions.
- Gitleaks and GitGuardian passed. Gitleaks retains the two exact non-secret
  service-ID fingerprints in `.gitleaksignore`; this is not a complete semantic
  application-security review.
- Root Docker image built; offline, read-only, non-root runtime checks passed
  with UID/GID 10001, no network and three packaged pose models. Checks cover
  API/worker imports, positive/missing pose, quality preflight, H.264, ffprobe,
  rotation, thumbnails, analyzed export and MOV/MKV/WebM inputs.
- Trivy's configured high/critical vulnerability gate passed.
- Clean marketing build and stale app-bundle cleanup checks passed.

[Render Beta Release Validation run 35912588499](https://github.com/NathanN-275/Peso/actions/runs/35912588499)
also completed successfully. Pinned Render CLI 2.28.0 authenticated validation
returned `valid: true` for both `render-beta.yaml` and
`render-public-beta.yaml`; policy tests, typecheck, backend tests, container build
and offline runtime checks passed. This supersedes the earlier schema-only
validation limitation. It does not apply or sync either Blueprint.

The staging migration-preview job was skipped by its workflow condition. It did
not inspect or change PesoDatabase. `production-release-source` was correctly
skipped because this draft targets `main`, not `production`.

The historical `peso-webapp` deploy-preview, header and redirect checks passed.
This is not evidence for the new combined project's build or access controls:
`config/combined-web-release-binding.json` remains pending.

## Remaining launch gates

CI does not establish live PesoDatabase migrations, backup/restore, two-user RLS,
US-IP enforcement, billing collection/alert delivery, intake-stop activation,
cleanup scheduling, accepted-job draining, desktop/phone end-to-end acceptance,
Starter benchmarks, email delivery, legal acceptance, or Nathan's launch approval.
The application-security review recorded in the September 22 security checkpoint
also remains incomplete. Keep the release at NO-GO until these are verified.

The original source PDF must be available again for a final requirement-by-
requirement audit. Its previously supplied path is currently missing.
