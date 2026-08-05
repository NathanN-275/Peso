# ADR 0001: Freeze dashboard corrections after one tuning pass

## Status

Accepted

## Decision

Exported dashboard corrections may be used for one declared rule-tuning pass.
After that pass, the bundle is frozen as the regression set. The evaluator
compares corrected points with replayed analysis output and reports error,
coverage, gaps, recovery, and identity-switch metrics. Corrections are not
silently used for model training.

## Context

The feedback bundles identify recurring pose identity swaps and barbell drift.
They can target this initial repair, but continued tuning against the same
clips would hide regressions.

## Consequences

- The current tuning pass must record its results before the bundles freeze.
- Later tracking changes must be measured against the annotated runs before release.
- Missing output is reported as missing evidence, not zero error.
- Training or fine-tuning requires a separately approved dataset split.
