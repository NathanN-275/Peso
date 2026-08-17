from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from app.analysis.evaluation.azure_kinect_fms import (
  adapt_fms_sequence,
  iter_fms_squat_paths,
  parse_fms_sequence_name,
  summarize_fms_sequence,
)


def audit_root(root: Path) -> dict[str, object]:
  summaries = []
  for path in iter_fms_squat_paths(root):
    payload = json.loads(path.read_text(encoding="utf-8"))
    summaries.append(summarize_fms_sequence(adapt_fms_sequence(
      payload,
      identity=parse_fms_sequence_name(path),
    )))

  by_view: dict[str, int] = {}
  by_movement: dict[str, int] = {}
  subjects: set[str] = set()
  coverage_values: list[float] = []
  for summary in summaries:
    sequence = summary["sequence"]
    view = str(sequence["view"])
    movement = str(sequence["movement"])
    by_view[view] = by_view.get(view, 0) + 1
    by_movement[movement] = by_movement.get(movement, 0) + 1
    subjects.add(str(sequence["subject"]))
    coverage_values.extend(float(value) for value in summary["joint_coverage"].values())

  return {
    "schema_version": 1,
    "source": "Azure Kinect Functional Movement Screen skeleton data",
    "purpose": "kinematic_stress_test_only",
    "accuracy_claim_eligible": False,
    "sequence_count": len(summaries),
    "subject_count": len(subjects),
    "by_view": by_view,
    "by_movement": by_movement,
    "median_joint_coverage": round(statistics.median(coverage_values), 5) if coverage_values else None,
    "missing_body_frame_count": sum(int(summary["missing_body_frame_count"]) for summary in summaries),
    "side_identity_sign_switches": sum(int(summary["side_identity_sign_switches"]) for summary in summaries),
    "sequences": summaries,
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Audit extracted m01/m02 Azure Kinect FMS squat skeletons.")
  parser.add_argument("--root", type=Path, required=True, help="Extracted Skeleton data directory.")
  parser.add_argument("--output", type=Path)
  args = parser.parse_args()
  report = audit_root(args.root)
  rendered = json.dumps(report, indent=2) + "\n"
  if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
  else:
    print(rendered, end="")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
