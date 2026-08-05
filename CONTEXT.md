# Peso domain glossary

## Marketing Site

The public, statically generated Peso website at `/`, `/privacy`, and `/terms`.
It explains the US web beta and links into the Web App, but it does not share a
client bundle, routing runtime, or authenticated state with the Web App.

## Web App

The browser-only Peso product mounted beneath `/app`. It uses the shared Peso
visual language and will eventually use the same production accounts and Saved
Lifts as mobile, while retaining browser-specific submission and quota rules.
The first milestone is fixture-driven and makes no backend calls.

## Dashboard Home

The signed-in Web App landing surface. It presents the two submission choices,
rolling web capacity, active processing work, pending reviews, and recent Saved
Lifts. Its navigation becomes a full sidebar, compact rail, or bottom bar as the
viewport narrows.

## Web Analysis Job

A server-owned request to analyze one squat video submitted through the Web
App. A job records its owner, video, status, timestamps, attempts, expiry,
failure class, and whether it currently consumes a rolling quota slot. Job state
is not inferred from queue visibility.

## Saved Lift

A user-owned analysis that was explicitly saved after review. Web accepts only
new squat submissions, but all existing Saved Lifts remain readable regardless
of exercise. Performed Reps and Load are workout facts; detected reps remain a
model observation.

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

## Annotation Draft

An unsaved annotation held locally for one Analysis Run. It survives browser
reloads until saved to feedback or explicitly discarded.

## Coaching

The measured interpretation of one exercise video, including detected reps,
technique metrics, and confidence signals.

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
