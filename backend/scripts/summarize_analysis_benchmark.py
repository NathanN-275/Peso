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


def _summarize_results(manifest: dict[str, Any], results_dir: Path) -> dict[str, Any]:
  missing: list[str] = []
  failures: list[str] = []
  payload_ready_ms: list[int] = []
  stage_timings: dict[str, list[int]] = {}

  for case in manifest["cases"]:
    result_path = results_dir / f"{case['id']}.json"
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

  summary: dict[str, Any] = {
    "missing_cases": missing,
    "failures": failures,
    "target_payload_ready_ms": manifest["target_payload_ready_ms"],
    "payload_ready_p50_ms": _percentile(payload_ready_ms, 50),
    "payload_ready_p95_ms": _percentile(payload_ready_ms, 95),
    "stage_p50_ms": {stage: _percentile(values, 50) for stage, values in stage_timings.items()},
    "stage_p95_ms": {stage: _percentile(values, 95) for stage, values in stage_timings.items()},
  }
  summary["passed"] = (
    not missing
    and not failures
    and summary["payload_ready_p95_ms"] is not None
    and summary["payload_ready_p95_ms"] <= manifest["target_payload_ready_ms"]
  )
  return summary


def _parse_profile_spec(value: str) -> tuple[str, Path]:
  profile_id, separator, directory = value.partition("=")
  if not separator or not profile_id or not directory:
    raise argparse.ArgumentTypeError("Profile results must use PROFILE_ID=RESULTS_DIR.")
  return profile_id, Path(directory)


def main() -> int:
  parser = argparse.ArgumentParser(
    description="Summarize saved Peso analysis results against an analysis benchmark manifest."
  )
  parser.add_argument(
    "--manifest",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "analysis_benchmark" / "pressing_manifest.json",
  )
  parser.add_argument("--results-dir", type=Path)
  parser.add_argument("--profile-results", type=_parse_profile_spec, action="append")
  args = parser.parse_args()
  if bool(args.results_dir) == bool(args.profile_results):
    parser.error("Pass exactly one of --results-dir or --profile-results.")

  manifest = _load_json(args.manifest)
  if args.results_dir:
    summary = _summarize_results(manifest, args.results_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["passed"] else 1

  summaries = {
    profile_id: _summarize_results(manifest, results_dir)
    for profile_id, results_dir in args.profile_results
  }
  expected_profile_ids = [profile["id"] for profile in manifest.get("pose_profiles") or []]
  missing_profiles = [profile_id for profile_id in expected_profile_ids if profile_id not in summaries]
  eligible = [
    (profile_id, summary)
    for profile_id, summary in summaries.items()
    if summary["passed"]
  ]
  recommended_profile = (
    min(eligible, key=lambda item: item[1]["payload_ready_p95_ms"])[0]
    if eligible and not missing_profiles
    else None
  )
  output = {
    "missing_profiles": missing_profiles,
    "recommended_profile": recommended_profile,
    "profiles": summaries,
  }
  print(json.dumps(output, indent=2, sort_keys=True))
  return 0 if recommended_profile else 1


if __name__ == "__main__":
  raise SystemExit(main())
