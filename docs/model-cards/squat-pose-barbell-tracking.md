# Squat pose and barbell tracking data/model card

## Status

The data adapters, dataset audits, training/export workflow, identity tracker, and promotion gates are implemented. No new detector or pose backend is approved for production yet because the required human-reviewed Peso labels and five new held-out clips do not exist.

## Canonical targets

- **Hip:** the anatomical hip-joint center defined in `CONTEXT.md`.
- **Barbell target:** the same visible near-side collar throughout a loaded lift, or the same visible near-side sleeve end for an unloaded bar.
- Uncertain identity produces a gap. A smooth point on a plate, rack, J-hook, safety arm, or storage peg is a failure.

## Supplied data

### Azure Kinect FMS skeleton archive

The archive contains 3,624 JSON sequences from 45 subjects. Peso uses only the 540 m01/m02 front/side files: m01 is the primary deep squat and m02 is the heels-elevated stress case. The local audit found 606 missing-body frames and 413 left/right ordering sign changes. The adapter preserves those gaps and marks every result `accuracy_claim_eligible: false` because the attachment contains no matching RGB video or expert-score file.

This corpus may test joint mapping, temporal gaps, segment stability, side identity, and bottom-phase behavior. It must not train or validate RGB keypoint accuracy and must not define loaded-back-squat coaching thresholds. Source: [Functional movement screen dataset](https://doi.org/10.1038/s41597-022-01188-7), [Figshare collection](https://doi.org/10.25452/figshare.plus.c.5774969).

### Roboflow endcap archive

The supplied CC BY 4.0 export contains 13,699 images and one `endcap` class. The reproducible audit found 3,769 source-name families, 252 families crossing the original splits, 30 empty labels, and 840 multi-box images. Dataset preparation groups all augmentations by source family, assigns an 80/10/10 split from a stable SHA-256 bucket, maps the retained class to `barbell_collar`, and quarantines every image that does not contain exactly one box.

The retained 12,829 images are detector-pretraining data only. Single frames cannot prove temporal identity, and automatic filtering cannot prove every published endcap is Peso's collar target. Keep the Roboflow attribution and dataset URL from the supplied `data.yaml` with every derivative.

## Peso ground truth

Use `backend/tests/fixtures/tracking_core/annotation_manifest.template.json`. Dense annotations must cover every pose-sampled active-rep frame with upper back, hip, knee, ankle, visible anatomical side, rep phase, collar center/box, and visible rack hardware. The seven existing clips are development evidence; the five new clips are test-only and must come from unseen recordings.

Never initialize labels from Peso tracker output. CVAT interpolation is allowed only between manually verified keyframes, followed by frame-by-frame review at bottoms, fastest motion, occlusions, and reacquisition.

## Training and artifact policy

1. Build the leakage-safe endcap dataset for pretraining.
2. Convert reviewed Peso CVAT video boxes with source-video splits.
3. Train YOLO11n and YOLO11s at 640 px, first on endcaps and then on Peso's seven classes.
4. Export fixed-shape opset-17 ONNX artifacts and record SHA-256, class order, validation metrics, and training inputs.
5. Select the smallest artifact that passes both tracking modes and stays within 1.10× current CPU latency.

Ultralytics is an offline training dependency only; it is not installed in the production worker. Review Ultralytics licensing and the derivative-model distribution terms before production deployment. Model weights and generated datasets remain outside Git.

## Promotion gates

- Pose: at least 95% labeled-point coverage, p95 normalized error at most 0.05 body heights, 100% visible-side identity accuracy, zero side switches, exact reviewed rep count, and bottom timing within two sampled frames.
- Pin-assisted collar: at least 90% active-rep coverage, p95 at most 10 px, max at most 18 px.
- Automatic collar: at least 90% active-rep coverage, p95 at most 16 px, max at most 26 px.
- Both modes: zero hardware identity switches and no more than 10% CPU latency regression.

Rollout remains `off` → `shadow` → `candidate` with legacy fallback → `apache_v1`. A benchmark recommendation never changes production configuration automatically.
