"""File-based entry point for managed container platforms."""

from __future__ import annotations

import sys
from pathlib import Path


# Running this file directly sets sys.path to the jobs directory. Add the
# backend root so the application's absolute imports resolve consistently.
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
  sys.path.insert(0, str(BACKEND_ROOT))

from app.jobs.analysis_worker import main


if __name__ == "__main__":
  main()
