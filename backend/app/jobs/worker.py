from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import socket
import threading
import time
from uuid import uuid4

from ..analysis.pipeline import analyze_video
from ..services.config import get_settings
from .analysis_queue import AnalysisJobQueue, AnalysisJobsMigrationRequired


logger = logging.getLogger(__name__)
MISSING_ANALYSIS_JOBS_MIGRATION_EXIT_CODE = 78


class LeaseHeartbeat:
  """Renews a claimed job lease while CPU-heavy analysis is running."""

  def __init__(
    self,
    *,
    queue: AnalysisJobQueue,
    job_id: str,
    worker_id: str,
    lease_seconds: int,
  ) -> None:
    self.queue = queue
    self.job_id = job_id
    self.worker_id = worker_id
    self.lease_seconds = lease_seconds
    self._stop = threading.Event()
    self._thread = threading.Thread(target=self._run, name=f"lease-{job_id}", daemon=True)

  def __enter__(self) -> "LeaseHeartbeat":
    self._thread.start()
    return self

  def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
    self._stop.set()
    self._thread.join(timeout=5)

  def _run(self) -> None:
    interval_seconds = max(15, self.lease_seconds // 3)

    while not self._stop.wait(interval_seconds):
      try:
        renewed = self.queue.renew(self.job_id, self.worker_id, self.lease_seconds)
      except Exception:
        logger.exception("Unable to renew analysis job lease job_id=%s", self.job_id)
        continue

      if not renewed:
        logger.error("Analysis job lease was lost job_id=%s", self.job_id)
        return


class AnalysisWorker:
  """Claims one durable analysis job at a time in a standalone process."""

  def __init__(self, *, queue: AnalysisJobQueue, worker_id: str, lease_seconds: int) -> None:
    self.queue = queue
    self.worker_id = worker_id
    self.lease_seconds = lease_seconds

  def run_once(self) -> bool:
    self.queue.recover_expired()
    job = self.queue.claim(self.worker_id, self.lease_seconds)

    if not job:
      return False

    logger.info(
      "Claimed analysis job job_id=%s video_id=%s attempt=%s worker_id=%s",
      job.id,
      job.video_id,
      job.attempt_count,
      self.worker_id,
    )

    try:
      with LeaseHeartbeat(
        queue=self.queue,
        job_id=job.id,
        worker_id=self.worker_id,
        lease_seconds=self.lease_seconds,
      ):
        analyze_video(job.video_id, manage_status=False)
    except Exception as error:
      error_summary = str(error).splitlines()[0][:2000] or error.__class__.__name__
      outcome = self.queue.fail(job.id, self.worker_id, error_summary)
      logger.exception(
        "Analysis job failed job_id=%s video_id=%s outcome=%s",
        job.id,
        job.video_id,
        outcome or "lease_lost",
      )
      return True

    if not self.queue.complete(job.id, self.worker_id):
      logger.error("Analysis job completed after its lease was lost job_id=%s", job.id)
    else:
      logger.info("Completed analysis job job_id=%s video_id=%s", job.id, job.video_id)

    return True


def _default_worker_id() -> str:
  return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


def _load_env_file(path_value: str) -> None:
  """Load the small KEY=VALUE subset used by backend/.env without overriding shell config."""
  path = Path(path_value)

  if not path.is_file():
    return

  for raw_line in path.read_text().splitlines():
    line = raw_line.strip()

    if not line or line.startswith("#") or "=" not in line:
      continue

    key, value = line.split("=", 1)
    key = key.removeprefix("export ").strip()
    value = value.strip()

    if not key or key in os.environ:
      continue

    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
      value = value[1:-1]

    os.environ[key] = value


def main() -> None:
  logging.basicConfig(level=logging.INFO)
  parser = argparse.ArgumentParser(description="Run durable Peso video-analysis jobs.")
  parser.add_argument("--once", action="store_true", help="Claim and process at most one job.")
  parser.add_argument("--env-file", default=".env", help="Optional backend environment file.")
  parser.add_argument("--worker-id", default=_default_worker_id(), help="Stable label for this worker process.")
  parser.add_argument("--poll-seconds", type=int, default=None, help="Idle poll interval override.")
  parser.add_argument("--lease-seconds", type=int, default=None, help="Lease duration override.")
  args = parser.parse_args()

  _load_env_file(args.env_file)
  settings = get_settings()
  poll_seconds = args.poll_seconds or settings.analysis_worker_poll_seconds
  lease_seconds = args.lease_seconds or settings.analysis_job_lease_seconds

  if poll_seconds <= 0 or lease_seconds <= 0:
    raise RuntimeError("Worker poll and lease durations must be positive.")

  worker = AnalysisWorker(
    queue=AnalysisJobQueue(),
    worker_id=args.worker_id,
    lease_seconds=lease_seconds,
  )

  try:
    if args.once:
      worker.run_once()
      return

    logger.info(
      "Starting analysis worker worker_id=%s poll_seconds=%s lease_seconds=%s",
      args.worker_id,
      poll_seconds,
      lease_seconds,
    )
    while True:
      if not worker.run_once():
        time.sleep(poll_seconds)
  except AnalysisJobsMigrationRequired as error:
    logger.error("%s", error)
    raise SystemExit(MISSING_ANALYSIS_JOBS_MIGRATION_EXIT_CODE) from error


if __name__ == "__main__":
  main()
