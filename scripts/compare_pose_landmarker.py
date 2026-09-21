"""Capture comparable source-frame pose results; review does not auto-promote.

Run --backend legacy in an isolated MediaPipe 0.10.21 review environment and
--backend candidate in a separate Python 3.11 Linux review environment. Never
install legacy dependencies or this review tool in the release image. Use the
same source video, immutable candidate digest, and options. Different platforms
confound timing comparisons; no equivalence is inferred.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import resource
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--backend', choices=['legacy', 'candidate'], required=True)
  parser.add_argument('--video', type=Path, required=True)
  parser.add_argument('--output', type=Path, required=True)
  parser.add_argument('--candidate-image', required=True)
  parser.add_argument('--complexity', type=int, choices=[0, 1, 2], default=2)
  parser.add_argument('--fps', type=float, default=18)
  args = parser.parse_args()
  if not re.fullmatch(r'ghcr\.io/nathann-275/peso-backend@sha256:[a-f0-9]{64}', args.candidate_image):
    raise RuntimeError('Comparison evidence requires the immutable Peso candidate image digest.')
  import cv2
  import mediapipe as mp
  from app.analysis.pose_estimator import MediaPipePoseBackend, PoseEstimatorConfig, landmarks_from_mediapipe

  config = PoseEstimatorConfig(model_complexity=args.complexity, target_fps=args.fps)
  if args.backend == 'legacy':
    if mp.__version__ != '0.10.21':
      raise RuntimeError('Legacy comparison requires the original MediaPipe 0.10.21 environment.')
    pose = mp.solutions.pose.Pose(static_image_mode=False, model_complexity=config.model_complexity,
      smooth_landmarks=True, min_detection_confidence=config.min_detection_confidence,
      min_tracking_confidence=config.min_tracking_confidence)
  else:
    if mp.__version__ != '0.10.30':
      raise RuntimeError('Candidate comparison requires MediaPipe 0.10.30.')
    pose = MediaPipePoseBackend(config)
  cap = cv2.VideoCapture(str(args.video))
  if not cap.isOpened():
    raise RuntimeError('Cannot open comparison clip.')
  cap.set(cv2.CAP_PROP_ORIENTATION_AUTO, 1)
  fps = cap.get(cv2.CAP_PROP_FPS)
  if fps <= 0:
    raise RuntimeError('Comparison clip must have a positive frame rate.')
  frames = []
  index = 0
  next_time = 0.0
  started = time.perf_counter()
  try:
    while True:
      ok, frame = cap.read()
      if not ok:
        break
      timestamp = index / fps
      if timestamp + 1e-6 >= next_time:
        h, w = frame.shape[:2]
        scale = min(1.0, config.max_frame_dimension / max(h, w))
        frame = cv2.resize(frame, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
        if args.backend == 'legacy':
          result = pose.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
          landmarks = landmarks_from_mediapipe(result.pose_landmarks) if result.pose_landmarks else None
        else:
          landmarks = pose.process(frame, round(timestamp * 1000))
        frames.append({'source_frame_index': index, 'timestamp_ms': round(timestamp * 1000), 'landmarks': landmarks})
        next_time += 1 / args.fps
      index += 1
  finally:
    pose.close()
    cap.release()
  with args.video.open('rb') as source:
    source_sha256 = hashlib.file_digest(source, 'sha256').hexdigest()
  report = {
    'backend': args.backend, 'mediapipe_version': importlib.metadata.version('mediapipe'),
    'candidate_image_reference': args.candidate_image,
    'source_sha256': source_sha256,
    'source_name': args.video.name, 'source_fps': fps, 'source_frames': index,
    'model_complexity': args.complexity, 'target_fps': args.fps,
    'sampled_frames': len(frames), 'detected_frames': sum(f['landmarks'] is not None for f in frames),
    'wall_seconds': time.perf_counter() - started,
    'peak_rss_mib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024**2 if sys.platform == 'darwin' else 1024),
    'platform': sys.platform, 'acceptance': 'requires reviewed labels and human comparison', 'frames': frames,
  }
  args.output.parent.mkdir(parents=True, exist_ok=True)
  args.output.write_text(json.dumps(report))
  print(json.dumps({k: v for k, v in report.items() if k != 'frames'}))


if __name__ == '__main__':
  main()
