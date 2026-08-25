# Peso domain glossary

## Marketing Site

The public, statically generated Peso website at `/`, `/privacy`, and `/terms`.
It explains the US web beta and links into the Web App, but it does not share a
client bundle, routing runtime, or authenticated state with the Web App.

## Web App

The browser-only Peso product mounted beneath `/app`. It uses the shared Peso
visual language, Peso Accounts, and Saved Lift Library as mobile while retaining
browser-specific submission and quota rules. Demo Analysis remains a local
simulation and is distinct from authenticated library activity.

## Peso Account

The user identity shared across Peso web and mobile. An authenticated Peso
Account owns one Saved Lift Library and authorizes access to its lifts and
library actions on either surface.

## Dashboard Home

The signed-in Web App landing surface. It presents the two submission choices,
rolling web capacity, active processing work, pending reviews, and recent Saved
Lifts. Its navigation becomes a full sidebar, compact rail, or bottom bar as the
viewport narrows.

## Analysis Job

A server-owned request to analyze one uploaded lift from mobile or web. Its
durable state continues independently of the client and survives API, worker,
and client restarts. Public stages are Queued, Downloading, Pose, Barbell
Tracking, Saving, Ready, and Failed. Stage timestamps and the worker heartbeat
are durable; percentages are not inferred.

## Analysis Activity

The owner-scoped list of Analysis Jobs that are queued, processing, ready for
review, or failed. It is the user's resumable path back to an unsaved Analysis
Run and is not part of the Saved Lift Library. The client refreshes it on app
or browser resume and polls only while foregrounded work is active.

## Demo Analysis

A client-side Web App simulation used to preview the upload-to-review flow. The
selected video stays on the browser device, its thumbnail is generated locally,
and clock-based queued and analyzing phases produce a bundled fixture result.
A Demo Analysis creates no upload, quota charge, backend request, or durable
record and must not be treated as a server-owned Analysis Job.

## Saved Lift

A user-owned analysis that was explicitly saved after review. Web accepts only
new squat submissions, but all existing Saved Lifts remain readable regardless
of exercise. Performed Reps and Load are workout facts; detected reps remain a
model observation.

## Saved Lift Library

The user-owned collection of Saved Lifts shared across Peso web and mobile.
Changes made to this library on either surface affect the same collection; it is
not a separate web-only demo or copy. The library is source-agnostic: lifts are
not separated or labeled by whether they were created on web or mobile.

## Saved Lift View

A presentation of the same Saved Lift Library. List View uses full-width lift
rows, while Grid View uses square thumbnail cards. Changing the view does not
change library membership, filtering, or selection.

## Saved Lift Selection

A temporary set of Saved Lifts chosen in batch-selection mode for export or
deletion. Selection is an action state, not a persistent property of a lift.

## Saved Lift Export

A single ZIP archive containing exactly the Saved Lifts selected from the
library, with each selected lift included once. A multi-lift export is delivered
as one bundle rather than as a series of separate browser downloads. Each entry
is the standard analyzed video for that lift with its available tracking
overlays included.

## Saved Lift Export Job

A background request that prepares a Saved Lift Export without requiring the
user to remain on the Saved Lifts page. Leaving the page does not cancel the job,
and the completed ZIP remains available until its temporary download expires.

## Saved Lift Deletion

A confirmed, permanent removal of selected Saved Lifts and their videos from the
shared Saved Lift Library. A deletion made on web removes the same lifts from
mobile; it is not a web-only hide or archive.

## Analysis run

A completed processing pass for one source video, producing pose landmarks,
barbell path, rep/depth results, diagnostics, and optional feedback.

## Tracking identity

The specific physical body joint or barbell collar that a path must continue
to represent across frames. A plausible-looking point is invalid if it changes
identity to the opposite-side joint, a plate, rack hardware, or another object.

## Correction

A user-provided point in an exported feedback annotation. Corrections may be
used during one declared tuning pass; the bundle is then frozen as regression
evidence and new clips provide held-out evaluation data.

## Recovery

The process of reacquiring the same tracking identity after an uncertain or
missing observation. Recovery may produce a gap when identity cannot be proven.

## Uncertain frame

A frame whose tracking evidence is insufficient for reliable geometry, depth,
or rep decisions. It must not be treated as a confident observation.

## Recording Quality Advisory

A recording-level assessment that identifies conditions likely to reduce
tracking reliability before an Analysis run. It warns the athlete about risk
without turning uncertain frames into confident observations.

## Frontal squat view

A direct-front through three-quarter camera view used primarily to observe both
knees and ankles. It supports bilateral body tracking and rep counting, but does
not imply that side-view depth or torso judgments are available.

## Hip

The anatomical center of the hip joint used for pose geometry. It is not the
outer hip crease, clothing edge, or visual edge of the pelvis. When that joint
cannot be located without risking an identity switch, the frame is a gap.

## Performed Reps

The rep count entered by the user when saving an analyzed video. It is the
official workout fact used by Home and Profile totals.

## Detected Reps

The rep count observed by the analysis model. It remains a diagnostic in the
review and analysis payload and does not replace Performed Reps on new saves.
Legacy saved rows without Performed Reps may use Detected Reps in totals.

## Load

The non-negative weight entered by the user when saving, represented by a
numeric value and either `lb` or `kg`. Zero is valid for unloaded movements.

## Body anchor

A user-selected reference point for one specific shoulder, hip, knee, or ankle
on the lifter's left or right side. Any partial set of body anchors may assist
automatic tracking without changing unpinned joint identities.

## Tracking reference frame

The user-selected video frame on which body or barbell anchors are placed. Its
timestamp belongs to the same playback timeline as the uploaded source video.

## Visible collar

The barbell collar that can be directly and consistently observed in
three-quarter footage. It is distinct from an inferred bar center.

## Review Projection

The bounded subset of an Analysis Run needed for interactive dashboard review.
It is distinct from the complete trace export.

## Playback Session

The independently loaded signed-video resource used to review an Analysis Run.
It may be refreshed without reloading trace or annotation data.

## Playback Skip

A five-second backward or forward movement within the current Playback Session.
Circular arrow icons represent this time-based skip; they do not navigate
between detected repetitions.

## Annotation Draft

An unsaved annotation held locally for one Analysis Run. It survives browser
reloads until saved to feedback or explicitly discarded.

## Coaching

The measured interpretation of one exercise video, including detected reps,
technique metrics, and confidence signals.

## Lift Insights

The per-repetition measurements presented with an Analysis Run. For each rep,
Lift Insights include duration, rep speed, and average and peak estimated hip
velocity rather than only a set-wide average. The same insights are available
during initial review and when the Saved Lift is reopened later.

## Estimated Hip Velocity

A framing-dependent estimate of hip movement used to compare repetitions within
the same video. It is not a calibrated physical speed and must not be labeled in
meters per second or another real-world distance unit.

## Cue

A short, actionable coaching instruction derived from analysis quality or
technique findings.

## Technique Trend

A change in a user's measured technique across saved videos for the same
exercise and camera view.

## Corrected Reps

The repetition count a user supplies when automatic detection is wrong. In the
current save flow this is represented by the user-owned Performed Reps fact.

## Saved Video

An analyzed video the user has explicitly kept in their workout history.

## Workout Metadata

Optional user-supplied performed reps, load value and unit, and notes attached
to a saved video.
