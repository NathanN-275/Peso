from __future__ import annotations

import io
import xml.etree.ElementTree as element_tree
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


POSE_LABEL_ALIASES = {
  "shoulder": "visible_shoulder",
  "upper_back": "visible_shoulder",
  "upper back": "visible_shoulder",
  "hip": "visible_hip",
  "knee": "visible_knee",
  "ankle": "visible_ankle",
}
BOTTOM_LABELS = {"rep_bottom", "rep bottom", "bottom_transition", "bottom transition"}
REQUIRED_POSE_LABELS = {
  "visible_shoulder",
  "visible_hip",
  "visible_knee",
  "visible_ankle",
}


def _xml_bytes(path: Path) -> bytes:
  if path.suffix.lower() != ".zip":
    return path.read_bytes()
  with zipfile.ZipFile(path) as archive:
    candidates = [name for name in archive.namelist() if name.endswith("annotations.xml")]
    if len(candidates) != 1:
      raise ValueError(f"Expected one annotations.xml in {path}, found {len(candidates)}.")
    return archive.read(candidates[0])


def _parse_points(value: str) -> list[tuple[float, float]]:
  points: list[tuple[float, float]] = []
  for raw_point in value.split(";"):
    raw_point = raw_point.strip()
    if not raw_point:
      continue
    coordinates = raw_point.split(",")
    if len(coordinates) != 2:
      raise ValueError(f"Invalid CVAT point coordinate: {raw_point!r}.")
    points.append((float(coordinates[0]), float(coordinates[1])))
  return points


def _integer_text(root: element_tree.Element, path: str) -> int | None:
  value = root.findtext(path)
  if not value:
    return None
  try:
    return int(value)
  except ValueError:
    return None


def _source_metadata(root: element_tree.Element) -> dict[str, Any]:
  job_id = root.findtext("meta/job/id")
  return {
    "name": root.findtext("meta/task/name") or (f"CVAT job {job_id}" if job_id else None),
    "source": root.findtext("meta/task/source"),
    "frameCount": _integer_text(root, "meta/task/size") or _integer_text(root, "meta/job/size"),
    "width": _integer_text(root, "meta/task/original_size/width") or _integer_text(root, "meta/original_size/width"),
    "height": _integer_text(root, "meta/task/original_size/height") or _integer_text(root, "meta/original_size/height"),
  }


def inspect_cvat_pose_export(
  path: str | Path,
  *,
  minimum_dense_coverage: float = 0.8,
) -> dict[str, Any]:
  source_path = Path(path)
  root = element_tree.parse(io.BytesIO(_xml_bytes(source_path))).getroot()
  source = _source_metadata(root)
  frame_count = int(source.get("frameCount") or 0)
  track_counts: Counter[str] = Counter()
  shape_counts: Counter[str] = Counter()
  manual_keyframe_counts: Counter[str] = Counter()
  valid_points_by_label_frame: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
  ambiguous_shapes: list[dict[str, Any]] = []
  bottom_frames: set[int] = set()

  for track in root.findall("track"):
    raw_label = str(track.attrib.get("label") or "").strip().lower()
    track_counts[raw_label] += 1
    normalized_label = POSE_LABEL_ALIASES.get(raw_label)
    is_bottom = raw_label in BOTTOM_LABELS
    for shape in track.findall("points"):
      if shape.attrib.get("outside") == "1":
        continue
      frame_index = int(shape.attrib.get("frame") or 0)
      shape_counts[raw_label] += 1
      if shape.attrib.get("keyframe") == "1":
        manual_keyframe_counts[raw_label] += 1
      points = _parse_points(shape.attrib.get("points") or "")
      if is_bottom:
        bottom_frames.add(frame_index)
        continue
      if normalized_label is None:
        continue
      if len(points) != 1:
        ambiguous_shapes.append({
          "trackId": track.attrib.get("id"),
          "label": raw_label,
          "frameIndex": frame_index,
          "pointCount": len(points),
        })
        continue
      valid_points_by_label_frame[(normalized_label, frame_index)].append(points[0])

  duplicate_label_frames = [
    {
      "label": label,
      "frameIndex": frame_index,
      "activePointCount": len(points),
    }
    for (label, frame_index), points in valid_points_by_label_frame.items()
    if len(points) > 1
  ]
  unique_valid_frames = {
    label: {
      frame_index
      for (candidate_label, frame_index), points in valid_points_by_label_frame.items()
      if candidate_label == label and len(points) == 1
    }
    for label in REQUIRED_POSE_LABELS
  }
  coverage_by_label = {
    label: round(len(frames) / max(frame_count, 1), 4)
    for label, frames in unique_valid_frames.items()
  }
  missing_labels = sorted(label for label, frames in unique_valid_frames.items() if not frames)
  sparse_labels = sorted(
    label
    for label, coverage in coverage_by_label.items()
    if label not in missing_labels and coverage < minimum_dense_coverage
  )
  reasons: list[str] = []
  if missing_labels:
    reasons.append("missing_required_pose_labels")
  if sparse_labels:
    reasons.append("required_pose_labels_are_not_dense")
  if ambiguous_shapes:
    reasons.append("point_shapes_contain_multiple_coordinates")
  if duplicate_label_frames:
    reasons.append("multiple_active_points_exist_for_the_same_label_and_frame")
  if not bottom_frames:
    reasons.append("rep_bottom_frames_are_missing")
  if frame_count <= 0 or not source.get("width") or not source.get("height"):
    reasons.append("source_video_metadata_is_incomplete")

  return {
    "schemaVersion": 1,
    "sourceArchive": source_path.name,
    "source": source,
    "trackCounts": dict(sorted(track_counts.items())),
    "shapeCounts": dict(sorted(shape_counts.items())),
    "manualKeyframeCounts": dict(sorted(manual_keyframe_counts.items())),
    "requiredPoseLabels": sorted(REQUIRED_POSE_LABELS),
    "validFrameCoverageByLabel": coverage_by_label,
    "ambiguousMultiPointShapeCount": len(ambiguous_shapes),
    "ambiguousMultiPointShapeExamples": ambiguous_shapes[:20],
    "duplicateLabelFrameCount": len(duplicate_label_frames),
    "duplicateLabelFrameExamples": duplicate_label_frames[:20],
    "bottomFrameCount": len(bottom_frames),
    "bottomFrames": sorted(bottom_frames),
    "minimumDenseCoverage": minimum_dense_coverage,
    "poseBackendSelectionReady": not reasons,
    "blockingReasons": reasons,
    "limitations": [
      "Only numeric annotation metadata is inspected; no source frames or raw images are persisted.",
      "Interpolated CVAT shapes are accepted only when exactly one physical point exists for a label on a frame.",
      "An upper_back label is transparently compared with the selected shoulder landmark and is not an exact anatomical match.",
    ],
  }


def convert_cvat_pose_export(
  path: str | Path,
  *,
  minimum_dense_coverage: float = 0.8,
) -> dict[str, Any]:
  source_path = Path(path)
  assessment = inspect_cvat_pose_export(
    source_path,
    minimum_dense_coverage=minimum_dense_coverage,
  )
  if not assessment["poseBackendSelectionReady"]:
    reasons = ", ".join(assessment["blockingReasons"])
    raise ValueError(f"CVAT pose export is not evaluation-ready: {reasons}.")

  root = element_tree.parse(io.BytesIO(_xml_bytes(source_path))).getroot()
  source = _source_metadata(root)
  width = int(source["width"])
  height = int(source["height"])
  frames: dict[int, dict[str, Any]] = defaultdict(lambda: {"landmarks": {}})

  for track in root.findall("track"):
    raw_label = str(track.attrib.get("label") or "").strip().lower()
    normalized_label = POSE_LABEL_ALIASES.get(raw_label)
    is_bottom = raw_label in BOTTOM_LABELS
    if normalized_label is None and not is_bottom:
      continue
    for shape in track.findall("points"):
      if shape.attrib.get("outside") == "1":
        continue
      frame_index = int(shape.attrib.get("frame") or 0)
      points = _parse_points(shape.attrib.get("points") or "")
      if is_bottom:
        frames[frame_index]["phase"] = "bottom_transition"
      elif len(points) == 1:
        x, y = points[0]
        frames[frame_index]["landmarks"][normalized_label] = {
          "x": round(x / width, 8),
          "y": round(y / height, 8),
          "sourceLabel": raw_label,
        }

  return {
    "schema_version": 1,
    "coordinate_space": "normalized_source_frame",
    "annotation_density": "dense",
    "source": source,
    "conversion": {
      "sourceArchive": source_path.name,
      "upperBackPoseTarget": "selected_shoulder",
      "assessment": assessment,
    },
    "frames": [
      {"source_frame_index": frame_index, **payload}
      for frame_index, payload in sorted(frames.items())
    ],
  }
