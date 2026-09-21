from __future__ import annotations

import argparse
import json
import math
import multiprocessing
import queue
import statistics
import time
from pathlib import Path
from typing import Any

from app.jobs.process_memory import ProcessMemoryPeaks, process_tree_rss_bytes


SAMPLE_SECONDS = 0.1
MEMORY_GATE_BYTES = 400_000_000
PROFILE_SETTINGS = {
  "current_18fps_720px": (18.0, 720),
  "balanced_15fps_640px": (15.0, 640),
  "fast_12fps_640px": (12.0, 640),
}
MODEL_COMPLEXITIES = {"lite": 0, "full": 1, "heavy": 2}
TRACKER_POSE_MODES = {
  "fresh",
  "fixture",
  "fixture_on_fresh_schedule",
  "fresh_on_fixture_schedule",
  "fresh_selected_wrist_hidden",
  "fresh_sides_swapped",
}
TRACKER_JOINTS = ("shoulder", "wrist", "hip", "knee", "ankle")


def _nearest_frame(
  frames_by_index: dict[int, dict[str, Any]],
  source_indices: list[int],
  source_frame_index: int,
) -> dict[str, Any]:
  return frames_by_index[min(source_indices, key=lambda index: abs(index - source_frame_index))]


def _pose_frames_for_tracker(
  fresh_frames: list[dict[str, Any]],
  fixture_frames: list[dict[str, Any]],
  mode: str,
  *,
  selected_side: str = "right",
) -> list[dict[str, Any]]:
  if mode == "fresh":
    return fresh_frames
  if mode == "fixture":
    return fixture_frames

  if mode == "fresh_selected_wrist_hidden":
    selected_wrist = f"{selected_side}_wrist"
    transformed = []
    for frame in fresh_frames:
      landmarks = {
        name: dict(point)
        for name, point in (frame.get("landmarks") or {}).items()
      }
      if selected_wrist in landmarks:
        landmarks[selected_wrist]["visibility"] = 0.0
      transformed.append({**frame, "landmarks": landmarks})
    return transformed

  if mode == "fresh_sides_swapped":
    transformed = []
    for frame in fresh_frames:
      original = frame.get("landmarks") or {}
      landmarks = {name: dict(point) for name, point in original.items()}
      for joint in TRACKER_JOINTS + ("elbow",):
        left_name = f"left_{joint}"
        right_name = f"right_{joint}"
        if left_name in original and right_name in original:
          landmarks[left_name] = dict(original[right_name])
          landmarks[right_name] = dict(original[left_name])
      transformed.append({**frame, "landmarks": landmarks})
    return transformed

  if mode == "fixture_on_fresh_schedule":
    source_frames = fixture_frames
    schedule_frames = fresh_frames
  elif mode == "fresh_on_fixture_schedule":
    source_frames = fresh_frames
    schedule_frames = fixture_frames
  else:
    raise ValueError(f"Unsupported tracker pose mode: {mode}")

  source_by_index = {
    int(frame["source_frame_index"]): frame
    for frame in source_frames
  }
  source_indices = sorted(source_by_index)
  return [
    {
      **_nearest_frame(
        source_by_index,
        source_indices,
        int(schedule_frame["source_frame_index"]),
      ),
      "frame_index": frame_index,
      "source_frame_index": int(schedule_frame["source_frame_index"]),
      "timestamp_ms": int(schedule_frame["timestamp_ms"]),
    }
    for frame_index, schedule_frame in enumerate(schedule_frames)
  ]


def _pose_fixture_comparison(
  estimation: dict[str, Any],
  fixture: dict[str, Any],
) -> dict[str, Any]:
  fresh_frames = estimation.get("frames") or []
  fixture_frames = fixture.get("pose_frames") or []
  fresh_by_index = {int(frame["source_frame_index"]): frame for frame in fresh_frames}
  fixture_by_index = {int(frame["source_frame_index"]): frame for frame in fixture_frames}
  fresh_indices = sorted(fresh_by_index)
  fixture_indices = sorted(fixture_by_index)
  common_indices = sorted(set(fresh_indices) & set(fixture_indices))
  fps = float(fixture["fps"])
  selected_side = str(fixture["selected_side"])
  opposite_side = "left" if selected_side == "right" else "right"
  width = int(estimation["processed_frame_width"])
  height = int(estimation["processed_frame_height"])

  timestamp_errors_ms = [
    abs(float(frame["timestamp_ms"]) - (int(frame["source_frame_index"]) / fps * 1000.0))
    for frame in fresh_frames
  ]
  nearest_source_distances = [
    min(abs(index - fixture_index) for fixture_index in fixture_indices)
    for index in fresh_indices
  ]

  fresh_joint_visible_counts = {joint: 0 for joint in TRACKER_JOINTS}
  fixture_joint_visible_counts = {joint: 0 for joint in TRACKER_JOINTS}
  same_side_errors: list[float] = []
  swapped_side_errors: list[float] = []
  swapped_closer_count = 0
  identity_comparison_count = 0
  for fresh_index in fresh_indices:
    fresh_frame = fresh_by_index[fresh_index]
    fixture_frame = _nearest_frame(fixture_by_index, fixture_indices, fresh_index)
    fresh_landmarks = fresh_frame.get("landmarks") or {}
    fixture_landmarks = fixture_frame.get("landmarks") or {}
    for joint in TRACKER_JOINTS:
      selected_name = f"{selected_side}_{joint}"
      opposite_name = f"{opposite_side}_{joint}"
      fresh_point = fresh_landmarks.get(selected_name) or {}
      fixture_point = fixture_landmarks.get(selected_name) or {}
      opposite_fixture_point = fixture_landmarks.get(opposite_name) or {}
      if float(fresh_point.get("visibility") or 0.0) >= 0.35:
        fresh_joint_visible_counts[joint] += 1
      if float(fixture_point.get("visibility") or 0.0) >= 0.35:
        fixture_joint_visible_counts[joint] += 1
      if not fresh_point or not fixture_point or not opposite_fixture_point:
        continue
      same_error = math.hypot(
        (float(fresh_point["x"]) - float(fixture_point["x"])) * width,
        (float(fresh_point["y"]) - float(fixture_point["y"])) * height,
      )
      swapped_error = math.hypot(
        (float(fresh_point["x"]) - float(opposite_fixture_point["x"])) * width,
        (float(fresh_point["y"]) - float(opposite_fixture_point["y"])) * height,
      )
      same_side_errors.append(same_error)
      swapped_side_errors.append(swapped_error)
      identity_comparison_count += 1
      if swapped_error < same_error:
        swapped_closer_count += 1

  return {
    "coordinate_space_match": (
      width == int(fixture["coordinate_space"]["width"])
      and height == int(fixture["coordinate_space"]["height"])
    ),
    "fresh_frame_count": len(fresh_frames),
    "fixture_frame_count": len(fixture_frames),
    "common_source_index_count": len(common_indices),
    "exact_source_index_coverage": round(
      len(common_indices) / max(len(fresh_indices), 1),
      4,
    ),
    "max_nearest_source_index_distance": max(nearest_source_distances, default=None),
    "max_timestamp_source_error_ms": round(max(timestamp_errors_ms), 3) if timestamp_errors_ms else None,
    "selected_side": selected_side,
    "fresh_selected_joint_coverage": {
      joint: round(count / max(len(fresh_frames), 1), 4)
      for joint, count in fresh_joint_visible_counts.items()
    },
    "fixture_selected_joint_coverage": {
      joint: round(count / max(len(fresh_frames), 1), 4)
      for joint, count in fixture_joint_visible_counts.items()
    },
    "identity_comparison_count": identity_comparison_count,
    "same_side_median_error_px": round(statistics.median(same_side_errors), 2) if same_side_errors else None,
    "swapped_side_median_error_px": round(statistics.median(swapped_side_errors), 2) if swapped_side_errors else None,
    "swapped_side_closer_ratio": round(
      swapped_closer_count / max(identity_comparison_count, 1),
      4,
    ),
  }


def _required_label_gate(
  tracking: dict[str, Any],
  fixture: dict[str, Any],
  *,
  processed_width: int,
  processed_height: int,
) -> dict[str, Any]:
  points = (tracking.get("barbellPath") or {}).get("points") or []
  fixture_width = int(fixture["coordinate_space"]["width"])
  fixture_height = int(fixture["coordinate_space"]["height"])
  tolerance = float(fixture["tolerance_px"]) * max(processed_width, processed_height) / max(
    fixture_width,
    fixture_height,
  )
  failures: list[str] = []
  required_hits = 0
  required_count = sum(not label.get("allowed_missing") for label in fixture["labels"])
  errors_px: list[float] = []
  label_diagnostics: list[dict[str, Any]] = []
  for label in fixture["labels"]:
    if label.get("allowed_missing"):
      continue
    label_time = int(label["source_frame_index"]) / float(fixture["fps"])
    nearby = [point for point in points if abs(float(point["time"]) - label_time) <= 0.07]
    if not nearby:
      failures.append(f"missing point near frame {label['source_frame_index']}")
      label_diagnostics.append({
        "source_frame_index": int(label["source_frame_index"]),
        "matched": False,
      })
      continue
    closest = min(nearby, key=lambda point: abs(float(point["time"]) - label_time))
    target_x = float(label["target"][0]) / fixture_width * processed_width
    target_y = float(label["target"][1]) / fixture_height * processed_height
    error_px = math.hypot(
      (float(closest["x"]) * processed_width) - target_x,
      (float(closest["y"]) * processed_height) - target_y,
    )
    label_diagnostics.append({
      "source_frame_index": int(label["source_frame_index"]),
      "matched": True,
      "matched_source_frame": round(float(closest["time"]) * float(fixture["fps"]), 2),
      "point_px": [
        round(float(closest["x"]) * processed_width, 2),
        round(float(closest["y"]) * processed_height, 2),
      ],
      "target_px": [round(target_x, 2), round(target_y, 2)],
      "error_px": round(error_px, 2),
    })
    errors_px.append(error_px)
    if error_px > tolerance:
      failures.append(
        f"frame {label['source_frame_index']} error {error_px:.2f}px exceeds {tolerance:.2f}px"
      )
    else:
      required_hits += 1

  diagnostics = tracking.get("diagnostics") or {}
  max_point_gap_seconds = diagnostics.get("max_point_gap_seconds")
  rep_windows = fixture.get("rep_windows") or [{"start": float("-inf"), "end": float("inf")}]
  point_gaps = [
    (
      float(points[index]["time"]) - float(points[index - 1]["time"]),
      float(points[index - 1]["time"]),
      float(points[index]["time"]),
    )
    for index in range(1, len(points))
    if any(
      float(window["start"]) <= float(points[index - 1]["time"])
      and float(points[index]["time"]) <= float(window["end"])
      for window in rep_windows
    )
  ]
  largest_point_gap = max(point_gaps, default=None)
  if not (tracking.get("barbellPath") or {}).get("available"):
    failures.append("barbell path unavailable")
  if required_hits != required_count:
    failures.append(f"required label hits {required_hits}/{required_count}")
  if not isinstance(max_point_gap_seconds, (int, float)) or float(max_point_gap_seconds) > 0.9:
    failures.append("maximum visible point gap exceeds 0.9 seconds")
  return {
    "passed": not failures,
    "required_label_hits": required_hits,
    "required_label_count": required_count,
    "max_error_px": round(max(errors_px), 2) if errors_px else None,
    "tolerance_px": round(tolerance, 2),
    "label_diagnostics": label_diagnostics,
    "largest_point_gap": (
      {
        "seconds": round(largest_point_gap[0], 4),
        "start_source_frame": round(largest_point_gap[1] * float(fixture["fps"]), 2),
        "end_source_frame": round(largest_point_gap[2] * float(fixture["fps"]), 2),
      }
      if largest_point_gap
      else None
    ),
    "failures": failures,
  }


def _run_candidate_child(
  video_path: str,
  fixture_path: str,
  profile_id: str,
  model_variant: str,
  tracker_pose_mode: str,
  pose_cache_path: str | None,
  rep_index: int | None,
  messages: Any,
) -> None:
  from app.analysis.barbell_tracker import BarbellTracker
  from app.analysis.pose_estimator import PoseEstimator, PoseEstimatorConfig

  try:
    target_fps, max_dimension = PROFILE_SETTINGS[profile_id]
    fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
    if rep_index is not None:
      fixture["labels"] = [
        label for label in fixture["labels"]
        if int(label["rep_index"]) == rep_index
      ]
      fixture["rep_windows"] = [
        window for window in fixture["rep_windows"]
        if int(window["rep_index"]) == rep_index
      ]
    messages.put({"type": "stage", "stage": "pose"})
    started = time.perf_counter()
    pose_cache = Path(pose_cache_path) if pose_cache_path else None
    if pose_cache is not None and pose_cache.exists():
      estimation = json.loads(pose_cache.read_text(encoding="utf-8"))
    else:
      estimation = PoseEstimator(config=PoseEstimatorConfig(
        target_fps=target_fps,
        max_frame_dimension=max_dimension,
        model_complexity=MODEL_COMPLEXITIES[model_variant],
        pose_backend="mediapipe",
        pose_fallback_enabled=False,
        analysis_profile_id=profile_id,
        analysis_profile_mode="benchmark",
      )).run(video_path)
      if pose_cache is not None:
        pose_cache.write_text(json.dumps(estimation), encoding="utf-8")
    pose_ms = int((time.perf_counter() - started) * 1000)
    pose_comparison = _pose_fixture_comparison(estimation, fixture)
    tracker_pose_frames = _pose_frames_for_tracker(
      estimation["frames"],
      fixture["pose_frames"],
      tracker_pose_mode,
      selected_side=str(fixture["selected_side"]),
    )

    messages.put({"type": "stage", "stage": "barbell_tracking"})
    started = time.perf_counter()
    tracking = BarbellTracker().track(
      video_path,
      pose_frames=tracker_pose_frames,
      frame_step=int(estimation["frame_step"]),
      processed_width=int(estimation["processed_frame_width"]),
      processed_height=int(estimation["processed_frame_height"]),
      selected_side=str(fixture["selected_side"]),
      rep_windows=fixture["rep_windows"],
      target_fps=target_fps,
    )
    tracking_ms = int((time.perf_counter() - started) * 1000)
    gate = _required_label_gate(
      tracking,
      fixture,
      processed_width=int(estimation["processed_frame_width"]),
      processed_height=int(estimation["processed_frame_height"]),
    )
    diagnostics = tracking.get("diagnostics") or {}
    messages.put({
      "type": "result",
      "result": {
        "profile_id": profile_id,
        "model_variant": model_variant,
        "tracker_pose_mode": tracker_pose_mode,
        "target_fps": target_fps,
        "max_frame_dimension": max_dimension,
        "processed_width": estimation["processed_frame_width"],
        "processed_height": estimation["processed_frame_height"],
        "sampled_frame_count": estimation["sampled_frame_count"],
        "pose_frame_count": estimation["pose_frame_count"],
        "pose_estimation_ms": pose_ms,
        "pose_fixture_comparison": pose_comparison,
        "barbell_tracking_ms": tracking_ms,
        "benchmark_gates": gate,
        "tracking_diagnostics": {
          key: diagnostics.get(key)
          for key in (
            "detected_point_count",
            "interpolated_point_count",
            "max_point_gap_seconds",
            "per_rep_coverage",
            "reacquisition_count",
            "reacquisition_success_count",
            "path_reset_count",
            "stale_prior_expiration_count",
            "skipped_no_pose_frame_count",
            "rejection_reason_counts",
            "bad_candidate_rejection_counts",
          )
        },
      },
    })
  except BaseException as error:
    messages.put({
      "type": "error",
      "error_type": type(error).__name__,
      "error": str(error),
    })


def run_candidate(
  *,
  video_path: Path,
  fixture_path: Path,
  profile_id: str,
  model_variant: str,
  tracker_pose_mode: str = "fresh",
  pose_cache_path: Path | None = None,
  rep_index: int | None = None,
  timeout_seconds: int,
) -> dict[str, Any]:
  context = multiprocessing.get_context("spawn")
  messages = context.Queue()
  process = context.Process(
    target=_run_candidate_child,
    args=(
      str(video_path),
      str(fixture_path),
      profile_id,
      model_variant,
      tracker_pose_mode,
      str(pose_cache_path) if pose_cache_path else None,
      rep_index,
      messages,
    ),
  )
  process.start()
  deadline = time.monotonic() + timeout_seconds
  next_sample_at = time.monotonic()
  stage = "starting"
  peaks = ProcessMemoryPeaks()
  result: dict[str, Any] | None = None
  error: dict[str, Any] | None = None
  try:
    while process.is_alive() and result is None and error is None:
      now = time.monotonic()
      if now >= next_sample_at:
        peaks.record(stage, process_tree_rss_bytes(process.pid or 0))
        next_sample_at = now + SAMPLE_SECONDS
      if now >= deadline:
        process.terminate()
        error = {"error_type": "TimeoutError", "error": "benchmark timed out"}
        break
      try:
        message = messages.get(timeout=min(SAMPLE_SECONDS, max(0.01, next_sample_at - now)))
      except queue.Empty:
        continue
      if message.get("type") == "stage":
        stage = str(message["stage"])
      elif message.get("type") == "result":
        result = dict(message["result"])
      elif message.get("type") == "error":
        error = dict(message)
    peaks.record(stage, process_tree_rss_bytes(process.pid or 0))
    process.join(timeout=5.0)
    while result is None and error is None:
      try:
        message = messages.get_nowait()
      except queue.Empty:
        break
      if message.get("type") == "result":
        result = dict(message["result"])
      elif message.get("type") == "error":
        error = dict(message)
  finally:
    if process.is_alive():
      process.kill()
      process.join(timeout=2.0)
    messages.close()
    messages.join_thread()

  peak_rss_mb, stage_peak_rss_mb = peaks.as_megabytes()
  if error is not None or result is None:
    return {
      "profile_id": profile_id,
      "model_variant": model_variant,
      "passed": False,
      "error": error or {"error_type": "ProcessExit", "error": f"exit code {process.exitcode}"},
      "peak_rss_bytes": peaks.peak_rss_bytes,
      "stage_peak_rss_bytes": dict(peaks.stage_peak_rss_bytes),
      "peak_rss_mb": peak_rss_mb,
      "stage_peak_rss_mb": stage_peak_rss_mb,
      "sample_interval_ms": int(SAMPLE_SECONDS * 1000),
    }
  result.update({
    "peak_rss_bytes": peaks.peak_rss_bytes,
    "stage_peak_rss_bytes": dict(peaks.stage_peak_rss_bytes),
    "peak_rss_mb": peak_rss_mb,
    "stage_peak_rss_mb": stage_peak_rss_mb,
    "sample_interval_ms": int(SAMPLE_SECONDS * 1000),
    "memory_gate_mb": 400,
    "passed": bool(
      result["benchmark_gates"]["passed"]
      and peaks.peak_rss_bytes < MEMORY_GATE_BYTES
    ),
  })
  return result


def main() -> int:
  parser = argparse.ArgumentParser(description="Benchmark IMG_0013 in the release runtime.")
  parser.add_argument("--video", type=Path, required=True)
  parser.add_argument("--fixture", type=Path, required=True)
  parser.add_argument("--profile", choices=tuple(PROFILE_SETTINGS), required=True)
  parser.add_argument("--model", choices=tuple(MODEL_COMPLEXITIES), default="full")
  parser.add_argument(
    "--tracker-pose-mode",
    choices=tuple(sorted(TRACKER_POSE_MODES)),
    default="fresh",
  )
  parser.add_argument("--pose-cache", type=Path)
  parser.add_argument("--rep-index", type=int, choices=(1, 2, 3))
  parser.add_argument("--timeout-seconds", type=int, default=600)
  args = parser.parse_args()
  report = run_candidate(
    video_path=args.video,
    fixture_path=args.fixture,
    profile_id=args.profile,
    model_variant=args.model,
    tracker_pose_mode=args.tracker_pose_mode,
    pose_cache_path=args.pose_cache,
    rep_index=args.rep_index,
    timeout_seconds=max(1, args.timeout_seconds),
  )
  print(json.dumps(report, indent=2, sort_keys=True))
  return 0 if report.get("passed") else 1


if __name__ == "__main__":
  raise SystemExit(main())
