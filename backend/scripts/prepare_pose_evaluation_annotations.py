from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.analysis.evaluation.cvat_pose_annotations import (
  convert_cvat_pose_export,
  inspect_cvat_pose_export,
)


def main() -> int:
  parser = argparse.ArgumentParser(
    description="Inspect a CVAT video export and optionally convert evaluation-ready pose labels.",
  )
  parser.add_argument("input", type=Path)
  parser.add_argument("--assessment-output", type=Path)
  parser.add_argument("--labels-output", type=Path)
  parser.add_argument("--minimum-dense-coverage", type=float, default=0.8)
  args = parser.parse_args()

  assessment = inspect_cvat_pose_export(
    args.input,
    minimum_dense_coverage=args.minimum_dense_coverage,
  )
  if args.assessment_output:
    args.assessment_output.parent.mkdir(parents=True, exist_ok=True)
    args.assessment_output.write_text(json.dumps(assessment, indent=2) + "\n", encoding="utf-8")

  if args.labels_output:
    converted = convert_cvat_pose_export(
      args.input,
      minimum_dense_coverage=args.minimum_dense_coverage,
    )
    args.labels_output.parent.mkdir(parents=True, exist_ok=True)
    args.labels_output.write_text(json.dumps(converted, indent=2) + "\n", encoding="utf-8")

  print(json.dumps(assessment, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
