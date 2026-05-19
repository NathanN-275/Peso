from __future__ import annotations

import unittest

from app.analysis.pose_fallback import analysis_needs_vitpose_fallback


class PipelineFallbackTest(unittest.TestCase):
  def test_clean_analysis_does_not_trigger_fallback(self) -> None:
    self.assertIsNone(
      analysis_needs_vitpose_fallback(
        {
          "diagnostics": {
            "quality_flags": [],
            "depth_status_counts": {
              "hit_depth_count": 3,
              "uncertain_depth_count": 0,
            },
            "pose_validation": {
              "rejected_landmark_count": 0,
              "occluded_landmark_count": 0,
            },
          },
          "reps": [
            {
              "depth_confidence": 0.8,
              "depth_components": {},
            }
          ],
        }
      )
    )

  def test_plate_occlusion_triggers_fallback(self) -> None:
    reason = analysis_needs_vitpose_fallback(
      {
        "diagnostics": {
          "quality_flags": ["plate_rack_occlusion_suspected"],
        },
        "reps": [],
      }
    )

    self.assertEqual(reason, "plate_rack_occlusion_suspected")

  def test_uncertain_depth_triggers_fallback(self) -> None:
    reason = analysis_needs_vitpose_fallback(
      {
        "diagnostics": {
          "depth_status_counts": {
            "uncertain_depth_count": 1,
          },
        },
        "reps": [],
      }
    )

    self.assertEqual(reason, "uncertain_depth")

  def test_low_bottom_confidence_triggers_fallback(self) -> None:
    reason = analysis_needs_vitpose_fallback(
      {
        "diagnostics": {},
        "reps": [
          {
            "depth_confidence": 0.2,
            "depth_components": {},
          }
        ],
      }
    )

    self.assertEqual(reason, "low_bottom_depth_confidence")


if __name__ == "__main__":
  unittest.main()
