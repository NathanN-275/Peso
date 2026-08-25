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
        {"id": "fast_12fps_640px", "target_fps": 12, "max_frame_dimension": 640},
        {"id": "balanced_15fps_640px", "target_fps": 15, "max_frame_dimension": 640},
        {"id": "current_18fps_720px", "target_fps": 18, "max_frame_dimension": 720},
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
    self.assertEqual(manifest["max_ui_ready_delay_ms"], 4000)
    self.assertTrue(manifest["require_accuracy_gates"])
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

  def test_profile_comparison_uses_declared_order_and_requires_gate_evidence(self) -> None:
    script_path = Path(__file__).parents[1] / "scripts" / "summarize_analysis_benchmark.py"
    spec = importlib.util.spec_from_file_location("analysis_benchmark_order", script_path)
    assert spec and spec.loader
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    manifest = {
      "target_payload_ready_ms": 60000,
      "require_accuracy_gates": True,
      "pose_profiles": [
        {"id": "fast_12fps_640px"},
        {"id": "balanced_15fps_640px"},
        {"id": "current_18fps_720px"},
      ],
      "cases": [{"id": "clip", "expected_rep_count": 3}],
    }

    from tempfile import TemporaryDirectory
    import sys
    from unittest.mock import patch

    with TemporaryDirectory() as root:
      root_path = Path(root)
      profile_directories = []
      for profile_id, passed in (
        ("fast_12fps_640px", False),
        ("balanced_15fps_640px", True),
        ("current_18fps_720px", True),
      ):
        directory = root_path / profile_id
        directory.mkdir()
        (directory / "clip.json").write_text(json.dumps({
          "rep_count": 3,
          "analysis_stage_timings_ms": {"analysis_payload_ready": 50000},
          "benchmark_gates": {"passed": passed},
        }), encoding="utf-8")
        profile_directories.append(f"{profile_id}={directory}")

      arguments = [str(script_path), "--manifest", str(root_path / "manifest.json")]
      (root_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
      for value in profile_directories:
        arguments.extend(["--profile-results", value])
      with patch.object(sys, "argv", arguments), patch("builtins.print") as output:
        exit_code = benchmark.main()

    self.assertEqual(exit_code, 0)
    payload = json.loads(output.call_args.args[0])
    self.assertEqual(payload["recommended_profile"], "balanced_15fps_640px")

  def test_latency_harness_detects_server_and_ui_delivery_regressions(self) -> None:
    script_path = Path(__file__).parents[1] / "scripts" / "check_analysis_latency.py"
    spec = importlib.util.spec_from_file_location("analysis_latency", script_path)
    assert spec and spec.loader
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as directory:
      result_path = Path(directory) / "current_clip.json"
      result_path.write_text(json.dumps({
        "analysis_stage_timings_ms": {"analysis_payload_ready": 62_823},
        "ui_ready_delay_ms": 300_000,
        "benchmark_gates": {"passed": True},
      }), encoding="utf-8")
      failed = harness.evaluate_results([result_path])

      result_path.write_text(json.dumps({
        "analysis_stage_timings_ms": {"analysis_payload_ready": 58_000},
        "ui_ready_delay_ms": 3_999,
        "benchmark_gates": {"passed": True},
      }), encoding="utf-8")
      passed = harness.evaluate_results([result_path])

    self.assertFalse(failed["passed"])
    self.assertTrue(any("server runtime" in failure for failure in failed["failures"]))
    self.assertTrue(any("UI ready delay" in failure for failure in failed["failures"]))
    self.assertTrue(passed["passed"])
