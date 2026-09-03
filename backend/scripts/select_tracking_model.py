from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MODEL_ORDER = {"yolo11n": 0, "yolo11s": 1}


def candidate_gate(candidate: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, object]:
  failures: list[str] = []
  baseline_latency = float(candidate.get("baseline_latency_ms") or 0.0)
  candidate_latency = float(candidate.get("latency_ms") or 0.0)
  if baseline_latency <= 0 or candidate_latency <= 0:
    failures.append("latency evidence is missing")
  elif candidate_latency > baseline_latency * float(thresholds.get("maximum_latency_ratio", 1.10)):
    failures.append("CPU latency exceeds the allowed regression")

  tracking = candidate.get("tracking") or {}
  for mode, prefix in (("pin_assisted", "pin_assisted"), ("automatic", "automatic")):
    metrics = tracking.get(mode) or {}
    if float(metrics.get("coverage") or 0.0) < float(thresholds.get("minimum_active_rep_coverage", 0.90)):
      failures.append(f"{mode} coverage is below threshold")
    if metrics.get("p95_px") is None or float(metrics["p95_px"]) > float(thresholds[f"{prefix}_collar_p95_px"]):
      failures.append(f"{mode} p95 error exceeds threshold")
    if metrics.get("max_px") is None or float(metrics["max_px"]) > float(thresholds[f"{prefix}_collar_max_px"]):
      failures.append(f"{mode} max error exceeds threshold")
    if int(metrics.get("hardware_identity_switches") or 0) != int(thresholds.get("hardware_identity_switches", 0)):
      failures.append(f"{mode} has hardware identity switches")
  return {"passed": not failures, "failures": failures}


def select_tracking_model(report: dict[str, Any], thresholds: dict[str, Any]) -> dict[str, object]:
  assessed = []
  for candidate in report.get("candidates") or []:
    gate = candidate_gate(candidate, thresholds)
    assessed.append({**candidate, "acceptance": gate})
  eligible = [candidate for candidate in assessed if candidate["acceptance"]["passed"]]
  selected = min(
    eligible,
    key=lambda candidate: (
      MODEL_ORDER.get(str(candidate.get("variant")), 99),
      float(candidate.get("latency_ms") or float("inf")),
    ),
    default=None,
  )
  return {
    "selected_variant": selected.get("variant") if selected else None,
    "selected_artifact": selected.get("artifact") if selected else None,
    "status": "promotion_ready" if selected else "no_candidate_passed",
    "candidates": assessed,
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Select the smallest YOLO11 artifact that passes tracking gates.")
  parser.add_argument("--report", type=Path, required=True)
  parser.add_argument("--thresholds", type=Path, required=True)
  args = parser.parse_args()
  report = json.loads(args.report.read_text(encoding="utf-8"))
  manifest = json.loads(args.thresholds.read_text(encoding="utf-8"))
  selection = select_tracking_model(report, manifest.get("thresholds") or manifest)
  print(json.dumps(selection, indent=2))
  return 0 if selection["selected_variant"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
