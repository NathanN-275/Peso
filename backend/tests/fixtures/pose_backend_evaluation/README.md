# Side-squat pose backend evaluation

This directory contains contract-only synthetic fixtures. They are not training data and must not be quoted as product accuracy evidence.

## Preparing reviewed labels

Keep source videos and real labels outside Git. In CVAT, annotate one physical visible-side point per shape for each of these labels:

- `upper_back` (compared transparently with the selected shoulder landmark)
- `hip`
- `knee`
- `ankle`
- `rep_bottom` on every reviewed bottom-transition frame

Use one continuing track per physical target. Do not create a new track for each click, and do not place multiple coordinates in one CVAT points shape. For backend selection, each required pose label must cover at least 80% of source frames. Add `visible_anatomical_side` (`left` or `right`) to the converted private JSON when the physical side is known; this term is internal evaluation metadata and is not user-facing copy.

Inspect a CVAT export without writing labels:

```bash
cd backend
PYTHONPATH=. .venv/bin/python scripts/prepare_pose_evaluation_annotations.py /private/annotations.zip
```

Convert only after the assessment reports `poseBackendSelectionReady: true`:

```bash
PYTHONPATH=. .venv/bin/python scripts/prepare_pose_evaluation_annotations.py \
  /private/annotations.zip \
  --assessment-output /private/assessment.json \
  --labels-output /private/pose-labels.json
```

Copy `side_squat_manifest.template.json` outside the repository, replace the private paths, and run both backends on the same clips:

```bash
PYTHONPATH=. .venv/bin/python scripts/evaluate_pose_backends.py \
  --manifest /private/side-squat-manifest.json \
  --output /private/pose-backend-report.json
```

Each backend runs in an isolated CPU subprocess. The report records package/model versions, device, inference and wall duration, peak resident memory, per-frame confidence, fallback events, executed-platform compatibility, proxy stability metrics, and separately labeled ground-truth metrics. The harness never changes the production backend automatically. RTMPose remains benchmark-only until its configured model provenance/licensing is reviewed and a dense corpus satisfies the manifest's evidence gate.
