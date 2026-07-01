# Pin-Assisted Barbell Tracking Work Summary

Updated: June 16, 2026

## Goal

Make barbell path tracking stay attached to user-selected near-side collar center throughout squat videos.

Required behavior:

- Single pin defines exact collar target.
- Pin-assisted mode should outperform automatic mode.
- Tracker must not jump to plate center, rack hardware, wrist, or another circular object.
- Brief uncertainty should create missing path point instead of wrong point.
- Automatic tracking should remain stable when no pin is supplied.
- Displayed marker should be smooth without visible lag or losing exact reference pin.

Target acceptance metrics:

- Reference pin error: at most 2 px.
- Pin-assisted p95 error: at most 8 px; max 14 px.
- Automatic p95 error: at most 12 px; max 18 px.
- No wrong plate/rack identity switches.
- At least 90% in-rep coverage when target remains visible.
- Rendered UI marker within 2 px of backend point.

## Reported Problem

Two June 15 screen recordings showed:

- Pin-assisted tracking drifting from selected collar and sometimes following wrong plate region.
- Automatic tracking performing better than pin-assisted mode, but still showing offset and jitter.
- Pin path changing from user-selected target to visual detector target after first frame.

Main causes found:

1. Generic KLT feature translation could follow coherent plate/background texture instead of exact pin.
2. Manual tracker replaced valid pin trajectory with detected hub/collar coordinates.
3. Manual-assisted points bypassed smoothing.
4. Sequential outlier filtering could accept first moderate spike and reject recovery.
5. Manual/automatic switching lacked explicit hysteresis and detailed diagnostics.

## Committed Work

Commits:

- `b9f92ed` (`Refactor app state and UI flows`)
- `7e57f8f` (`Refine manual barbell recovery and debug frame writing`)

These commits contain current pin-tracking implementation and UI work.

### Pin Setup and Review UI

- Added complete single-frame pin setup for upper back, hip, knee, ankle, and barbell. The upper-back pin is stored under the legacy `shoulder` key for compatibility.
- Added reference timestamp and normalized anchor payload.
- Added selected-side resolution based on pinned body chain.
- Added reference pin overlay during review near saved reference timestamp.
- Added tracking-state display for reference, guided, automatic, and estimated points.
- Added pin capability/preflight policy and upload payload support.

Key files:

- `src/components/TrackingPinSetupModal.tsx`
- `src/components/TrackingReferenceOverlay.tsx`
- `src/components/BarbellPathOverlay.tsx`
- `src/components/PoseOverlay.tsx`
- `src/screens/AnalysisReviewScreen.tsx`
- `lib/trackingOverlayPolicy.js`

### Manual Body and Barbell Tracking

- Tracks anchors forward and backward from selected reference frame.
- Barbell anchor uses local feature tracking around selected collar.
- Added affine/RANSAC motion estimation and local template validation.
- Preserves reference pin exactly.
- Added body-chain validation and whole-chain fallback handling.
- Added two-frame re-entry requirements after rejected manual tracks.
- Propagates selected side through pose validation, squat analysis, and barbell tracking.

Key files:

- `backend/app/analysis/manual_tracking.py`
- `backend/app/analysis/pose_validator.py`
- `backend/app/analysis/exercises/squat.py`
- `backend/app/analysis/pipeline.py`

### Barbell Tracker Fusion

- Manual collar prior is authoritative while plausible.
- Visual plate/hub detector validates pin trajectory instead of immediately replacing it.
- Consecutive disagreement is required before fallback.
- Consecutive agreement is required before manual re-entry.
- Wrong or uncertain targets can produce gaps rather than synthetic points.
- Added source-state and rejection diagnostics.

Key file:

- `backend/app/analysis/barbell_tracking/tracker.py`

### Smoothing and Outlier Handling

- Added centered temporal outlier detection so one spike does not poison later points.
- Added confidence-weighted symmetric smoothing.
- Reference point remains unchanged.
- Manual and automatic smoothing displacement is capped.
- UI interpolation preserves tracking state and refuses long gaps.

Key files:

- `backend/app/analysis/barbell_tracking/postprocess.py`
- `src/utils/videoReview.ts`

### Diagnostics

- Debug frames can show raw pin, calibrated visual target, final emitted point, state, residual, and rejection reason.
- Added counters for manual accepted/blended/rejected/fallback points.
- Added visual mismatch residuals, source switches, coverage, and per-rep gaps.
- Debug MP4 writer now supports odd processed dimensions by exporting even-sized frames.

Key files:

- `backend/app/analysis/barbell_tracking/debug.py`
- `backend/app/analysis/barbell_tracking/results.py`
- `backend/scripts/run_img0012_tracking_regression.py`

## Latest Recovery Work

Commit `7e57f8f` updated:

- `backend/app/analysis/barbell_tracking/tracker.py`
- `backend/app/analysis/manual_tracking.py`

Latest changes add/refine:

- Visual detector offset calibration against exact reference pin.
- Calibration only at explicit reference frame when reference metadata exists.
- `manual_visual_mismatch_streak` and `manual_visual_match_streak` hysteresis.
- Visual recovery state after two consecutive pin/visual mismatches.
- Return to pin-guided state after two consecutive matches.
- Missing point when recovery has no valid visual target.
- Automatic tracking state while visual recovery is active.
- Debug diagnostics for raw pin, raw visual point, calibrated visual point, residual, and recovery state.
- Valid debug MP4 output for odd-width videos.
- Type annotations updated because manual tracks now carry diagnostics beyond numeric coordinates.

## June 16 Targeted Drift and Keypoint Fixes

Current uncommitted backend changes:

- Visual-to-pin calibration is now explicitly one-time. When reference metadata exists, only the `reference` prior can establish `visual_to_pin_offset = pin - raw_visual`; guided frames cannot recalibrate it. Legacy first-visible calibration remains only when no explicit reference prior exists.
- Recovery now has an explicit final safety gate using existing collar descriptor, hub safety, geometry, and confidence thresholds.
- Unsafe recovery frames append `None`, stay in reacquiring mode, write debug/diagnostic data, and do not update accepted path history.
- Recovery diagnostics now include raw pin, raw visual, calibrated visual, offset, offset source/frame, residual, match/mismatch streaks, active state, emitted-versus-gap state, and rejection reason.
- Missing-sample handling now interpolates only one or two ordinary interior gaps. Leading, trailing, three-or-more-frame, manual recovery, and local identity-risk gaps remain absent.
- Interpolated points use linear time/position, conservative confidence, `estimated` tracking state, and no manual-assisted flag.
- Added `MAX_JOINT_DISPLACEMENT_PX = 15` for upper back, hip, knee, and ankle optical-flow tracks.
- Joint proposals beyond 15 px reuse the previous valid coordinate, reduce confidence, log at DEBUG level, and store per-point distance/cap diagnostics.
- Tracking-assistance diagnostics now expose total and per-joint velocity-cap counts.

Changed files:

- `backend/app/analysis/barbell_tracking/tracker.py`
- `backend/app/analysis/barbell_tracking/postprocess.py`
- `backend/app/analysis/manual_tracking.py`
- `backend/app/analysis/pipeline.py`

## June 17 Pin-First Barbell Path Work

Current uncommitted backend changes added on top of the June 16 fixes:

- Added a pin-assisted primary path builder that uses the existing manual barbell ROI/KLT/template track as the authoritative `barbellPath` when a reference barbell pin exists and coverage is sufficient.
- `BarbellTracker.track()` now returns the pin-assisted ROI path before running automatic plate/collar tracking, so valid pin output is no longer replaced by automatic visual coordinates.
- Short missing pin runs are emitted as low-confidence `trackingState: "estimated"` points with no `manual_assisted` flag.
- Long missing pin runs remain gaps and are counted in diagnostics.
- Automatic/no-pin tracking behavior is left on the existing path.
- Added diagnostics for `reference`, `pin_roi`, `pin_estimated`, `visual_reacquired`, `automatic_fallback`, and `gap` source counts.
- Added regression tests proving the pin path owns output, automatic visual replacement is bypassed, short gaps become estimated points, and long gaps remain gaps.

Additional changed files:

- `backend/app/analysis/barbell_tracking/pin_tracker.py`
- `backend/tests/test_barbell_tracker.py`

## Verification Completed

Passing checks:

- `184` backend tests: passed.
- `70` focused manual/barbell tracking tests after final edits: passed.
- `28` JavaScript policy tests: passed.
- `npx tsc --noEmit`: passed.
- `git diff --check`: passed.
- Debug MP4 generation with odd processed dimensions: verified.
- June 16 direct probes: reference offset sign/source, unsafe recovery gap, short/long/blocked interpolation, and 20 px joint velocity cap passed.

Important regression coverage includes:

- Manual pin remains exact instead of switching to visual hub.
- Coordinated manual drift rejection.
- Two-frame manual re-entry.
- Wrong rack and J-cup distractors.
- Local tracking when fresh circle detection drops out.
- Moderate centered spike removal.
- Manual jitter smoothing with exact reference preservation.
- Real automatic `IMG_0013` collar labels across three reps.
- Real `IMG_0012` manual anchor tracking coverage.

## Known Limitations

- `IMG_0012` has only four trusted manually labeled barbell points. Dense labels were not invented from tracker output.
- Raw manual optical flow on `IMG_0012` can drift about 31 px after reference frame. The current uncommitted calibration/recovery changes prevent unsafe visual replacement, but dense labels are still needed to quantify the corrected path.
- Full `run_img0012_tracking_regression.py` cannot run in current headless macOS environment because MediaPipe fails to initialize OpenGL (`kGpuService` / `NSOpenGLPixelFormat`).
- Screen-recording review proves visible drift qualitatively, but recordings are not source-video ground-truth fixtures.
- Acceptance metrics above are goals; dense labeled pin-assisted fixture is still required to prove p95/max error.

## Next Work

1. Run app end-to-end on original source video with current uncommitted recovery and joint-cap changes.
2. Record pin-assisted and automatic outputs using same clip and same playback timestamps.
3. Confirm calibrated visual recovery stays on exact near-side collar and never selects rack hardware.
4. Add dense manual labels for ascent, descent, bottoms, tops, fastest movement, and occlusions.
5. Calculate p50, p95, max error, coverage, and identity-switch count for both modes.
6. Tune mismatch tolerance and recovery thresholds only from labeled errors, not appearance alone.
7. Commit further threshold or recovery changes only after end-to-end visual verification.

## Suggested Skills

- `diagnose`: reproduce and measure remaining drift against dense labels.
- `tdd`: add failing labeled regression before threshold changes.
- `caveman`: keep communication terse during iteration.

## Useful Commands

```bash
cd /Users/nathan/Downloads/peso-app/backend
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest tests.test_manual_tracking tests.test_barbell_tracker
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests

cd /Users/nathan/Downloads/peso-app
node --test scripts/*.test.js
npx tsc --noEmit
git diff --check
git status --short
```

## Current Git State

- Branch: `tracking-pins`
- HEAD: `7e57f8f`
- Remote branch currently shown at: `5f87912`
- Tracking implementation is committed locally.
- Worktree contains this untracked summary plus uncommitted backend changes in tracker, postprocessing, manual tracking, and pipeline diagnostics.
