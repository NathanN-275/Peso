from __future__ import annotations

import unittest

from app.analysis.evaluation.azure_kinect_fms import (
  FmsSequenceIdentity,
  adapt_fms_sequence,
  parse_fms_sequence_name,
  summarize_fms_sequence,
)


def body(*, hip_y: float = 700.0) -> dict[str, object]:
  positions = [[0.0, 0.0] for _ in range(32)]
  confidence = [0 for _ in range(32)]
  mapped = {
    5: [900.0, 400.0], 12: [1100.0, 400.0],
    18: [930.0, hip_y], 19: [940.0, 950.0], 20: [945.0, 1200.0],
    22: [1070.0, hip_y], 23: [1060.0, 950.0], 24: [1055.0, 1200.0],
  }
  for index, point in mapped.items():
    positions[index] = point
    confidence[index] = 3
  return {"joint_position_2d_color": positions, "confidence_level": confidence}


class AzureKinectFmsTest(unittest.TestCase):
  def test_only_m01_and_m02_are_accepted(self) -> None:
    identity = parse_fms_sequence_name("front_s01_m01_20210522141451_e1.json")
    self.assertEqual(identity.condition, "primary")
    with self.assertRaises(ValueError):
      parse_fms_sequence_name("front_s01_m03_20210522141451_e1.json")

  def test_adapter_maps_joints_and_preserves_missing_body_gap(self) -> None:
    payload = {
      "frames": [
        {"timestamp_usec": 100_000, "bodies": [body()]},
        {"timestamp_usec": 133_333, "bodies": []},
      ],
      "original_frmae_num": [8, 9],
    }
    adapted = adapt_fms_sequence(
      payload,
      identity=FmsSequenceIdentity("side", "s01", "m02", "20210522141451", "e1"),
    )

    self.assertEqual(adapted["frames"][0]["source_frame_index"], 8)
    self.assertAlmostEqual(adapted["frames"][0]["landmarks"]["left_hip"]["x"], 930 / 2048)
    self.assertEqual(adapted["frames"][1]["landmarks"]["left_hip"]["visibility"], 0.0)
    self.assertFalse(adapted["accuracy_claim_eligible"])

  def test_summary_reports_bottom_and_identity_switches(self) -> None:
    payload = {
      "frames": [
        {"timestamp_usec": 0, "bodies": [body(hip_y=650)]},
        {"timestamp_usec": 33_333, "bodies": [body(hip_y=800)]},
        {"timestamp_usec": 66_666, "bodies": [body(hip_y=660)]},
      ]
    }
    adapted = adapt_fms_sequence(
      payload,
      identity=FmsSequenceIdentity("front", "s01", "m01", "20210522141451", "e1"),
    )
    summary = summarize_fms_sequence(adapted)

    self.assertEqual(summary["bottom_frame_index"], 1)
    self.assertEqual(summary["side_identity_sign_switches"], 0)
    self.assertEqual(summary["joint_coverage"]["left_knee"], 1.0)


if __name__ == "__main__":
  unittest.main()
