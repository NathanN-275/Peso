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


def _nearest_point(
  points: list[dict[str, Any]],
  *,
  time_seconds: float,
  tolerance_seconds: float,
) -> dict[str, Any] | None:
  candidate = min(
    points,
    key=lambda point: abs(float(point.get("time", 0.0)) - time_seconds),
    default=None,
  )
  if candidate is None:
    return None
  return candidate if abs(float(candidate.get("time", 0.0)) - time_seconds) <= tolerance_seconds else None


def evaluate_thresholds(result: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, Any]:
  mode = result.get("mode")
  prefix = "pin_assisted" if mode == "pin_assisted" else "automatic"
  failures: list[str] = []
  checks = {
    "coverage": (
      float(result.get("coverage") or 0.0),
      ">=",
      float(thresholds.get("minimum_active_rep_coverage", 0.90)),
    ),
    "p95_px": (result.get("p95_px"), "<=", thresholds.get(f"{prefix}_collar_p95_px")),
    "max_px": (result.get("max_px"), "<=", thresholds.get(f"{prefix}_collar_max_px")),
    "hardware_identity_switches": (
      int(result.get("hardware_identity_switches") or 0),
      "==",
      int(thresholds.get("hardware_identity_switches", 0)),
    ),
  }
  for name, (actual, operator, expected) in checks.items():
    if actual is None or expected is None:
      failures.append(f"{name}: missing value")
    elif operator == ">=" and float(actual) < float(expected):
      failures.append(f"{name}: {actual} < {expected}")
    elif operator == "<=" and float(actual) > float(expected):
      failures.append(f"{name}: {actual} > {expected}")
    elif operator == "==" and actual != expected:
      failures.append(f"{name}: {actual} != {expected}")
  return {"passed": not failures, "failures": failures, "checks": checks}


def evaluate_clip(clip: dict[str, Any], *, manifest_dir: Path) -> dict[str, Any]:
  result_path = manifest_dir / clip["result_json"]
  label_path = manifest_dir / clip["labels_json"]
  result = _load_json(result_path)
  labels = _load_json(label_path)
  points = (result.get("barbellPath") or {}).get("points") or []
  errors: list[float] = []
  missed = 0
  hardware_switches = 0

  tolerance_seconds = float(clip.get("timestamp_tolerance_seconds", 0.04))
  active_labels = [
    label for label in labels.get("barbell_collar", [])
    if label.get("active_rep", True) is not False
  ]
  for label in active_labels:
    expected_time = float(label.get("time", 0.0))
    actual = _nearest_point(
      points,
      time_seconds=expected_time,
      tolerance_seconds=tolerance_seconds,
    )
    if actual is None:
      missed += 1
      continue
    if actual.get("objectClass") in {"rack_upright", "j_hook", "safety_arm", "storage_peg"}:
      hardware_switches += 1
    error = _distance_px(actual, label)
    if error is not None:
      errors.append(error)

  return {
    "clip": clip.get("id") or clip.get("video") or result_path.name,
    "mode": clip.get("mode", "unknown"),
    "labeled_points": len(active_labels),
    "tracked_points": len(points),
    "missed_labels": missed,
    "coverage": (len(errors) / max(len(active_labels), 1)),
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
  parser.add_argument("--enforce", action="store_true", help="Exit nonzero when any populated clip misses a gate.")
  args = parser.parse_args()
  manifest = _load_json(args.manifest)
  manifest_dir = args.manifest.parent
  clips = manifest.get("clips") or []
  results = [evaluate_clip(clip, manifest_dir=manifest_dir) for clip in clips]
  gates = [evaluate_thresholds(result, manifest.get("thresholds") or {}) for result in results]
  for result, gate in zip(results, gates):
    result["acceptance"] = gate
  summary = {
    "manifest": str(args.manifest),
    "clip_count": len(clips),
    "results": results,
    "thresholds": manifest.get("thresholds") or {},
    "passed": bool(results) and all(gate["passed"] for gate in gates),
  }
  print(json.dumps(summary, indent=2, sort_keys=True))
  return 0 if not args.enforce or summary["passed"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
