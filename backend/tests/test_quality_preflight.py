from __future__ import annotations

import unittest

from app.analysis.side_squat.quality_preflight import (
  QUALITY_PREFLIGHT_MODEL_VERSION,
  QUALITY_PREFLIGHT_THRESHOLD_VERSION,
  QualityPreflightThresholds,
  evaluate_quality_observations,
)


def observation(**overrides):
  value = {
    "frameIndex": 0,
    "timestampMs": 0,
    "poseDetected": True,
    "sideViewScore": 0.9,
    "bodyChainVisible": 1.0,
    "subjectHeight": 0.62,
    "feetVisible": 1.0,
    "blurVariance": 120.0,
    "personDetectionCount": 1,
    "secondPersonAreaRatio": 0.0,
    "cameraShiftRatio": 0.005,
    "luminanceMean": 120.0,
    "luminanceStd": 48.0,
  }
  value.update(overrides)
  return value


def evaluate(observations, exercise_type="squat"):
  return evaluate_quality_observations(
    observations,
    exercise_type=exercise_type,
    frame_count=600,
    fps=30.0,
    duration_ms=20000,
    thresholds=QualityPreflightThresholds(sample_count=len(observations)),
  )


class QualityPreflightPolicyTest(unittest.TestCase):
  def test_clear_side_view_passes_with_versioned_sample_metadata(self) -> None:
    result = evaluate([observation(frameIndex=index * 50) for index in range(12)])

    self.assertEqual(result["status"], "pass")
    self.assertEqual(result["modelVersion"], QUALITY_PREFLIGHT_MODEL_VERSION)
    self.assertEqual(result["thresholdVersion"], QUALITY_PREFLIGHT_THRESHOLD_VERSION)
    self.assertEqual(result["sampledFrameMetadata"]["sampledFrameCount"], 12)
    self.assertNotIn("image", str(result["sampledFrameMetadata"]).lower())

  def test_non_side_view_is_blocked_by_its_own_threshold(self) -> None:
    result = evaluate([observation(sideViewScore=0.2) for _ in range(12)])

    self.assertEqual(result["status"], "blocked")
    self.assertEqual(result["checks"]["sideView"]["reasonCode"], "camera_not_side_facing")
    self.assertEqual(result["checks"]["bodyChain"]["status"], "pass")

  def test_intermittent_body_chain_is_blocked(self) -> None:
    observations = [
      observation(bodyChainVisible=1.0 if index < 5 else 0.0)
      for index in range(12)
    ]
    result = evaluate(observations)

    self.assertEqual(result["checks"]["bodyChain"]["status"], "blocked")
    self.assertEqual(result["checks"]["bodyChain"]["reasonCode"], "body_chain_not_visible")

  def test_small_lifter_and_excessive_blur_block_independently(self) -> None:
    result = evaluate([
      observation(subjectHeight=0.2, blurVariance=12.0)
      for _ in range(12)
    ])

    self.assertEqual(result["checks"]["subjectScale"]["reasonCode"], "lifter_too_small")
    self.assertEqual(result["checks"]["motionBlur"]["reasonCode"], "motion_blur_excessive")

  def test_auxiliary_person_detector_blocks_only_sustained_comparable_people(self) -> None:
    isolated_detection = evaluate([
      observation(
        personDetectionCount=2 if index == 0 else 0,
        secondPersonAreaRatio=0.8 if index == 0 else 0.0,
      )
      for index in range(12)
    ])
    ambiguous = evaluate([
      observation(personDetectionCount=2, secondPersonAreaRatio=0.8)
      for _ in range(12)
    ])

    self.assertEqual(isolated_detection["checks"]["multiplePeople"]["status"], "pass")
    self.assertEqual(ambiguous["checks"]["multiplePeople"]["status"], "blocked")
    self.assertEqual(ambiguous["checks"]["dominantLifter"]["status"], "blocked")

  def test_camera_and_lighting_diagnostics_warn_without_overwriting_required_checks(self) -> None:
    result = evaluate([
      observation(cameraShiftRatio=0.08, luminanceMean=20.0, luminanceStd=10.0)
      for _ in range(12)
    ])

    self.assertEqual(result["status"], "warning")
    self.assertEqual(result["checks"]["cameraMovement"]["status"], "warning")
    self.assertEqual(result["checks"]["lighting"]["status"], "warning")
    self.assertTrue(all(result["checks"][name]["status"] == "pass" for name in (
      "sideView",
      "bodyChain",
      "subjectScale",
      "motionBlur",
      "dominantLifter",
      "multiplePeople",
    )))

  def test_goblet_squat_marks_collar_visibility_not_applicable(self) -> None:
    result = evaluate([observation() for _ in range(12)], exercise_type="goblet squat")

    self.assertEqual(result["checks"]["barbellCollarVisibility"]["status"], "not_applicable")


if __name__ == "__main__":
  unittest.main()
