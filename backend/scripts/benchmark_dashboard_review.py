#!/usr/bin/env python3
"""Compare exported full traces with the dashboard's compact review projection."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from app.services.analysis_trace import AnalysisTraceService


def main() -> int:
  parser = argparse.ArgumentParser()
  parser.add_argument("bundles", nargs="+", type=Path)
  args = parser.parse_args()
  results = []
  for bundle_path in args.bundles:
    with zipfile.ZipFile(bundle_path) as archive:
      raw_trace = archive.read("trace.json")
    trace = json.loads(raw_trace)
    review = AnalysisTraceService._review_projection(trace)
    review_bytes = len(json.dumps(review, separators=(",", ":")).encode())
    results.append({
      "bundle": str(bundle_path),
      "full_trace_bytes": len(raw_trace),
      "review_bytes": review_bytes,
      "reduction_ratio": round(1 - (review_bytes / max(len(raw_trace), 1)), 4),
    })
  print(json.dumps(results, indent=2, sort_keys=True))
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
