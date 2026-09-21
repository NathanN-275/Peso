"""Fetch versioned official models at build/setup time; never at runtime."""
from pathlib import Path
import hashlib
import sys
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.analysis.pose_landmarker import MODEL_DIRECTORY, MODEL_SHA256


def main() -> None:
  MODEL_DIRECTORY.mkdir(parents=True, exist_ok=True)
  for variant, checksum in MODEL_SHA256.items():
    filename = f"pose_landmarker_{variant}.task"
    target = MODEL_DIRECTORY / filename
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == checksum:
      continue
    url = f"https://storage.googleapis.com/mediapipe-models/pose_landmarker/{filename[:-5]}/float16/1/{filename}"
    with urllib.request.urlopen(url, timeout=60) as response:
      data = response.read()
    if hashlib.sha256(data).hexdigest() != checksum:
      raise RuntimeError(f"Model checksum mismatch: {variant}")
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(target)
    print(f"Verified {filename}: {checksum}")


if __name__ == "__main__":
  main()
