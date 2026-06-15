from __future__ import annotations

import json
import math
from pathlib import Path

from app.analysis.barbell_tracking.tracker import BarbellTracker
from app.analysis.manual_tracking import (
  barbell_track_priors,
  fuse_manual_body_tracks,
  track_manual_anchors,
)
from app.analysis.pose_estimator import PoseEstimator, PoseEstimatorConfig
from app.analysis.pose_validator import validate_squat_pose_frames


def main() -> None:
  backend_root = Path(__file__).resolve().parents[1]
  fixture = json.loads(
    (backend_root / "tests" / "fixtures" / "manual_tracking_img0012_reference.json").read_text()
  )
  video_path = backend_root / "test_videos" / fixture["video"]
  width = int(fixture["coordinate_space"]["width"])
  height = int(fixture["coordinate_space"]["height"])
  first_label = fixture["labels"][0]
  setup = {
    "version": 1,
    "reference_time_ms": fixture["reference_time_ms"],
    "barbell_target": "near_side_collar",
    "anchors": {
      name: {"x": point[0] / width, "y": point[1] / height}
      for name, point in first_label["anchors"].items()
    },
  }

  estimation = PoseEstimator(
    config=PoseEstimatorConfig(pose_backend="mediapipe", max_frame_dimension=720)
  ).run(str(video_path))
  tracking = track_manual_anchors(
    str(video_path),
    setup=setup,
    pose_frames=estimation["frames"],
    fps=estimation["fps"],
    width=estimation["processed_frame_width"],
    height=estimation["processed_frame_height"],
  )
  fused_frames, fusion = fuse_manual_body_tracks(
    estimation["frames"],
    setup=setup,
    tracking=tracking,
  )
  validated_frames, validation = validate_squat_pose_frames(
    fused_frames,
    selected_side_override=fusion["selected_side"],
  )
  result = BarbellTracker().track(
    str(video_path),
    pose_frames=validated_frames,
    frame_step=estimation["frame_step"],
    processed_width=estimation["processed_frame_width"],
    processed_height=estimation["processed_frame_height"],
    selected_side=fusion["selected_side"],
    manual_barbell_priors=barbell_track_priors(tracking),
  )

  selected_sides = {
    fusion["selected_side"],
    validation["selected_side"],
    result["diagnostics"]["selected_side"],
  }
  if len(selected_sides) != 1:
    raise AssertionError(f"tracking stages selected different sides: {sorted(selected_sides)}")

  points = result["barbellPath"]["points"]
  tolerance = float(fixture["tolerance_px"])
  rows = []
  for label in fixture["labels"]:
    label_time = label["source_frame_index"] / float(fixture["fps"])
    point = min(points, key=lambda item: abs(float(item["time"]) - label_time))
    expected_x, expected_y = label["anchors"]["barbell"]
    actual_x = float(point["x"]) * width
    actual_y = float(point["y"]) * height
    error_px = math.hypot(actual_x - expected_x, actual_y - expected_y)
    rows.append({
      "source_frame_index": label["source_frame_index"],
      "error_px": round(error_px, 2),
      "tracking_state": point.get("trackingState"),
    })
    if error_px > tolerance:
      raise AssertionError(
        f"barbell point at frame {label['source_frame_index']} missed by {error_px:.2f}px"
      )

  print(json.dumps({
    "selected_side": next(iter(selected_sides)),
    "tolerance_px": tolerance,
    "labels": rows,
    "diagnostics": {
      key: result["diagnostics"].get(key)
      for key in (
        "manual_accepted_count",
        "manual_blended_count",
        "manual_rejected_count",
        "manual_fallback_count",
        "manual_rejection_reason_counts",
      )
    },
  }, indent=2))


if __name__ == "__main__":
  main()
