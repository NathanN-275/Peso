# Gate 2: container and dependency security — September 30, 2026

**Status: PASS for tested source `ed6a44430df5f3e24309c9f3b5016c89158077bc`.**

## Dependency patch

Checkpoint `0997df2f64304ebd163c5b8f513e29b40dbdc83b` failed the frontend
dependency audit in [run 36789141562](https://github.com/NathanN-275/Peso/actions/runs/36789141562).
The new brace-expansion advisories affected locked version 5.0.9:
GHSA-qhr7-859c-m2p7 (HIGH), GHSA-6j4f-fj2g-mc7p (HIGH), and
GHSA-q2hr-2g5m-vwhr (moderate). Expo fingerprint uses it through minimatch 10.

Commit `ed6a44430df5f3e24309c9f3b5016c89158077bc` updates only the root lockfile
entry to compatible patch 5.0.12, including its registry integrity checksum.
No audit exception or severity threshold changed. Existing image-size build-tool
exceptions remain; a passing configured audit does not mean zero npm advisories.

Local audit, TypeScript, all 222 policy tests, combined fixture web build and
bundle budget passed. The fixture build must never be deployed. Startup JS
remains 520,865 gzip bytes and WOFF2 fonts 58,224 bytes, within their budgets.

[Run 36789630513](https://github.com/NathanN-275/Peso/actions/runs/36789630513)
completed successfully and passes container-security, frontend-security,
backend-security (including Python dependency audit),
reservation-database-security, secret-scan and marketing-build on the patched
commit. Production-release-source is intentionally skipped for a PR into main.

## Container acceptance

The CI container job builds from the root Dockerfile, runs the offline non-root
runtime harness against that image, then scans the same local tag with Trivy
v0.74.0. The scan rejects HIGH/CRITICAL findings, including unfixed findings.
The runtime harness checks API/worker imports, all three MediaPipe pose models,
missing pose, quality preflight, H.264, FFprobe, rotation, thumbnails, analyzed
export and MOV/MKV/WebM inputs, with network disabled and a read-only filesystem.

The npm lockfile is excluded by .dockerignore and no backend image input changed
in the patch. The patched commit nevertheless received its own independent image
build, offline runtime test and successful scan in
[job 110139220080](https://github.com/NathanN-275/Peso/actions/runs/36789630513/job/110139220080).

- CI image ID: `sha256:46ec96394e52dd1aaa1d594058d96b5827009463bfa7c05a1c3a3e633a76d20a`.
- Image built at 23:17:54 UTC; offline runtime passed at 23:17:56 UTC with
  UID/GID 10001 and all three pose models.
- Trivy completed at 23:18:15 UTC: zero HIGH/CRITICAL findings across the
  reported Wolfi and Python package targets, including unfixed findings.
- The original checkpoint's independent container test also passed, and Render
  Blueprint/runtime validation run 36789141497 completed successfully. The
  patched commit's separate Render validation is not claimed complete here.

This is the image ID built and tested on the CI runner, not a published registry
digest. No image was published or deployed by this workflow. A later deployment
must retain or rebuild and verify its exact deployable artifact; this successful
scan is not transferable to arbitrary rebuilds. Synthetic smoke checks do not
establish real-clip accuracy, hosted sizing or production acceptance.

Gate 2 required no backend/base-image changes: the repository already contains
the earlier MediaPipe/FFmpeg migration. Stopping after this gate; credential
history remediation is Gate 3 and has not been performed in this chunk.
