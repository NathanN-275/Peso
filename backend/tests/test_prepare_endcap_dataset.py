from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.prepare_endcap_dataset import assigned_split, audit_archive, prepare_archive, source_family


class PrepareEndcapDatasetTest(unittest.TestCase):
  def _archive(self, root: Path) -> Path:
    path = root / "dataset.zip"
    with zipfile.ZipFile(path, "w") as archive:
      archive.writestr("train/images/lift_jpg.rf.aaaaaaaa.jpg", b"image-a")
      archive.writestr("train/labels/lift_jpg.rf.aaaaaaaa.txt", "0 0.5 0.5 0.1 0.1\n")
      archive.writestr("test/images/lift_jpg.rf.bbbbbbbb.jpg", b"image-b")
      archive.writestr("test/labels/lift_jpg.rf.bbbbbbbb.txt", "0 0.5 0.5 0.1 0.1\n")
      archive.writestr("valid/images/composite_jpg.rf.cccccccc.jpg", b"image-c")
      archive.writestr("valid/labels/composite_jpg.rf.cccccccc.txt", "0 0.2 0.2 0.1 0.1\n0 0.8 0.8 0.1 0.1\n")
    return path

  def test_source_family_strips_roboflow_hash_and_split_is_stable(self) -> None:
    self.assertEqual(source_family("lift_jpg.rf.1234abcd"), "lift_jpg")
    self.assertEqual(assigned_split("lift_jpg"), assigned_split("lift_jpg"))

  def test_audit_finds_cross_split_family(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      report = audit_archive(self._archive(Path(temp_dir)))

    self.assertEqual(report["image_count"], 3)
    self.assertEqual(report["source_family_count"], 2)
    self.assertEqual(report["cross_split_source_family_count"], 1)
    self.assertEqual(report["quarantined_ambiguous_count"], 1)

  def test_prepare_keeps_families_together_and_quarantines_multi_box_images(self) -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
      root = Path(temp_dir)
      output = root / "output"
      manifest = prepare_archive(self._archive(root), output)
      labels = list(output.glob("labels/*/*.txt"))

      self.assertEqual(len(labels), 2)
      self.assertEqual(len({path.parent.name for path in labels}), 1)
      self.assertEqual(manifest["quarantined"]["ambiguous_multi_box"], 1)
      self.assertTrue(all(path.read_text().startswith("0 ") for path in labels))


if __name__ == "__main__":
  unittest.main()
