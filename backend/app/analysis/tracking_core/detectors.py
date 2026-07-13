from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np

from .models import Detection, DetectionFrame


class ObjectDetectorBackend(Protocol):
  name: str

  def detect(
    self,
    *,
    video_path: str,
    width: int,
    height: int,
    source_frame_indices: set[int] | None = None,
    timestamps_by_source_index: dict[int, float] | None = None,
  ) -> list[DetectionFrame]:
    raise NotImplementedError


class NullObjectDetector:
  name = "null_detector"

  def detect(
    self,
    *,
    video_path: str,
    width: int,
    height: int,
    source_frame_indices: set[int] | None = None,
    timestamps_by_source_index: dict[int, float] | None = None,
  ) -> list[DetectionFrame]:
    return []


class FixtureObjectDetector:
  name = "fixture_detector"

  def __init__(self, fixture_path: str | Path) -> None:
    self.fixture_path = Path(fixture_path)

  def detect(
    self,
    *,
    video_path: str,
    width: int,
    height: int,
    source_frame_indices: set[int] | None = None,
    timestamps_by_source_index: dict[int, float] | None = None,
  ) -> list[DetectionFrame]:
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
      source_frame_index = int(frame.get("source_frame_index", len(frames)))
      if source_frame_indices is not None and source_frame_index not in source_frame_indices:
        continue
      frames.append(
        DetectionFrame(
          source_frame_index=source_frame_index,
          time=float((timestamps_by_source_index or {}).get(source_frame_index, frame.get("time", 0.0))),
          detections=tuple(detections),
        )
      )
    return frames


class YoloOnnxObjectDetector:
  """Run an externally managed, custom YOLO ONNX detector on analysis frames.

  The detector deliberately knows nothing about analysis or tracking state. It
  returns normalized detections so the existing temporal tracker remains the
  sole owner of collar identity and output shape.
  """

  name = "yolo_onnx_detector"

  def __init__(
    self,
    *,
    model_path: str | Path,
    class_names: tuple[str, ...],
    confidence_threshold: float = 0.45,
    nms_iou_threshold: float = 0.45,
    input_size: int = 640,
  ) -> None:
    self.model_path = Path(model_path)
    self.class_names = class_names
    self.confidence_threshold = float(confidence_threshold)
    self.nms_iou_threshold = float(nms_iou_threshold)
    self.input_size = int(input_size)
    if not self.model_path.is_file():
      raise FileNotFoundError(f"YOLO tracking model was not found: {self.model_path}")
    if not self.class_names:
      raise ValueError("YOLO_TRACKING_CLASS_NAMES must declare the exported model class order.")
    try:
      import onnxruntime as ort
    except ImportError as error:  # pragma: no cover - requirements pin this dependency.
      raise RuntimeError("onnxruntime is required for YOLO tracking.") from error
    self._session = ort.InferenceSession(str(self.model_path), providers=["CPUExecutionProvider"])
    self._input = self._session.get_inputs()[0]
    self._input_name = self._input.name

  def detect(
    self,
    *,
    video_path: str,
    width: int,
    height: int,
    source_frame_indices: set[int] | None = None,
    timestamps_by_source_index: dict[int, float] | None = None,
  ) -> list[DetectionFrame]:
    capture = cv2.VideoCapture(video_path)
    if not capture.isOpened():
      raise RuntimeError(f"Unable to open video for YOLO tracking: {video_path}")

    selected_indices = source_frame_indices
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    frames: list[DetectionFrame] = []
    source_index = 0
    try:
      while True:
        success, image = capture.read()
        if not success:
          break
        if selected_indices is not None and source_index not in selected_indices:
          source_index += 1
          continue
        timestamp = (timestamps_by_source_index or {}).get(source_index)
        if timestamp is None:
          timestamp = source_index / fps if fps > 0 else source_index / 30.0
        frames.append(
          DetectionFrame(
            source_frame_index=source_index,
            time=float(timestamp),
            detections=tuple(self._detect_image(image)),
          )
        )
        source_index += 1
    finally:
      capture.release()
    return frames

  def _detect_image(self, image: np.ndarray) -> list[Detection]:
    tensor, scale, pad_x, pad_y = self._preprocess(image)
    outputs = self._session.run(None, {self._input_name: tensor})
    boxes, scores, class_ids = self._decode_output(outputs[0])
    if not boxes:
      return []
    indices = cv2.dnn.NMSBoxes(boxes, scores, self.confidence_threshold, self.nms_iou_threshold)
    if indices is None:
      return []
    output: list[Detection] = []
    for index in np.asarray(indices).reshape(-1).tolist() if len(indices) else []:
      x, y, box_width, box_height = boxes[int(index)]
      x0 = (x - pad_x) / scale
      y0 = (y - pad_y) / scale
      x1 = (x + box_width - pad_x) / scale
      y1 = (y + box_height - pad_y) / scale
      class_id = class_ids[int(index)]
      if class_id < 0 or class_id >= len(self.class_names):
        continue
      output.append(
        Detection.from_pixel_box(
          kind=self.class_names[class_id],  # type: ignore[arg-type]
          confidence=float(scores[int(index)]),
          bbox=(x0, y0, x1, y1),
          width=image.shape[1],
          height=image.shape[0],
        )
      )
    return output

  def _preprocess(self, image: np.ndarray) -> tuple[np.ndarray, float, float, float]:
    source_height, source_width = image.shape[:2]
    scale = min(self.input_size / max(source_width, 1), self.input_size / max(source_height, 1))
    resized_width = max(1, round(source_width * scale))
    resized_height = max(1, round(source_height * scale))
    resized = cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR)
    pad_x = (self.input_size - resized_width) / 2
    pad_y = (self.input_size - resized_height) / 2
    canvas = np.full((self.input_size, self.input_size, 3), 114, dtype=np.uint8)
    left = int(round(pad_x))
    top = int(round(pad_y))
    canvas[top:top + resized_height, left:left + resized_width] = resized
    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    layout = tuple(int(value) if isinstance(value, int) else -1 for value in self._input.shape)
    if len(layout) == 4 and layout[-1] == 3:
      return np.expand_dims(rgb, axis=0), scale, float(left), float(top)
    return np.expand_dims(np.transpose(rgb, (2, 0, 1)), axis=0), scale, float(left), float(top)

  def _decode_output(self, output: Any) -> tuple[list[list[int]], list[float], list[int]]:
    values = np.asarray(output)
    if values.ndim == 3:
      values = values[0]
    if values.ndim != 2:
      return [], [], []
    if values.shape[0] < values.shape[1] and values.shape[0] in {4 + len(self.class_names), 5 + len(self.class_names)}:
      values = values.T

    boxes: list[list[int]] = []
    scores: list[float] = []
    class_ids: list[int] = []
    expected_yolov5_width = 5 + len(self.class_names)
    expected_yolov8_width = 4 + len(self.class_names)
    for row in values:
      if len(row) == 6 and int(row[5]) < len(self.class_names):
        x0, y0, x1, y1, score, class_id = row
        if float(score) < self.confidence_threshold:
          continue
        boxes.append([int(x0), int(y0), int(x1 - x0), int(y1 - y0)])
        scores.append(float(score))
        class_ids.append(int(class_id))
        continue
      if len(row) not in {expected_yolov5_width, expected_yolov8_width}:
        continue
      class_start = 5 if len(row) == expected_yolov5_width else 4
      class_scores = row[class_start:]
      class_id = int(np.argmax(class_scores))
      score = float(class_scores[class_id])
      if class_start == 5:
        score *= float(row[4])
      if score < self.confidence_threshold:
        continue
      center_x, center_y, box_width, box_height = [float(value) for value in row[:4]]
      boxes.append([
        int(center_x - (box_width / 2)),
        int(center_y - (box_height / 2)),
        int(box_width),
        int(box_height),
      ])
      scores.append(score)
      class_ids.append(class_id)
    return boxes, scores, class_ids
