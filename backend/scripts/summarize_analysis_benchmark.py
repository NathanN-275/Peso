from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


def _percentile(values: list[int], percentile: float) -> int | None:
  if not values:
    return None
  ordered = sorted(values)
  index = min(max(math.ceil((percentile / 100) * len(ordered)) - 1, 0), len(ordered) - 1)
  return ordered[index]


def _load_json(path: Path) -> dict[str, Any]:
  return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
  parser = argparse.ArgumentParser(
    description="Summarize saved Peso analysis results against the pressing benchmark manifest."
  )
  parser.add_argument(
    "--manifest",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "analysis_benchmark" / "pressing_manifest.json",
  )
  parser.add_argument("--results-dir", type=Path, required=True)
  args = parser.parse_args()

  manifest = _load_json(args.manifest)
  missing: list[str] = []
  failures: list[str] = []
  payload_ready_ms: list[int] = []
  stage_timings: dict[str, list[int]] = {}

  for case in manifest["cases"]:
    result_path = args.results_dir / f"{case['id']}.json"
    if not result_path.exists():
      missing.append(case["id"])
      continue
    result = _load_json(result_path)
    if case["expected_rep_count"] is not None and result.get("rep_count") != case["expected_rep_count"]:
      failures.append(f"{case['id']}: expected {case['expected_rep_count']} reps, got {result.get('rep_count')}")
    timings = result.get("analysis_stage_timings_ms") or {}
    ready = timings.get("analysis_payload_ready")
    if isinstance(ready, int):
      payload_ready_ms.append(ready)
    else:
      failures.append(f"{case['id']}: missing analysis_payload_ready timing")
    for stage, duration in timings.items():
      if isinstance(duration, int):
        stage_timings.setdefault(stage, []).append(duration)

  summary = {
    "missing_cases": missing,
    "failures": failures,
    "target_payload_ready_ms": manifest["target_payload_ready_ms"],
    "payload_ready_p50_ms": _percentile(payload_ready_ms, 50),
    "payload_ready_p95_ms": _percentile(payload_ready_ms, 95),
    "stage_p50_ms": {stage: _percentile(values, 50) for stage, values in stage_timings.items()},
    "stage_p95_ms": {stage: _percentile(values, 95) for stage, values in stage_timings.items()},
  }
  print(json.dumps(summary, indent=2, sort_keys=True))
  if missing or failures or (summary["payload_ready_p95_ms"] or 0) > manifest["target_payload_ready_ms"]:
    return 1
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
