# Peso domain glossary

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

## Body anchor

A user-selected reference point for one specific shoulder, hip, knee, or ankle
on the lifter's left or right side. Any partial set of body anchors may assist
automatic tracking without changing unpinned joint identities.

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
