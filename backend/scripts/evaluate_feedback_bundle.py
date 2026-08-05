#!/usr/bin/env python3
"""Evaluate one or more exported Peso feedback bundles."""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

from app.analysis.feedback_evaluator import aggregate_feedback_results, evaluate_feedback


def read_bundle(path: Path) -> tuple[dict, dict]:
  with zipfile.ZipFile(path) as archive:
    return (
      json.loads(archive.read("trace.json")),
      json.loads(archive.read("feedback.json")),
    )


def read_manifest(path: Path | None) -> dict[str, dict[str, Any]]:
  if path is None:
    return {}
  payload = json.loads(path.read_text())
  return {str(run["run_id"]): run for run in payload.get("runs", [])}


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("bundles", nargs="+", type=Path)
  parser.add_argument("--replay-manifest", type=Path)
  parser.add_argument("--output", type=Path)
  parser.add_argument("--require-full-coverage", action="store_true")
  args = parser.parse_args()
  manifest = read_manifest(args.replay_manifest)
  results = []
  for bundle in args.bundles:
    trace, feedback = read_bundle(bundle)
    result = {"bundle": str(bundle), **evaluate_feedback(trace, feedback)}
    replay = manifest.get(str(result.get("run_id")))
    if replay is not None:
      result["replay"] = replay
    results.append(result)
  report = {"runs": results, "aggregate": aggregate_feedback_results(results)}
  destination = args.output.open("w") if args.output else sys.stdout
  try:
    json.dump(report, destination, indent=2, sort_keys=True)
    destination.write("\n")
  finally:
    if args.output:
      destination.close()
  return 2 if args.require_full_coverage and report["aggregate"]["unmatched_correction_count"] else 0


if __name__ == "__main__":
  raise SystemExit(main())
