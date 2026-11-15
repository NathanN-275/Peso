# Gate 2 acceptance at the October 28 local checkpoint

Gate 2 passes for release-security/offline-runtime checkpoint
`57f013de0b650b7e5f5bf89ea4d7cc1338c936b3`, under
[ADR 0019](../adr/0019-gate-2-production-security-scope.md) and the accepted
[launch plan](public-beta-launch-plan.md). The docs-only successor rebinds the
same verified runtime inputs. The full public beta goal remains active; the
other thirteen launch gates remain unaccepted. This is not public-launch,
provider/hosted compatibility or protected-release acceptance.

## Native inventory gap resolved

The earlier 46-Wolfi/73-Python report did not inventory the separately compiled
FFmpeg 9.0.1. That review correctly left Gate 2 open. The new Dockerfile installs
signed `ffmpeg-9.0=9.0.2-r8` and removes the custom compile stage/path. The existing
runtime gate now verifies package ownership of `/usr/bin/ffmpeg` and
`/usr/bin/ffprobe`, in addition to version and every existing native/media check.
The actual image scan inventories FFmpeg and seven media libraries at 9.0.2-r8.
No compiler, model, application, migration, feature-flag or audit-policy workaround
was introduced to make a failing check pass.

## Requirement and evidence audit

The parent independently checked raw receipts, all 711 current source hashes,
frontend output/evidence hashes, the full image archive and OCI identities,
actual package inventory and scan report, test logs and current input bindings.
A delegated reviewer hit its usage limit before its final report; no independent
final approval is inferred from preliminary messages.

| Accepted Gate 2 requirement | Verified evidence and scope |
| --- | --- |
| Exact source and reuse bindings | Clean runtime checkpoint above; all 711 source hashes match. All 96 Docker inputs and the current runtime checker/wrapper/WebM fixture match the image test. The prior 64-file frontend output and 103-file evidence inventory were rehashed; the exact four-path native/deployment diff changes no frontend build/typecheck inputs. |
| Lockfiles, patches and enforced dependency policy | Fresh root and web audit decisions bind checkpoint57f013d, exact lockfiles/manifests/patches/verifiers and clean Git trees. Installed patch verification passed. Root has 0 HIGH/CRITICAL, 7 LOW and 4 moderate; web has zero findings. Complete raw reports and hashes agree. No HIGH treatment, exception or expiry renewal is used. |
| Matching image and complete scanner report | Image `sha256:0122e19c01df3b870a128e0e3db8c1ae6d50864238a907fc6a16315ae42744c9`. The full archive, OCI index/platform/config and scan report were rehashed. Scan includes 90 Wolfi and 73 Python packages, including all eight FFmpeg packages, and reports zero findings at every severity. Lower findings in the separate root Node report remain retained. |
| Linux build and runtime identities | Successful pulled linux/amd64 build from a frozen Git archive. Frontend Node24.18.0/npm12.0.2; runtime checker requires MediaPipe0.10.30, protobuf6.33.5 and packaged FFmpeg n9.0.2/9.0.2-r8. Full package versions are retained in the complete image report. |
| API/worker and native inference | Actual image imports API, worker, ONNX Runtime and RTMLib. All three pose models pass their SHA256 checks and positive 33-point inference; missing pose and repeated timestamps pass. Runtime network is disabled, so no model download can hide missing baked assets. |
| Media and supported formats | Existing actual-image check passes preflight, H.264/ffprobe, rotation-aware playback, thumbnail and analyzed export, MOV/MKV probing and VP9 WebM-to-H.264 playback. This is not real-clip tracking equivalence, longest-clip performance or browser codec acceptance. |
| Relevant checks and unchanged enforcement | All441 actual-image cases across32 modules and fresh409 Node policy cases pass. Eighteen related policy cases and syntax passed. TypeScript and the guarded synthetic frontend build/budgets remain applicable through unchanged inputs; they are not claimed as new runs for the native-only change. Existing CI/security jobs are unchanged. |
| Execution safeguards and cleanup | Runtime and image regressions use network-none, nonroot UID/GID10001, read-only filesystem, dropped capabilities, no-new-privileges, bounded tmpfs/resources and explicit read-only synthetic fixtures. No hosted credentials are supplied. Retained commands/configuration enforce that scoped isolation; a boundary snapshot is not presented as continuous hosted-isolation proof. Owned containers are absent after successful checks. |
| Reuse and later release binding | The tested image is identified by exact bytes, not an arbitrary future rebuild. Frontend reuse is bounded to unchanged inputs and the captured output. Later candidate, dependency, image, environment or feature-flag changes require applicable checks/rebinding before release. |

Exact image/archive/scan identities:

- Platform manifest: `sha256:dbb4ca7f3b65ede0c869005dbd469995208bb58c3018b833d723612d3a88f3e8`.
- Configuration: `sha256:a2481a59ffffe77b7faad4838af29f2d909b08c03bad9721711589a88cedac2e`.
- Backend archive SHA256: `428c98aa3a05097b8a4222638ecc8fdcda314a69cdfb229281f231453dd9dda3`.
- Scan report SHA256: `55e8f2376c16880ce255679d50e710426273948e7fc6e30f62948e55798e5a04`.

[Backend evidence](/Users/nathan/.codex/visualizations/2026/10/23/01a16692-8c4a-7f93-a124-c243a95c6eac/gate2-backend-packaged-ffmpeg-20261028-v1/README.md)
contains build/runtime/regressions/native inventory and full scan. The
[checkpoint audit](/Users/nathan/.codex/visualizations/2026/10/23/01a16692-8c4a-7f93-a124-c243a95c6eac/gate2-checkpoint-acceptance-20261028-v1/README.md)
contains the independent raw-verification controller/results and fresh Node
policy/dependency reports. The original gap and failed observer/precondition
attempts remain in their historical evidence; they are not erased or called passes.

## Remaining gates and limits

CI jobs select Node20/22/24 in different scopes. Local Node24 evidence is not a
claim those GitHub jobs ran. Required checks on the protected release SHA remain
Gate13; verified Netlify runtime and a real production-configured build remain
Gate11. No workflow was edited based on an unproved version incompatibility.

Credential/history disposition remains Gate3. Actual provider/Auth/recovery,
backup/migrations, geography, quotas/monitoring, backend cutover and browser/native/
end-to-end acceptance remain their named gates. Media flags stay off.

The [Storage crash counterexamples](private-media-upload-reconciliation.md) still
block provider/cleanup acceptance. Nathan authorized the private support request,
and the provider confirmed submission with optional project/AI access off; no
technical answer or supported cleanup contract has been received. The local
counterexamples do not establish the hosted provider's version or affectedness.
This gate acceptance does not waive those findings or substitute package scans
for erasure proof. Any newly established candidate security impact reopens Gate2.
No public exposure, project mutation, paid resumption, merge or push is authorized
by this local acceptance.
