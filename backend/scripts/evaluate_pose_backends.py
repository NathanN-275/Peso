from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from app.analysis.evaluation.pose_backend_metrics import evaluate_pose_result
from app.analysis.pose_estimator import PoseEstimator, PoseEstimatorConfig


SUPPORTED_BACKENDS = ("hybrid", "mediapipe", "rtmpose")


def _load_json(path: Path) -> dict[str, Any]:
  return json.loads(path.read_text(encoding="utf-8"))


def _package_version(name: str) -> str | None:
  try:
    return importlib.metadata.version(name)
  except importlib.metadata.PackageNotFoundError:
    return None


def _peak_rss_mb() -> float:
  value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
  # macOS reports bytes; Linux reports KiB.
  return value / (1024 * 1024) if sys.platform == "darwin" else value / 1024


def _compatibility_payload(success: bool) -> dict[str, Any]:
  system = platform.system()
  return {
    "cpuRequiredForCorrectness": True,
    "device": "cpu",
    "platform": system,
    "machine": platform.machine(),
    "localMacOS": success if system == "Darwin" else "not_executed_on_macos",
    "renderCompatibleLinuxCpu": success if system == "Linux" else "not_executed_on_linux",
    "note": "Compatibility is recorded only for the platform that actually executed this worker.",
  }


def _backend_versions(backend: str) -> dict[str, str | None]:
  return {
    "mediapipe": _package_version("mediapipe") if backend in {"mediapipe", "hybrid"} else None,
    "rtmlib": _package_version("rtmlib") if backend in {"rtmpose", "hybrid"} else None,
    "onnxruntime": _package_version("onnxruntime") if backend in {"rtmpose", "hybrid"} else None,
  }


def _worker(args: argparse.Namespace) -> int:
  annotations = _load_json(args.annotations) if args.annotations else None
  config = PoseEstimatorConfig(
    target_fps=args.target_fps,
    max_frame_dimension=args.max_frame_dimension,
    model_complexity=args.model_complexity,
    min_detection_confidence=args.min_detection_confidence,
    min_tracking_confidence=args.min_tracking_confidence,
    pose_backend=args.worker_backend,
    pose_fallback_enabled=True,
    pose_fallback_device="cpu",
    pose_fallback_det_frequency=args.rtmpose_detection_frequency,
    pose_fallback_mode=args.rtmpose_mode,
    debug_landmark_export_dir=None,
  )
  started = time.perf_counter()
  try:
    estimation = PoseEstimator(config=config).run(str(args.worker_video))
    metrics = evaluate_pose_result(
      estimation,
      annotations=annotations,
      confidence_threshold=args.confidence_threshold,
      sudden_displacement_heights_per_second=args.sudden_displacement_threshold,
    )
    result = {
      "status": "completed",
      "backend": args.worker_backend,
      "backendVersions": _backend_versions(args.worker_backend),
      "landmarkModel": estimation.get("landmark_model"),
      "device": "cpu",
      "backendSelectionReason": "benchmark_requested_backend",
      "fallbackEvents": [],
      "inferenceDurationMs": estimation.get("processing_duration_ms"),
      "wallDurationMs": int(round((time.perf_counter() - started) * 1000)),
      "peakResidentMemoryMb": round(_peak_rss_mb(), 2),
      "source": {
        "framesPerSecond": estimation.get("fps"),
        "frameCount": estimation.get("frame_count"),
        "durationMs": estimation.get("duration_ms"),
        "processedWidth": estimation.get("processed_frame_width"),
        "processedHeight": estimation.get("processed_frame_height"),
        "targetFramesPerSecond": estimation.get("target_fps"),
        "frameStep": estimation.get("frame_step"),
      },
      "compatibility": _compatibility_payload(True),
      **metrics,
    }
  except Exception as error:
    result = {
      "status": "failed",
      "backend": args.worker_backend,
      "backendVersions": _backend_versions(args.worker_backend),
      "device": "cpu",
      "backendSelectionReason": "benchmark_requested_backend",
      "fallbackEvents": [],
      "wallDurationMs": int(round((time.perf_counter() - started) * 1000)),
      "peakResidentMemoryMb": round(_peak_rss_mb(), 2),
      "compatibility": _compatibility_payload(False),
      "error": {"type": type(error).__name__, "message": str(error)},
    }
  print(json.dumps(result))
  return 0


def _resolve_path(value: str | None, manifest_dir: Path) -> Path | None:
  if not value:
    return None
  path = Path(value).expanduser()
  return path if path.is_absolute() else manifest_dir / path


def _validate_manifest(manifest: dict[str, Any]) -> None:
  if manifest.get("schema_version") != 1:
    raise ValueError("Pose backend evaluation manifest schema_version must be 1.")
  backends = manifest.get("backends")
  if not isinstance(backends, list) or not backends:
    raise ValueError("Manifest must list at least one backend.")
  unsupported = sorted(set(backends) - set(SUPPORTED_BACKENDS))
  if unsupported:
    raise ValueError(f"Unsupported pose backends: {unsupported}.")
  cases = manifest.get("cases")
  if not isinstance(cases, list) or not cases:
    raise ValueError("Manifest must contain at least one evaluation case.")
  ids = [case.get("id") for case in cases if isinstance(case, dict)]
  if len(ids) != len(cases) or any(not value for value in ids) or len(set(ids)) != len(ids):
    raise ValueError("Every evaluation case needs a unique non-empty id.")


def _worker_command(
  *,
  script_path: Path,
  backend: str,
  video_path: Path,
  annotations_path: Path | None,
  config: dict[str, Any],
) -> list[str]:
  command = [
    sys.executable,
    str(script_path),
    "--worker-backend",
    backend,
    "--worker-video",
    str(video_path),
    "--target-fps",
    str(config.get("target_fps", 18)),
    "--max-frame-dimension",
    str(config.get("max_frame_dimension", 720)),
    "--model-complexity",
    str(config.get("mediapipe_model_complexity", 2)),
    "--min-detection-confidence",
    str(config.get("min_detection_confidence", 0.6)),
    "--min-tracking-confidence",
    str(config.get("min_tracking_confidence", 0.6)),
    "--rtmpose-detection-frequency",
    str(config.get("rtmpose_detection_frequency", 3)),
    "--rtmpose-mode",
    str(config.get("rtmpose_mode", "balanced")),
    "--confidence-threshold",
    str(config.get("confidence_threshold", 0.35)),
    "--sudden-displacement-threshold",
    str(config.get("sudden_displacement_heights_per_second", 4.0)),
  ]
  if annotations_path:
    command.extend(["--annotations", str(annotations_path)])
  return command


def _run_manifest(manifest_path: Path) -> dict[str, Any]:
  manifest = _load_json(manifest_path)
  _validate_manifest(manifest)
  manifest_dir = manifest_path.parent
  config = manifest.get("config") or {}
  results: list[dict[str, Any]] = []
  script_path = Path(__file__).resolve()

  for case in manifest["cases"]:
    video_path = _resolve_path(case.get("video_path"), manifest_dir)
    annotations_path = _resolve_path(case.get("annotations_path"), manifest_dir)
    if video_path is None or not video_path.is_file():
      raise FileNotFoundError(f"{case['id']}: source video does not exist: {video_path}.")
    if annotations_path is not None and not annotations_path.is_file():
      raise FileNotFoundError(f"{case['id']}: annotations do not exist: {annotations_path}.")

    backend_results: list[dict[str, Any]] = []
    for backend in manifest["backends"]:
      completed = subprocess.run(
        _worker_command(
          script_path=script_path,
          backend=backend,
          video_path=video_path,
          annotations_path=annotations_path,
          config=config,
        ),
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "PYTHONPATH": "."},
        capture_output=True,
        text=True,
        check=False,
      )
      try:
        backend_result = json.loads(completed.stdout)
      except json.JSONDecodeError:
        backend_result = {
          "status": "failed",
          "backend": backend,
          "error": {
            "type": "WorkerProtocolError",
            "message": completed.stderr[-2000:] or completed.stdout[-2000:] or "Worker returned no JSON.",
          },
        }
      backend_result["workerExitCode"] = completed.returncode
      if completed.stderr:
        backend_result["workerStderrTail"] = completed.stderr[-2000:]
      backend_results.append(backend_result)
    results.append({
      "id": case["id"],
      "exerciseType": case.get("exercise_type", "squat"),
      "viewType": case.get("view_type", "side"),
      "cameraCase": case.get("camera_case"),
      "hasAnnotations": annotations_path is not None,
      "backends": backend_results,
    })

  selection = select_pose_backend(results, manifest)
  return {
    "schemaVersion": 1,
    "manifest": manifest_path.name,
    "generatedAtUnixMs": int(time.time() * 1000),
    "config": config,
    "results": results,
    "selection": selection,
  }


def select_pose_backend(results: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
  thresholds = manifest.get("acceptance_thresholds") or {}
  backend_names = list(manifest.get("backends") or [])
  profiles: dict[str, dict[str, Any]] = {}
  for backend_name in backend_names:
    samples = [
      backend
      for case in results
      for backend in case.get("backends") or []
      if backend.get("backend") == backend_name
    ]
    p95_values = [
      backend.get("groundTruthMetrics", {}).get("p95NormalizedLabeledPointError")
      for backend in samples
    ]
    coverages = [
      backend.get("groundTruthMetrics", {}).get("matchedPointCoverage")
      for backend in samples
    ]
    identity_accuracies = [
      backend.get("groundTruthMetrics", {}).get("visibleSideIdentityAccuracy")
      for backend in samples
    ]
    side_switches = sum(
      int(backend.get("proxyMetrics", {}).get("visibleSideIdentityStability", {}).get("sideSwitchCount") or 0)
      for backend in samples
    )
    failures: list[str] = []
    if len(samples) != len(results) or any(sample.get("status") != "completed" for sample in samples):
      failures.append("backend did not complete every case")
    if any(sample.get("groundTruthMetrics", {}).get("accuracyClaimEligible") is not True for sample in samples):
      failures.append("dense ground truth is incomplete")
    if not p95_values or any(value is None for value in p95_values):
      failures.append("p95 labeled-point error is missing")
    elif max(float(value) for value in p95_values) > float(thresholds.get("max_p95_normalized_error", 0.05)):
      failures.append("p95 labeled-point error exceeds threshold")
    if not coverages or any(value is None for value in coverages):
      failures.append("visible-joint coverage is missing")
    elif min(float(value) for value in coverages) < float(thresholds.get("minimum_visible_joint_coverage", 0.95)):
      failures.append("visible-joint coverage is below threshold")
    if not identity_accuracies or any(value is None for value in identity_accuracies):
      failures.append("visible-side identity accuracy is missing")
    elif min(float(value) for value in identity_accuracies) < float(thresholds.get("minimum_visible_side_identity_accuracy", 1.0)):
      failures.append("visible-side identity accuracy is below threshold")
    if side_switches > int(thresholds.get("maximum_side_identity_switches", 0)):
      failures.append("side identity switched during a clip")
    profiles[backend_name] = {
      "passed": not failures,
      "failures": failures,
      "worstP95NormalizedLabeledPointError": max((float(value) for value in p95_values if value is not None), default=None),
      "minimumMatchedPointCoverage": min((float(value) for value in coverages if value is not None), default=None),
      "minimumVisibleSideIdentityAccuracy": min((float(value) for value in identity_accuracies if value is not None), default=None),
      "sideIdentitySwitchCount": side_switches,
      "wallDurationMs": sum(int(sample.get("wallDurationMs") or 0) for sample in samples),
    }

  production_backend = str(manifest.get("production_backend") or "hybrid")
  baseline = profiles.get(production_backend)
  candidates = [
    (name, profile)
    for name, profile in profiles.items()
    if name != production_backend and profile["passed"]
  ]
  improved = [
    (name, profile)
    for name, profile in candidates
    if baseline
    and baseline.get("worstP95NormalizedLabeledPointError") is not None
    and profile.get("worstP95NormalizedLabeledPointError") is not None
    and float(profile["worstP95NormalizedLabeledPointError"]) < float(baseline["worstP95NormalizedLabeledPointError"])
  ]
  recommended = min(
    improved,
    key=lambda item: (float(item[1]["worstP95NormalizedLabeledPointError"]), int(item[1]["wallDurationMs"])),
    default=None,
  )
  selection_allowed = manifest.get("allow_backend_selection") is True
  return {
    "status": "evidence_ready_for_review" if selection_allowed and recommended else "not_selected",
    "reason": (
      "candidate_improves_p95_and_passes_identity_gates"
      if selection_allowed and recommended
      else "manifest_disallows_backend_selection"
      if not selection_allowed
      else "no_candidate_improved_on_production_backend"
    ),
    "productionBackend": production_backend,
    "recommendedProductionBackend": recommended[0] if selection_allowed and recommended else None,
    "profiles": profiles,
    "note": "This harness recommends evidence for review but never changes production configuration.",
  }


def _parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="Evaluate MediaPipe and RTMPose on the same side-squat corpus.")
  parser.add_argument("--manifest", type=Path)
  parser.add_argument("--output", type=Path)
  parser.add_argument("--worker-backend", choices=SUPPORTED_BACKENDS)
  parser.add_argument("--worker-video", type=Path)
  parser.add_argument("--annotations", type=Path)
  parser.add_argument("--target-fps", type=float, default=18)
  parser.add_argument("--max-frame-dimension", type=int, default=720)
  parser.add_argument("--model-complexity", type=int, default=2)
  parser.add_argument("--min-detection-confidence", type=float, default=0.6)
  parser.add_argument("--min-tracking-confidence", type=float, default=0.6)
  parser.add_argument("--rtmpose-detection-frequency", type=int, default=3)
  parser.add_argument("--rtmpose-mode", default="balanced")
  parser.add_argument("--confidence-threshold", type=float, default=0.35)
  parser.add_argument("--sudden-displacement-threshold", type=float, default=4.0)
  return parser


def main() -> int:
  args = _parser().parse_args()
  if args.worker_backend:
    if args.worker_video is None:
      raise ValueError("--worker-video is required in worker mode.")
    return _worker(args)
  if args.manifest is None:
    raise ValueError("--manifest is required.")
  report = _run_manifest(args.manifest)
  rendered = json.dumps(report, indent=2) + "\n"
  if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
  else:
    print(rendered, end="")
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
