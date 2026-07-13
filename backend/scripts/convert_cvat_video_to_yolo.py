"""Convert versioned CVAT video exports into a source-video-safe YOLO dataset.

The manifest owns the split. A source video may appear in exactly one split, so
frames from the same lift cannot leak between train, validation, and test.
"""

from __future__ import annotations

import argparse
import json
import shutil
import xml.etree.ElementTree as element_tree
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2


YOLO_OBJECT_CLASSES = (
  "barbell_collar",
  "rack_upright",
  "j_hook",
  "safety_arm",
  "storage_peg",
  "sleeve",
  "plate_face",
)
LABEL_ALIASES = {
  "rack_storage_peg": "storage_peg",
}
VALID_SPLITS = {"train", "val", "test"}


def _annotation_xml(path: Path) -> str:
  if path.suffix.lower() != ".zip":
    return path.read_text(encoding="utf-8")
  with zipfile.ZipFile(path) as archive:
    names = [name for name in archive.namelist() if name.endswith("annotations.xml")]
    if len(names) != 1:
      raise ValueError(f"Expected one annotations.xml in {path}, found {len(names)}.")
    return archive.read(names[0]).decode("utf-8")


def load_cvat_boxes(path: Path) -> dict[int, list[tuple[str, float, float, float, float]]]:
  """Return visible video-track boxes keyed by source frame index."""
  root = element_tree.fromstring(_annotation_xml(path))
  boxes: dict[int, list[tuple[str, float, float, float, float]]] = defaultdict(list)
  for track in root.findall("track"):
    label = LABEL_ALIASES.get(track.attrib.get("label", ""), track.attrib.get("label", ""))
    if label not in YOLO_OBJECT_CLASSES:
      continue
    for box in track.findall("box"):
      if box.attrib.get("outside") == "1":
        continue
      frame_index = int(box.attrib["frame"])
      boxes[frame_index].append((
        label,
        float(box.attrib["xtl"]),
        float(box.attrib["ytl"]),
        float(box.attrib["xbr"]),
        float(box.attrib["ybr"]),
      ))
  return dict(boxes)


def _yolo_line(label: str, box: tuple[str, float, float, float, float], *, width: int, height: int) -> str:
  _, x0, y0, x1, y1 = box
  x0, x1 = sorted((max(0.0, x0), min(float(width), x1)))
  y0, y1 = sorted((max(0.0, y0), min(float(height), y1)))
  box_width = x1 - x0
  box_height = y1 - y0
  if box_width <= 0 or box_height <= 0:
    raise ValueError(f"Invalid {label} box: {(x0, y0, x1, y1)}")
  return "{} {:.8f} {:.8f} {:.8f} {:.8f}".format(
    YOLO_OBJECT_CLASSES.index(label),
    ((x0 + x1) / 2) / width,
    ((y0 + y1) / 2) / height,
    box_width / width,
    box_height / height,
  )


def convert_clip(clip: dict[str, Any], *, output_dir: Path) -> dict[str, Any]:
  clip_id = str(clip["id"])
  split = str(clip["split"])
  if split not in VALID_SPLITS:
    raise ValueError(f"{clip_id}: split must be one of {sorted(VALID_SPLITS)}.")
  video_path = Path(clip["video_path"])
  annotation_path = Path(clip["annotations_path"])
  boxes = load_cvat_boxes(annotation_path)
  if not boxes:
    raise ValueError(f"{clip_id}: no supported CVAT boxes found; add collar boxes before conversion.")
  if not any(label == "barbell_collar" for frame_boxes in boxes.values() for label, *_ in frame_boxes):
    raise ValueError(f"{clip_id}: barbell_collar boxes are required; point tracks are not YOLO detector labels.")

  image_dir = output_dir / "images" / split
  label_dir = output_dir / "labels" / split
  image_dir.mkdir(parents=True, exist_ok=True)
  label_dir.mkdir(parents=True, exist_ok=True)
  capture = cv2.VideoCapture(str(video_path))
  if not capture.isOpened():
    raise RuntimeError(f"{clip_id}: unable to open source video {video_path}")
  width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
  height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
  if width <= 0 or height <= 0:
    raise RuntimeError(f"{clip_id}: source video dimensions are unavailable")

  written = 0
  source_index = 0
  try:
    while True:
      success, image = capture.read()
      if not success:
        break
      frame_boxes = boxes.get(source_index)
      if frame_boxes:
        stem = f"{clip_id}_{source_index:06d}"
        image_path = image_dir / f"{stem}.jpg"
        label_path = label_dir / f"{stem}.txt"
        if not cv2.imwrite(str(image_path), image):
          raise RuntimeError(f"{clip_id}: failed to write {image_path}")
        label_path.write_text(
          "\n".join(_yolo_line(label, box, width=width, height=height) for box in frame_boxes) + "\n",
          encoding="utf-8",
        )
        written += 1
      source_index += 1
  finally:
    capture.release()
  if written == 0:
    raise ValueError(f"{clip_id}: CVAT boxes did not align with any video frames.")
  return {
    "id": clip_id,
    "split": split,
    "source_video": str(video_path),
    "annotation_export": str(annotation_path),
    "source_frame_count": source_index,
    "exported_frame_count": written,
    "width": width,
    "height": height,
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Convert CVAT video boxes into a YOLO detector dataset.")
  parser.add_argument("--manifest", type=Path, required=True, help="JSON list of source videos and their fixed splits.")
  parser.add_argument("--output-dir", type=Path, required=True)
  parser.add_argument("--replace", action="store_true", help="Replace an existing output directory.")
  args = parser.parse_args()

  manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
  clips = manifest.get("clips") if isinstance(manifest, dict) else manifest
  if not isinstance(clips, list) or not clips:
    raise ValueError("Manifest must provide a non-empty clips list.")
  ids = [str(clip.get("id")) for clip in clips if isinstance(clip, dict)]
  source_paths = [str(clip.get("video_path")) for clip in clips if isinstance(clip, dict)]
  if len(ids) != len(clips) or len(set(ids)) != len(ids) or len(set(source_paths)) != len(source_paths):
    raise ValueError("Each manifest clip requires a unique id and unique source video path.")
  if args.output_dir.exists():
    if not args.replace:
      raise FileExistsError(f"Output directory exists: {args.output_dir}; pass --replace to recreate it.")
    shutil.rmtree(args.output_dir)
  args.output_dir.mkdir(parents=True)

  converted = [convert_clip(clip, output_dir=args.output_dir) for clip in clips]
  (args.output_dir / "dataset_manifest.json").write_text(
    json.dumps({"version": 1, "classes": YOLO_OBJECT_CLASSES, "clips": converted}, indent=2) + "\n",
    encoding="utf-8",
  )
  (args.output_dir / "data.yaml").write_text(
    "path: {}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n{}".format(
      args.output_dir.resolve(),
      "".join(f"  {index}: {name}\n" for index, name in enumerate(YOLO_OBJECT_CLASSES)),
    ),
    encoding="utf-8",
  )
  print(json.dumps({"output_dir": str(args.output_dir), "clips": converted}, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
