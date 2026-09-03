from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


VARIANTS = {"yolo11n": "yolo11n.pt", "yolo11s": "yolo11s.pt"}


def _sha256(path: Path) -> str:
  digest = hashlib.sha256()
  with path.open("rb") as source:
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
      digest.update(chunk)
  return digest.hexdigest()


def _load_yolo() -> Any:
  try:
    from ultralytics import YOLO
  except ImportError as error:
    raise RuntimeError(
      "Training requires backend/requirements-training.txt in a separate environment."
    ) from error
  return YOLO


def _best_weight(train_result: Any) -> Path:
  save_dir = Path(str(train_result.save_dir))
  best = save_dir / "weights" / "best.pt"
  if not best.is_file():
    raise RuntimeError(f"Training did not produce expected weights: {best}")
  return best


def train_variant(
  *,
  variant: str,
  base_weight: Path,
  pretrain_data: Path,
  peso_data: Path,
  output_dir: Path,
  device: str,
  pretrain_epochs: int,
  fine_tune_epochs: int,
  image_size: int,
) -> dict[str, object]:
  if variant not in VARIANTS:
    raise ValueError(f"Unsupported variant: {variant}")
  if not base_weight.is_file():
    raise FileNotFoundError(
      f"Local base weight is required to avoid implicit downloads: {base_weight}"
    )
  YOLO = _load_yolo()
  project_dir = output_dir / "runs"
  pretrain = YOLO(str(base_weight)).train(
    data=str(pretrain_data),
    epochs=pretrain_epochs,
    imgsz=image_size,
    device=device,
    project=str(project_dir),
    name=f"{variant}-endcap-pretrain",
    exist_ok=False,
  )
  pretrain_weight = _best_weight(pretrain)
  fine_tune = YOLO(str(pretrain_weight)).train(
    data=str(peso_data),
    epochs=fine_tune_epochs,
    imgsz=image_size,
    device=device,
    project=str(project_dir),
    name=f"{variant}-peso-finetune",
    exist_ok=False,
  )
  fine_tuned_weight = _best_weight(fine_tune)
  model = YOLO(str(fine_tuned_weight))
  validation = model.val(data=str(peso_data), split="val", imgsz=image_size, device=device)
  exported_path = Path(str(model.export(
    format="onnx",
    imgsz=image_size,
    dynamic=False,
    simplify=True,
    opset=17,
  )))
  artifact_dir = output_dir / "artifacts"
  artifact_dir.mkdir(parents=True, exist_ok=True)
  artifact_path = artifact_dir / f"peso-collar-{variant}.onnx"
  shutil.copy2(exported_path, artifact_path)
  return {
    "variant": variant,
    "base_weight": str(base_weight),
    "pretrain_data": str(pretrain_data),
    "peso_data": str(peso_data),
    "artifact": str(artifact_path),
    "artifact_size_bytes": artifact_path.stat().st_size,
    "sha256": _sha256(artifact_path),
    "image_size": image_size,
    "validation_map50": float(getattr(validation.box, "map50", 0.0)),
    "validation_map50_95": float(getattr(validation.box, "map", 0.0)),
    "promotion_status": "requires_held_out_tracking_benchmark",
  }


def main() -> int:
  parser = argparse.ArgumentParser(description="Pretrain and fine-tune YOLO11n/s tracking detectors.")
  parser.add_argument("--pretrain-data", type=Path, required=True)
  parser.add_argument("--peso-data", type=Path, required=True)
  parser.add_argument("--base-weight-dir", type=Path, required=True)
  parser.add_argument("--output-dir", type=Path, required=True)
  parser.add_argument("--variants", nargs="+", choices=sorted(VARIANTS), default=sorted(VARIANTS))
  parser.add_argument("--device", default="cpu")
  parser.add_argument("--pretrain-epochs", type=int, default=50)
  parser.add_argument("--fine-tune-epochs", type=int, default=100)
  parser.add_argument("--image-size", type=int, default=640)
  args = parser.parse_args()
  reports = [
    train_variant(
      variant=variant,
      base_weight=args.base_weight_dir / VARIANTS[variant],
      pretrain_data=args.pretrain_data,
      peso_data=args.peso_data,
      output_dir=args.output_dir,
      device=args.device,
      pretrain_epochs=args.pretrain_epochs,
      fine_tune_epochs=args.fine_tune_epochs,
      image_size=args.image_size,
    )
    for variant in args.variants
  ]
  report = {"schema_version": 1, "models": reports}
  report_path = args.output_dir / "training-report.json"
  report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
  print(json.dumps(report, indent=2))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
