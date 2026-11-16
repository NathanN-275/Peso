# Web UI and analysis flow

Nathan approved this scope on November 15, 2026. Base: merged main `01952ea5`.
Implementation is isolated from the existing working directories and their unrelated edits.
The pending password visibility toggle is included. Hosted publication is a separate decision.

## Behavior

- Desktop and mobile navigation use outline home, barbell, folder and user icons. Settings uses a 24px gear. The collapsed sidebar shows a placeholder square and a separate expand control.
- Upload feedback separates transfer, verification, quality checking and queue submission. Quality warnings still require the user's choice before admission. Server acceptance opens an untimed queue confirmation, with Back to Home and capacity-aware advice about submitting another video.
- Home renders every activity independently. Original filename, thumbnail and queued time identify the lift on Home and its activity page; older media has readable fallback names. Filename lookup is one owner-scoped metadata query, not a storage URL or filesystem path.
- Foreground polling restarts after an empty list receives a new upload. It stops for hidden pages and terminal lists and refreshes on resume. Current, complete and pending stages use server state; elapsed times freeze at terminal timestamps. Failures show the public category and last reached step. Retry follows server permission; deletion keeps its confirmation.
- Web review contains the entire video and uses that same fitted geometry for pose, trails, bar path, reference pins and diagnostics. Labeled Play/Pause and a keyboard-operable timeline remain reachable. Web uses one HTML video with explicit paused source replacement; native review continues using Expo. Private source attachment, bounded renewal and release still apply.
- Loading, failed playback and a confirmed expired playback lease have different copy. A missing source never implies that the recording expired. Confirmed pruned Saved Lifts retain their existing separate treatment.
- Authenticated thumbnails use actual generated video frames with contain sizing. Neutral loading/unavailable states replace the marketing screenshot. The approximately one-second frame is clamped inside short recordings. No manual selector or bulk regeneration runs.

## Measurement and performance decision

Added separate timing events for client transfer, verification, quality checking and queue submission; server receive/storage write/verification download/probe/quality download/evaluation; queue wait from the latest queued timestamp at worker claim; and client readiness observation. Existing pipeline timings cover pose, barbell tracking, saving and asset finalization. Client/server clock skew and network time affect readiness observations; these are diagnostics, not progress percentages or ETAs.

Local benchmark: existing pinned Linux image `peso-web-mvp:a4ae869` (MediaPipe 0.10.30), network disabled, 1 CPU, 2 GiB, identical source fixture and fresh heavy-model pose for each profile. The existing IMG_0013 collar accuracy and 400 MB memory gates were retained. These single-run local results are not hosted latency acceptance or a replacement for the full accuracy/identity corpus.

| Profile | Pose | Barbell | Combined minimum | Peak RSS | Collar gate |
| --- | ---: | ---: | ---: | ---: | --- |
| Current 18 fps / 720px | 47.902 s | 63.050 s | 110.952 s | 352.83 MB | 9/9 labels, pass |
| Balanced 15 fps / 640px | 42.235 s | 42.940 s | 85.175 s | 349.98 MB | 2/9 labels, fail |
| Fast 12 fps / 640px | 36.367 s | 61.449 s | 97.816 s | 357.89 MB | 2/9 labels, fail |

The same read-only 19.338-second clip took 19.495 seconds for the mandatory full-frame metadata probe and 10.947 seconds for 12-sample quality evaluation. The existing quality checker returned `blocked` on this source; that policy was not relaxed. These figures exclude network transfer, storage download and queue wait. Their new timing events require a later approved hosted run for meaningful end-to-end figures.

No candidate satisfies all existing gates and the 60-second target. Keep the current profile; do not promote the faster inaccurate profiles or claim the target is achieved. Verification checks remain intact. No compute upgrade or paid service resumption was performed for these benchmarks.

## Validation and rollout

Automated checks exercise independent duplicate-name activities, empty-to-active polling, hidden/resume, failure categories, permitted retry, private-media expiry and release, thumbnail byte limits and error states, backend ownership and short/rotated media. The offline browser harness runs the real exported app with synthetic Auth/API/media, blocking all other origins. It checks desktop/mobile queue confirmation and reload, full-frame review, actual advancing playback, Play/Pause, keyboard seeking and thumbnails.

The Render test queue was empty and both paid staging services were suspended before the 9:25 PM Eastern deadline. Further hosted acceptance requires a separately approved window and deployment. Do not publish this branch directly to production. Validate the final candidate at the existing `main--peso-webapp.netlify.app` staging address, including real-device portrait, landscape and normalized rotated recordings. Confirm readiness appears within one 4-second poll interval plus request time; do not substitute a timer for server readiness. Preserve existing accuracy, identity, memory and privacy gates.

## Recorded checks

- TypeScript typecheck and dependency integrity verification passed.
- The complete JavaScript policy suite passed: 709 tests. The final focused UI/media/lifecycle suite passed 71 tests after the last source changes.
- Focused backend filename/route/upload/thumbnail/phase tests passed: 92 tests and 16 subtests. Quality-preflight and pipeline fallback checks also passed: 32 tests and 10 subtests. The final worker/queue timing checks passed in the isolated Linux image: 37 tests. macOS cannot deliver the owned process-group signals used by five existing cancellation tests; the matching Linux tests pass.
- Offline Chromium at 1280px and 390px verified separate duplicate-name activities, readiness within one poll interval, queue confirmation and reload, real private thumbnail JPEG bytes, portrait/landscape playback, reachable controls in a short landscape viewport, advancing time, pause, End/Home seeking, contained geometry, reference-pin alignment accurate failed-fetch copy, source cleanup on navigation, grid thumbnails and the password-eye toggle. No external requests were permitted. Browser fixture media uses WebM because the bundled test Chromium lacks H.264 support; real-device H.264 acceptance remains part of staging rollout.
- No hosted deployment, thumbnail backfill or production setting change was performed.

### Offline browser reproduction

From a dependency-installed checkout, export with public synthetic fixture values only:

```sh
EXPO_PUBLIC_WEB_SURFACE=web-app EXPO_PUBLIC_WEB_ROUTER_BASE=/app \
EXPO_PUBLIC_SUPABASE_URL=https://fixture.supabase.co \
EXPO_PUBLIC_SUPABASE_ANON_KEY=fixture \
EXPO_PUBLIC_BACKEND_URL=https://api.fixture.test \
EXPO_PUBLIC_PRIVATE_MEDIA_ENABLED=true \
npx expo export --platform web --clear --output-dir /tmp/peso-ui-fixture
PESO_UI_EXPORT=/tmp/peso-ui-fixture node tests/offline/web-analysis-ui.cjs
```

The harness requires FFmpeg and a Playwright Chromium install. `PESO_CHROMIUM` can select a local executable. Use `--clear` when changing inlined Expo environment variables. The fixture hostnames are intercepted, never contacted. This is not a deployable app artifact.

## Merge verification

The first PR run caught an activity metadata test whose repository mock lacked the new optional filename result, and an existing scanner control whose random value sometimes fell below Gitleaks' detection threshold. The metadata fixture now returns the legacy empty-name map and asserts owner-scoped lookup without media signing. The generic credential control now uses deterministic high-entropy synthetic bytes and explicitly asserts a blocking `generic-api-key` finding. Scanner policy and reviewed occurrence pins are unchanged. The affected backend checks passed 64 tests; all 27 real-Gitleaks integration cases passed.
