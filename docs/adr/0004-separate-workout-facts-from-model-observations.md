# ADR 0004: Separate workout facts from model observations

## Status

Accepted

## Decision

Every new saved analysis requires user-entered Performed Reps and Load. These
values are stored on the video and are the official workout facts shown in
saved views and used in Home and Profile totals. Detected Reps remain part of
the immutable analysis result as a model observation and diagnostic.

Legacy saved rows may have null workout facts. Their totals fall back to
Detected Reps until the product provides an explicit backfill or edit flow.

## Context

Rep detection can be incomplete or uncertain because of camera angle,
occlusion, tracking gaps, or model changes. Treating a model estimate as the
user's workout record makes historical totals unstable and obscures tracking
quality.

## Consequences

- `POST /videos/{video_id}/save` requires performed reps, load value, and unit.
- New saves are rejected unless all workout facts are valid.
- Analysis diagnostics can be compared with user-entered facts without
  rewriting either source.
- Saved cards and reviews label performed and detected reps separately.
- Older clients must update before they can save videos.
