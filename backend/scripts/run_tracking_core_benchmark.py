from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any


def _distance_px(actual: dict[str, Any], expected: dict[str, Any]) -> float | None:
  if not all(isinstance(actual.get(key), (int, float)) for key in ("x", "y")):
    return None
  if not all(isinstance(expected.get(key), (int, float)) for key in ("x", "y")):
    return None
  return math.hypot(float(actual["x"]) - float(expected["x"]), float(actual["y"]) - float(expected["y"]))


def _percentile(values: list[float], percentile: float) -> float | None:
  if not values:
    return None
  sorted_values = sorted(values)
  index = min(max(int(math.ceil((percentile / 100.0) * len(sorted_values))) - 1, 0), len(sorted_values) - 1)
  return sorted_values[index]


def _load_json(path: Path) -> dict[str, Any]:
  return json.loads(path.read_text(encoding="utf-8"))


def evaluate_clip(clip: dict[str, Any], *, manifest_dir: Path) -> dict[str, Any]:
  result_path = manifest_dir / clip["result_json"]
  label_path = manifest_dir / clip["labels_json"]
  result = _load_json(result_path)
  labels = _load_json(label_path)
  points = (result.get("barbellPath") or {}).get("points") or []
  points_by_time = {round(float(point.get("time", 0.0)), 3): point for point in points}
  errors: list[float] = []
  missed = 0
  hardware_switches = 0

  for label in labels.get("barbell_collar", []):
    expected_time = round(float(label.get("time", 0.0)), 3)
    actual = points_by_time.get(expected_time)
    if actual is None:
      missed += 1
      continue
    if actual.get("hardwareRejected") is True or actual.get("objectClass") in {"rack_upright", "j_hook", "storage_peg"}:
      hardware_switches += 1
    error = _distance_px(actual, label)
    if error is not None:
      errors.append(error)

  return {
    "clip": clip.get("id") or clip.get("video") or result_path.name,
    "mode": clip.get("mode", "unknown"),
    "labeled_points": len(labels.get("barbell_collar", [])),
    "tracked_points": len(points),
    "missed_labels": missed,
    "coverage": (len(errors) / max(len(labels.get("barbell_collar", [])), 1)),
    "p50_px": statistics.median(errors) if errors else None,
    "p95_px": _percentile(errors, 95),
    "max_px": max(errors) if errors else None,
    "hardware_identity_switches": hardware_switches,
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Evaluate apache_v1 tracking against dense labels.")
  parser.add_argument(
    "--manifest",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tracking_core" / "benchmark_manifest.json",
  )
  args = parser.parse_args()
  manifest = _load_json(args.manifest)
  manifest_dir = args.manifest.parent
  clips = manifest.get("clips") or []
  results = [evaluate_clip(clip, manifest_dir=manifest_dir) for clip in clips]
  summary = {
    "manifest": str(args.manifest),
    "clip_count": len(clips),
    "results": results,
    "thresholds": manifest.get("thresholds") or {},
  }
  print(json.dumps(summary, indent=2, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
