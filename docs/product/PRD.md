# Peso Product Requirements Document

**Status:** Beta scope | **Updated:** 2026-08-25

## Product summary

Peso turns a lifting video into inspectable movement evidence and one useful coaching cue. The current release focuses on side-view squat analysis for lifters who train without a coach at every session.

## Problem and vision

Lifters can record a set, but reviewing it frame by frame is slow and subjective. Peso should make the important movement patterns easier to see, explain what the system observed, and give the athlete a practical focus for the next set.

## Users

- **Primary:** self-coached lifters reviewing squat technique.
- **Secondary:** coaches or technically curious athletes who need playback, traces, and saved history.

## Goals for the current beta

1. A user can upload or record a supported squat video from web or mobile.
2. The user receives clear progress while a durable Analysis Job runs.
3. The user can review playback, tracking overlays, rep-level insights, diagnostics, and coaching cues.
4. The user can save a reviewed lift with performed reps, load, unit, and notes.
5. The user can return to active work and saved lifts across web and mobile.
6. Low-quality or unsupported footage produces an honest advisory or limited result.

## Out of scope for this beta

- Treating model-detected reps as the official workout total.
- Promising calibrated physical speed, medical advice, or injury diagnosis.
- Full accuracy for frontal-view analysis.
- Personalized machine-learning coaching before enough verified history exists.
- Social features, coach marketplaces, and multi-athlete accounts.

## Core user journey

`Capture -> Submit -> Quality advisory -> Queue -> Analyze -> Review -> Save or discard -> Revisit history`

### Functional requirements

| ID | Requirement | Acceptance signal |
| --- | --- | --- |
| FR-01 | Authenticate the Peso Account and enforce ownership of uploads and saved lifts. | A user cannot read or mutate another account's data. |
| FR-02 | Accept a supported video and validate size, duration, and usable media. | Invalid submissions explain the problem before or during processing. |
| FR-03 | Persist an Analysis Job independently of the client. | Refreshing, closing the app, or restarting a worker does not lose the job. |
| FR-04 | Show durable public stages: Queued, Downloading, Pose, Barbell Tracking, Saving, Ready, Failed. | Activity can be resumed from web or mobile. |
| FR-05 | Return evidence-aware analysis. | Review includes overlays, rep observations, diagnostics, and confidence limitations. |
| FR-06 | Allow save metadata correction. | Performed Reps and Load remain user-owned workout facts. |
| FR-07 | Keep Saved Lift Library consistent across surfaces. | A web save, edit, export, or deletion is visible on mobile. |
| FR-08 | Preserve safe access to media. | Playback and exports use expiring, owner-scoped access. |

## Non-functional requirements

- **Trust:** uncertain frames remain uncertain; cues must be explainable from visible evidence.
- **Resilience:** queued and processing work survives client and service restarts.
- **Privacy:** uploaded media and analysis results are owner-scoped and not public by default.
- **Performance:** normal analysis should complete within the configured backend timeout budget; the UI must remain usable while work is active.
- **Accessibility:** core submission, review, save, and failure states must be usable with keyboard navigation and readable contrast on web.

## Success measures

- Submission-to-review completion rate for supported side-view squats.
- Analysis failure and limited-result rate, segmented by recording-quality verdict.
- Percentage of completed reviews that are saved.
- Repeat review rate from the Saved Lift Library.
- User corrections to detected reps and recurring tracking failure modes.

## Release roadmap

1. **Beta:** dependable side-view squat workflow, durable jobs, review, save, and history.
2. **Reliability:** improve identity preservation, pin-assisted tracking, quality guidance, and diagnostics.
3. **Expansion:** strengthen frontal analysis and add more exercises only after held-out evaluation supports them.

## Source of truth

This document describes product intent. The [technical design](TDD.md), [readiness review](PRR.md), `CONTEXT.md`, backend README, ADRs, and tests describe implementation and evidence.
