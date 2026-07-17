# ADR 0002: Version the dashboard and retain drafts locally

## Status

Accepted

## Decision

The local analysis dashboard is versioned with the application. It reads a
bounded review projection rather than the complete trace on initial load.
Unsaved annotations persist in browser-local storage per analysis run; the
existing Save action remains the only server write.

## Context

Complete traces can be tens of megabytes and include data unnecessary for a
frame-by-frame review. Reloading them while a reviewer types can overwrite the
active annotation draft. Server autosave would add write contention to a local
developer tool without improving the feedback export contract.

## Consequences

- Full traces remain available through the existing detail and export paths.
- Dashboard changes, tests, and startup tooling are reviewable in Git.
- Browser-local drafts are best effort and do not appear on another device.
