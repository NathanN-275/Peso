from __future__ import annotations

import json
import importlib.util
import unittest
from pathlib import Path


class AnalysisBenchmarkManifestTest(unittest.TestCase):
  def test_pressing_manifest_covers_every_supported_pressing_view(self) -> None:
    path = Path(__file__).parent / "fixtures" / "analysis_benchmark" / "pressing_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    cases = manifest["cases"]

    self.assertEqual(manifest["target_payload_ready_ms"], 30000)
    self.assertEqual(
      manifest["pose_profiles"],
      [
        {"id": "current", "target_fps": 18, "max_frame_dimension": 720},
        {"id": "balanced_15fps_640px", "target_fps": 15, "max_frame_dimension": 640},
        {"id": "fast_12fps_640px", "target_fps": 12, "max_frame_dimension": 640},
      ],
    )
    self.assertEqual(len(cases), 6)
    self.assertEqual(
      {(case["exercise"], case["view"]) for case in cases},
      {
        ("bench press", "side"),
        ("bench press", "front"),
        ("incline bench press", "side"),
        ("incline bench press", "front"),
        ("overhead press", "side"),
        ("overhead press", "front"),
      },
    )
    self.assertTrue(all(case["duration_seconds"] == 15 for case in cases))

  def test_slow_recording_template_targets_one_minute_for_two_minutes(self) -> None:
    path = Path(__file__).parent / "fixtures" / "analysis_benchmark" / "slow_recording.template.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))

    self.assertEqual(manifest["target_payload_ready_ms"], 60000)
    self.assertEqual(manifest["cases"][0]["duration_seconds"], 120)
    self.assertIsNone(manifest["cases"][0]["expected_rep_count"])

  def test_profile_comparison_selects_fastest_passing_result(self) -> None:
    script_path = Path(__file__).parents[1] / "scripts" / "summarize_analysis_benchmark.py"
    spec = importlib.util.spec_from_file_location("analysis_benchmark", script_path)
    assert spec and spec.loader
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    manifest = {
      "target_payload_ready_ms": 60000,
      "cases": [{"id": "slow_recording", "expected_rep_count": 3}],
    }

    with self.subTest("fast candidate passes"):
      from tempfile import TemporaryDirectory

      with TemporaryDirectory() as directory:
        result_path = Path(directory) / "slow_recording.json"
        result_path.write_text(json.dumps({
          "rep_count": 3,
          "analysis_stage_timings_ms": {"analysis_payload_ready": 54000},
        }), encoding="utf-8")
        summary = benchmark._summarize_results(manifest, Path(directory))

    self.assertTrue(summary["passed"])
    self.assertEqual(summary["payload_ready_p95_ms"], 54000)
