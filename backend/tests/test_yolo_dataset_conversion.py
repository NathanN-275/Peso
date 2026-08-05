from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.convert_cvat_video_to_yolo import YOLO_OBJECT_CLASSES, _yolo_line, load_cvat_boxes


class YoloDatasetConversionTest(unittest.TestCase):
  def test_cvat_video_boxes_keep_frame_indices_and_normalize_storage_alias(self) -> None:
    xml = """<?xml version=\"1.0\"?>
    <annotations>
      <track id=\"1\" label=\"barbell_collar\"><box frame=\"4\" outside=\"0\" xtl=\"10\" ytl=\"20\" xbr=\"30\" ybr=\"40\" /></track>
      <track id=\"2\" label=\"rack_storage_peg\"><box frame=\"4\" outside=\"0\" xtl=\"60\" ytl=\"30\" xbr=\"80\" ybr=\"50\" /></track>
      <track id=\"3\" label=\"barbell_collar\"><box frame=\"5\" outside=\"1\" xtl=\"10\" ytl=\"20\" xbr=\"30\" ybr=\"40\" /></track>
    </annotations>"""
    with tempfile.TemporaryDirectory() as temp_dir:
      path = Path(temp_dir) / "annotations.xml"
      path.write_text(xml, encoding="utf-8")
      boxes = load_cvat_boxes(path)

    self.assertEqual(sorted(label for label, *_ in boxes[4]), ["barbell_collar", "storage_peg"])
    self.assertNotIn(5, boxes)

  def test_yolo_line_uses_normalized_center_width_and_height(self) -> None:
    line = _yolo_line(
      "barbell_collar",
      ("barbell_collar", 10.0, 20.0, 30.0, 40.0),
      width=100,
      height=100,
    )

    self.assertEqual(line, f"{YOLO_OBJECT_CLASSES.index('barbell_collar')} 0.20000000 0.30000000 0.20000000 0.20000000")


if __name__ == "__main__":
  unittest.main()
