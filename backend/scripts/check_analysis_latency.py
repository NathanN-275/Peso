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


def evaluate_results(
  paths: list[Path],
  *,
  server_budget_ms: int = 60_000,
  poll_interval_ms: int = 4_000,
  require_accuracy_gates: bool = True,
) -> dict[str, Any]:
  failures: list[str] = []
  server_runtimes: list[int] = []
  ui_ready_delays: list[int] = []
  cases: list[dict[str, Any]] = []

  for path in paths:
    payload = json.loads(path.read_text(encoding="utf-8"))
    timings = payload.get("analysis_stage_timings_ms") or payload.get("analysisStageTimingsMs") or {}
    runtime = timings.get("analysis_payload_ready")
    ui_delay = payload.get("ui_ready_delay_ms")
    case_failures: list[str] = []
    if not isinstance(runtime, int):
      case_failures.append("missing analysis_payload_ready timing")
    else:
      server_runtimes.append(runtime)
      if runtime > server_budget_ms:
        case_failures.append(f"server runtime {runtime}ms exceeds {server_budget_ms}ms")
    if not isinstance(ui_delay, int):
      case_failures.append("missing ui_ready_delay_ms")
    else:
      ui_ready_delays.append(ui_delay)
      if ui_delay > poll_interval_ms:
        case_failures.append(f"UI ready delay {ui_delay}ms exceeds {poll_interval_ms}ms")
    if require_accuracy_gates and (payload.get("benchmark_gates") or {}).get("passed") is not True:
      case_failures.append("reviewed accuracy gates did not pass")
    failures.extend(f"{path.stem}: {failure}" for failure in case_failures)
    cases.append({
      "id": path.stem,
      "server_runtime_ms": runtime,
      "ui_ready_delay_ms": ui_delay,
      "passed": not case_failures,
    })

  return {
    "passed": bool(paths) and not failures,
    "server_budget_ms": server_budget_ms,
    "poll_interval_ms": poll_interval_ms,
    "server_runtime_p95_ms": _percentile(server_runtimes, 95),
    "ui_ready_delay_p95_ms": _percentile(ui_ready_delays, 95),
    "failures": failures,
    "cases": cases,
  }


def main() -> int:
  parser = argparse.ArgumentParser(
    description="Check Peso server and UI-ready latency using saved reviewed analysis results."
  )
  parser.add_argument("results", nargs="+", type=Path)
  parser.add_argument("--server-budget-ms", type=int, default=60_000)
  parser.add_argument("--poll-interval-ms", type=int, default=4_000)
  parser.add_argument("--skip-accuracy-gates", action="store_true")
  args = parser.parse_args()
  report = evaluate_results(
    args.results,
    server_budget_ms=args.server_budget_ms,
    poll_interval_ms=args.poll_interval_ms,
    require_accuracy_gates=not args.skip_accuracy_gates,
  )
  print(json.dumps(report, indent=2, sort_keys=True))
  return 0 if report["passed"] else 1


if __name__ == "__main__":
  raise SystemExit(main())
