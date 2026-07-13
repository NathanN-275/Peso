from __future__ import annotations

import json
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
