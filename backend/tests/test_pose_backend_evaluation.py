from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from app.analysis.evaluation.cvat_pose_annotations import (
  convert_cvat_pose_export,
  inspect_cvat_pose_export,
)
from app.analysis.evaluation.pose_backend_metrics import evaluate_pose_result


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "pose_backend_evaluation"


def _load(name: str):
  return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _cvat_xml(*, ambiguous: bool = False) -> str:
  tracks = []
  track_id = 0
  for label in ("upper_back", "hip", "knee", "ankle"):
    points = "10,20;11,21" if ambiguous and label == "hip" else "10,20"
    tracks.append(
      f'<track id="{track_id}" label="{label}">'
      f'<points frame="0" keyframe="1" outside="0" points="{points}"/>'
      '<points frame="1" keyframe="1" outside="0" points="11,21"/>'
      '</track>'
    )
    track_id += 1
  tracks.append(
    f'<track id="{track_id}" label="rep_bottom">'
    '<points frame="1" keyframe="1" outside="0" points="0,0"/>'
    '</track>'
  )
  return (
    '<annotations><meta><task><name>synthetic</name><source>synthetic.mov</source>'
    '<size>2</size><original_size><width>100</width><height>200</height></original_size>'
    '</task></meta>'
    + ''.join(tracks)
    + '</annotations>'
  )


class PoseBackendEvaluationTest(unittest.TestCase):
  def test_synthetic_contract_separates_proxy_metrics_from_accuracy_claims(self) -> None:
    result = evaluate_pose_result(
      _load("synthetic_pose_result.json"),
      annotations=_load("synthetic_dense_labels.json"),
    )

    self.assertEqual(result["proxyMetrics"]["landmarkAvailability"]["coverage"], 1.0)
    self.assertEqual(result["proxyMetrics"]["confidenceCoverage"]["coverage"], 1.0)
    self.assertEqual(result["proxyMetrics"]["visibleSideIdentityStability"]["sideSwitchCount"], 0)
    self.assertEqual(result["groundTruthMetrics"]["medianNormalizedLabeledPointError"], 0.0)
    self.assertFalse(result["groundTruthMetrics"]["accuracyClaimEligible"])
    self.assertIn("absolute accuracy claim", result["groundTruthMetrics"]["limitation"])

  def test_identity_switches_are_counted_without_calling_them_ground_truth(self) -> None:
    estimation = copy.deepcopy(_load("synthetic_pose_result.json"))
    for index, frame in enumerate(estimation["frames"]):
      side = "left" if index % 2 else "right"
      opposite = "right" if side == "left" else "left"
      for joint in ("shoulder", "hip", "knee", "ankle"):
        source = frame["landmarks"].pop(f"right_{joint}")
        frame["landmarks"][f"{side}_{joint}"] = source
        frame["landmarks"][f"{opposite}_{joint}"] = {**source, "visibility": 0.1}

    result = evaluate_pose_result(estimation)

    identity = result["proxyMetrics"]["visibleSideIdentityStability"]
    self.assertEqual(identity["sideSwitchCount"], 4)
    self.assertEqual(identity["stabilityScore"], 0.0)
    self.assertIn("Proxy metric", identity["note"])

  def test_valid_dense_cvat_points_convert_to_normalized_evaluation_labels(self) -> None:
    with tempfile.TemporaryDirectory() as directory:
      xml_path = Path(directory) / "annotations.xml"
      xml_path.write_text(_cvat_xml(), encoding="utf-8")
      assessment = inspect_cvat_pose_export(xml_path)
      converted = convert_cvat_pose_export(xml_path)

    self.assertTrue(assessment["poseBackendSelectionReady"])
    self.assertEqual(converted["annotation_density"], "dense")
    self.assertEqual(converted["frames"][0]["landmarks"]["visible_hip"]["x"], 0.1)
    self.assertEqual(converted["frames"][0]["landmarks"]["visible_hip"]["y"], 0.1)
    self.assertEqual(converted["frames"][1]["phase"], "bottom_transition")

  def test_ambiguous_multi_point_cvat_shape_is_not_backend_selection_ready(self) -> None:
    with tempfile.TemporaryDirectory() as directory:
      xml_path = Path(directory) / "annotations.xml"
      xml_path.write_text(_cvat_xml(ambiguous=True), encoding="utf-8")
      assessment = inspect_cvat_pose_export(xml_path)

      with self.assertRaises(ValueError):
        convert_cvat_pose_export(xml_path)

    self.assertFalse(assessment["poseBackendSelectionReady"])
    self.assertEqual(assessment["ambiguousMultiPointShapeCount"], 1)
    self.assertIn("point_shapes_contain_multiple_coordinates", assessment["blockingReasons"])

  def test_manifest_template_keeps_backend_selection_disabled_until_review(self) -> None:
    manifest = _load("side_squat_manifest.template.json")
    script_path = Path(__file__).parents[1] / "scripts" / "evaluate_pose_backends.py"
    spec = importlib.util.spec_from_file_location("pose_backend_harness", script_path)
    assert spec and spec.loader
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    harness._validate_manifest(manifest)
    self.assertEqual(manifest["backends"], ["hybrid", "mediapipe", "rtmpose"])
    self.assertFalse(manifest["allow_backend_selection"])
    self.assertEqual(manifest["config"]["target_fps"], 18)

  def test_backend_selection_requires_lower_p95_and_zero_identity_switches(self) -> None:
    script_path = Path(__file__).parents[1] / "scripts" / "evaluate_pose_backends.py"
    spec = importlib.util.spec_from_file_location("pose_backend_harness_selection", script_path)
    assert spec and spec.loader
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)
    manifest = {
      "allow_backend_selection": True,
      "production_backend": "hybrid",
      "backends": ["hybrid", "rtmpose"],
      "acceptance_thresholds": {
        "minimum_visible_joint_coverage": 0.95,
        "max_p95_normalized_error": 0.05,
        "minimum_visible_side_identity_accuracy": 1.0,
        "maximum_side_identity_switches": 0,
      },
    }

    def result(name: str, p95: float, switches: int = 0):
      return {
        "backend": name,
        "status": "completed",
        "wallDurationMs": 100,
        "groundTruthMetrics": {
          "accuracyClaimEligible": True,
          "p95NormalizedLabeledPointError": p95,
          "matchedPointCoverage": 0.98,
          "visibleSideIdentityAccuracy": 1.0,
        },
        "proxyMetrics": {"visibleSideIdentityStability": {"sideSwitchCount": switches}},
      }

    selection = harness.select_pose_backend([
      {"backends": [result("hybrid", 0.045), result("rtmpose", 0.035)]}
    ], manifest)
    blocked = harness.select_pose_backend([
      {"backends": [result("hybrid", 0.045), result("rtmpose", 0.035, switches=1)]}
    ], manifest)

    self.assertEqual(selection["recommendedProductionBackend"], "rtmpose")
    self.assertIsNone(blocked["recommendedProductionBackend"])


if __name__ == "__main__":
  unittest.main()
