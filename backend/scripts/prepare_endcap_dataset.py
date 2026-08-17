from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


ROBOFLOW_HASH = re.compile(r"\.rf\.[0-9a-f]+$", re.IGNORECASE)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
SPLITS = ("train", "valid", "test")


@dataclass(frozen=True)
class EndcapSample:
  image_name: str
  label_name: str
  source_family: str
  original_split: str
  box_lines: tuple[str, ...]


def source_family(stem: str) -> str:
  return ROBOFLOW_HASH.sub("", stem)


def assigned_split(family: str) -> str:
  bucket = int(hashlib.sha256(family.encode("utf-8")).hexdigest()[:8], 16) % 10
  return "train" if bucket < 8 else "valid" if bucket == 8 else "test"


def _samples(archive: zipfile.ZipFile) -> list[EndcapSample]:
  names = set(archive.namelist())
  output: list[EndcapSample] = []
  for image_name in sorted(names):
    parts = Path(image_name).parts
    if len(parts) != 3 or parts[0] not in SPLITS or parts[1] != "images":
      continue
    image_path = Path(image_name)
    if image_path.suffix.lower() not in IMAGE_SUFFIXES:
      continue
    label_name = f"{parts[0]}/labels/{image_path.stem}.txt"
    if label_name not in names:
      continue
    lines = tuple(line.strip() for line in archive.read(label_name).decode("utf-8").splitlines() if line.strip())
    output.append(EndcapSample(
      image_name=image_name,
      label_name=label_name,
      source_family=source_family(image_path.stem),
      original_split=parts[0],
      box_lines=lines,
    ))
  return output


def audit_archive(archive_path: Path) -> dict[str, object]:
  with zipfile.ZipFile(archive_path) as archive:
    samples = _samples(archive)
  family_splits: dict[str, set[str]] = {}
  box_counts = Counter()
  for sample in samples:
    family_splits.setdefault(sample.source_family, set()).add(sample.original_split)
    box_counts[len(sample.box_lines)] += 1
  return {
    "image_count": len(samples),
    "source_family_count": len(family_splits),
    "cross_split_source_family_count": sum(len(splits) > 1 for splits in family_splits.values()),
    "box_count_distribution": dict(sorted(box_counts.items())),
    "eligible_single_box_count": sum(len(sample.box_lines) == 1 for sample in samples),
    "quarantined_ambiguous_count": sum(len(sample.box_lines) != 1 for sample in samples),
  }


def _normalized_label(line: str) -> str:
  values = line.split()
  if len(values) != 5:
    raise ValueError(f"Invalid YOLO endcap label: {line!r}")
  coordinates = [float(value) for value in values[1:]]
  if not all(0.0 <= value <= 1.0 for value in coordinates):
    raise ValueError(f"YOLO coordinates must be normalized: {line!r}")
  if coordinates[2] <= 0.0 or coordinates[3] <= 0.0:
    raise ValueError(f"YOLO boxes must have positive dimensions: {line!r}")
  return "0 " + " ".join(f"{value:.8f}" for value in coordinates)


def prepare_archive(archive_path: Path, output_dir: Path, *, replace: bool = False) -> dict[str, object]:
  if output_dir.exists():
    if not replace:
      raise FileExistsError(f"Output directory exists: {output_dir}")
    shutil.rmtree(output_dir)
  output_dir.mkdir(parents=True)

  counts = Counter()
  quarantined = Counter()
  with zipfile.ZipFile(archive_path) as archive:
    samples = _samples(archive)
    for sample in samples:
      if len(sample.box_lines) != 1:
        quarantined["empty" if not sample.box_lines else "ambiguous_multi_box"] += 1
        continue
      split = assigned_split(sample.source_family)
      image_suffix = Path(sample.image_name).suffix.lower()
      digest = hashlib.sha256(sample.image_name.encode("utf-8")).hexdigest()[:12]
      stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", sample.source_family).strip("-") or "sample"
      output_stem = f"{stem}-{digest}"
      image_dir = output_dir / "images" / split
      label_dir = output_dir / "labels" / split
      image_dir.mkdir(parents=True, exist_ok=True)
      label_dir.mkdir(parents=True, exist_ok=True)
      (image_dir / f"{output_stem}{image_suffix}").write_bytes(archive.read(sample.image_name))
      (label_dir / f"{output_stem}.txt").write_text(_normalized_label(sample.box_lines[0]) + "\n", encoding="utf-8")
      counts[split] += 1

  manifest = {
    "schema_version": 1,
    "source_archive": archive_path.name,
    "source_license": "CC BY 4.0",
    "source_class": "endcap",
    "output_class": "barbell_collar",
    "use": "detector_pretraining_only",
    "split_strategy": "sha256_source_family_80_10_10",
    "filters": ["exactly_one_box", "normalized_valid_box"],
    "counts": dict(counts),
    "quarantined": dict(quarantined),
    "limitations": [
      "Single-frame labels cannot validate temporal identity tracking.",
      "Automatic filtering cannot prove that every endcap box is Peso's visible collar target.",
      "Production promotion requires held-out Peso source-video labels.",
    ],
  }
  (output_dir / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
  (output_dir / "data.yaml").write_text(
    f"path: {output_dir.resolve()}\ntrain: images/train\nval: images/valid\ntest: images/test\nnames:\n  0: barbell_collar\n",
    encoding="utf-8",
  )
  return manifest


def main() -> int:
  parser = argparse.ArgumentParser(description="Audit or prepare a leakage-safe Roboflow endcap pretraining dataset.")
  parser.add_argument("--archive", type=Path, required=True)
  parser.add_argument("--output-dir", type=Path)
  parser.add_argument("--replace", action="store_true")
  parser.add_argument("--audit-only", action="store_true")
  args = parser.parse_args()
  if args.audit_only:
    print(json.dumps(audit_archive(args.archive), indent=2))
    return 0
  if args.output_dir is None:
    raise ValueError("--output-dir is required unless --audit-only is used.")
  print(json.dumps(prepare_archive(args.archive, args.output_dir, replace=args.replace), indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
