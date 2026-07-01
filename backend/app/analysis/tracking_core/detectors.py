from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .models import Detection, DetectionFrame


class ObjectDetectorBackend(Protocol):
  name: str

  def detect(self, *, video_path: str, width: int, height: int) -> list[DetectionFrame]:
    raise NotImplementedError


class NullObjectDetector:
  name = "null_detector"

  def detect(self, *, video_path: str, width: int, height: int) -> list[DetectionFrame]:
    return []


class FixtureObjectDetector:
  name = "fixture_detector"

  def __init__(self, fixture_path: str | Path) -> None:
    self.fixture_path = Path(fixture_path)

  def detect(self, *, video_path: str, width: int, height: int) -> list[DetectionFrame]:
    payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
    frames: list[DetectionFrame] = []
    for frame in payload.get("frames", []):
      detections: list[Detection] = []
      for detection in frame.get("detections", []):
        if "bbox_px" in detection:
          detections.append(
            Detection.from_pixel_box(
              kind=detection["kind"],
              confidence=float(detection.get("confidence", 0.0)),
              bbox=tuple(detection["bbox_px"]),
              width=width,
              height=height,
              track_id=detection.get("trackId"),
            )
          )
        else:
          center = detection.get("center") or {}
          detections.append(
            Detection(
              kind=detection["kind"],
              confidence=float(detection.get("confidence", 0.0)),
              center=Detection.from_pixel_box(
                kind=detection["kind"],
                confidence=float(detection.get("confidence", 0.0)),
                bbox=(
                  float(center.get("x", 0.0)) * width,
                  float(center.get("y", 0.0)) * height,
                  float(center.get("x", 0.0)) * width,
                  float(center.get("y", 0.0)) * height,
                ),
                width=width,
                height=height,
              ).center,
              track_id=detection.get("trackId"),
            )
          )
      frames.append(
        DetectionFrame(
          source_frame_index=int(frame.get("source_frame_index", len(frames))),
          time=float(frame.get("time", 0.0)),
          detections=tuple(detections),
        )
      )
    return frames
