from __future__ import annotations

import argparse
import logging
import multiprocessing
import os
import queue
import signal
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import FrameType
from typing import Any, Protocol
from uuid import uuid4

from ..analysis.pipeline import analyze_video
from ..services.analysis_job_repository import AnalysisJobRepository


logger = logging.getLogger(__name__)
DEFAULT_LEASE_SECONDS = 3600
DEFAULT_POLL_SECONDS = 2.0
DEFAULT_RECOVERY_SECONDS = 60.0
DEFAULT_NORMAL_TIMEOUT_SECONDS = 180
DEFAULT_MAX_TIMEOUT_SECONDS = 600
DEFAULT_LONG_CLIP_TIMEOUT_MULTIPLIER = 3.0
PUBLIC_ANALYSIS_STAGES = {"downloading", "pose", "barbell_tracking", "saving"}


def _positive_int_env(name: str, default: int) -> int:
  try:
    return max(1, int(os.getenv(name, str(default))))
  except ValueError:
    return default


def _positive_float_env(name: str, default: float) -> float:
  try:
    return max(0.1, float(os.getenv(name, str(default))))
  except ValueError:
    return default


def analysis_timeout_seconds(
  duration_ms: int | None,
  *,
  normal_timeout_seconds: int = DEFAULT_NORMAL_TIMEOUT_SECONDS,
  max_timeout_seconds: int = DEFAULT_MAX_TIMEOUT_SECONDS,
  long_clip_multiplier: float = DEFAULT_LONG_CLIP_TIMEOUT_MULTIPLIER,
) -> int:
  duration_seconds = float(duration_ms or 0) / 1000.0
  if duration_seconds <= 60.0:
    return normal_timeout_seconds
  scaled_timeout = int(round(duration_seconds * long_clip_multiplier))
  return min(max(scaled_timeout, normal_timeout_seconds), max_timeout_seconds)


def classify_analysis_failure(error_type: str, message: str) -> tuple[str, bool]:
  normalized = f"{error_type} {message}".lower()
  if any(
    marker in normalized
    for marker in (
      "unable to open uploaded video",
      "invalid video",
      "invalid_video",
      "unsupported video",
      "video duration",
      "was not found",
      "valid video stream",
      "contents do not match the selected video format",
      "unable to validate uploaded video contents",
    )
  ):
    return "invalid_video", False
  if "timeout" in normalized or "timed out" in normalized:
    return "analysis_timeout", False
  if any(
    marker in normalized
    for marker in (
      "storage",
      "network",
      "connection",
      "temporar",
      "rate limit",
      "service unavailable",
      "httpx",
      "supabase",
    )
  ):
    return "transient_infrastructure", True
  return "analysis_runtime", True


@dataclass(frozen=True)
class AnalysisRunOutcome:
  succeeded: bool
  error: str | None = None
  failure_class: str | None = None
  retryable: bool = False


class AnalysisRunner(Protocol):
  def run(
    self,
    video_id: str,
    *,
    timeout_seconds: int,
    on_stage: Callable[[str], None],
  ) -> AnalysisRunOutcome: ...


class InlineAnalysisRunner:
  """Test seam for injected analyzers; production work uses a child process."""

  def __init__(self, analyzer: Callable[[str], None]) -> None:
    self.analyzer = analyzer

  def run(
    self,
    video_id: str,
    *,
    timeout_seconds: int,
    on_stage: Callable[[str], None],
  ) -> AnalysisRunOutcome:
    del timeout_seconds, on_stage
    try:
      self.analyzer(video_id)
    except Exception as error:
      failure_class, retryable = classify_analysis_failure(type(error).__name__, str(error))
      return AnalysisRunOutcome(False, str(error), failure_class, retryable)
    return AnalysisRunOutcome(True)


def _run_analysis_child(video_id: str, messages: Any) -> None:
  from ..services.security_logging import configure_security_logging
  configure_security_logging()

  def report_stage(stage: str) -> None:
    messages.put({"type": "stage", "stage": stage})

  try:
    analyze_video(video_id, progress_callback=report_stage)
  except BaseException as error:
    messages.put({
      "type": "failed",
      "error_type": type(error).__name__,
      "error": str(error),
    })
  else:
    messages.put({"type": "completed"})


class InterruptibleAnalysisRunner:
  """Run one analysis in a process that can be terminated at its hard deadline."""

  def __init__(self, *, poll_seconds: float = 0.25) -> None:
    self.poll_seconds = max(0.05, poll_seconds)

  def run(
    self,
    video_id: str,
    *,
    timeout_seconds: int,
    on_stage: Callable[[str], None],
  ) -> AnalysisRunOutcome:
    context = multiprocessing.get_context("spawn")
    messages = context.Queue()
    process = context.Process(
      target=_run_analysis_child,
      args=(video_id, messages),
      name=f"analysis-{video_id}",
    )
    process.start()
    deadline = time.monotonic() + timeout_seconds
    outcome: AnalysisRunOutcome | None = None

    try:
      while process.is_alive() and outcome is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
          process.terminate()
          process.join(timeout=5.0)
          if process.is_alive():
            process.kill()
            process.join(timeout=2.0)
          return AnalysisRunOutcome(
            False,
            f"Analysis exceeded its {timeout_seconds}-second deadline.",
            "analysis_timeout",
            False,
          )
        try:
          message = messages.get(timeout=min(self.poll_seconds, remaining))
        except queue.Empty:
          continue
        outcome = self._handle_message(message, on_stage)

      process.join(timeout=2.0)
      while outcome is None:
        try:
          message = messages.get_nowait()
        except queue.Empty:
          break
        outcome = self._handle_message(message, on_stage)
      if outcome is not None:
        return outcome
      return AnalysisRunOutcome(
        False,
        f"Analysis process exited with code {process.exitcode} without a completion result.",
        "worker_process_exit",
        True,
      )
    finally:
      if process.is_alive():
        process.terminate()
        process.join(timeout=2.0)
      messages.close()
      messages.join_thread()

  @staticmethod
  def _handle_message(
    message: dict[str, Any],
    on_stage: Callable[[str], None],
  ) -> AnalysisRunOutcome | None:
    message_type = message.get("type")
    if message_type == "stage":
      stage = str(message.get("stage") or "")
      if stage in PUBLIC_ANALYSIS_STAGES:
        on_stage(stage)
      return None
    if message_type == "completed":
      return AnalysisRunOutcome(True)
    if message_type == "failed":
      error_type = str(message.get("error_type") or "RuntimeError")
      error = str(message.get("error") or "Unknown analysis failure.")
      failure_class, retryable = classify_analysis_failure(error_type, error)
      return AnalysisRunOutcome(False, error, failure_class, retryable)
    return None


class _LeaseHeartbeat:
  def __init__(
    self,
    *,
    jobs: AnalysisJobRepository,
    job_id: str,
    worker_id: str,
    lease_seconds: int,
  ) -> None:
    self.jobs = jobs
    self.job_id = job_id
    self.worker_id = worker_id
    self.lease_seconds = lease_seconds
    self.interval_seconds = max(30.0, min(300.0, lease_seconds / 3))
    self.stop_event = threading.Event()
    self.thread = threading.Thread(target=self._run, name=f"lease-{job_id}", daemon=True)

  def start(self) -> None:
    self.thread.start()

  def stop(self) -> None:
    self.stop_event.set()
    self.thread.join(timeout=2.0)

  def _run(self) -> None:
    while not self.stop_event.wait(self.interval_seconds):
      try:
        renewed = self.jobs.renew(
          self.job_id,
          self.worker_id,
          lease_seconds=self.lease_seconds,
        )
        if not renewed:
          logger.error("Worker %s lost lease for analysis job %s.", self.worker_id, self.job_id)
          return
      except Exception:
        logger.exception("Unable to renew lease for analysis job %s.", self.job_id)


class AnalysisWorker:
  def __init__(
    self,
    *,
    jobs: AnalysisJobRepository | None = None,
    analyzer: Callable[[str], None] | None = None,
    runner: AnalysisRunner | None = None,
    worker_id: str | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    recovery_seconds: float = DEFAULT_RECOVERY_SECONDS,
    normal_timeout_seconds: int = DEFAULT_NORMAL_TIMEOUT_SECONDS,
    max_timeout_seconds: int = DEFAULT_MAX_TIMEOUT_SECONDS,
    long_clip_timeout_multiplier: float = DEFAULT_LONG_CLIP_TIMEOUT_MULTIPLIER,
  ) -> None:
    self.jobs = jobs or AnalysisJobRepository()
    self.runner = runner or (
      InlineAnalysisRunner(analyzer) if analyzer is not None else InterruptibleAnalysisRunner()
    )
    self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
    self.lease_seconds = max(60, lease_seconds)
    self.poll_seconds = max(0.1, poll_seconds)
    self.recovery_seconds = max(1.0, recovery_seconds)
    self.normal_timeout_seconds = max(1, normal_timeout_seconds)
    self.max_timeout_seconds = max(self.normal_timeout_seconds, max_timeout_seconds)
    self.long_clip_timeout_multiplier = max(1.0, long_clip_timeout_multiplier)
    self.stop_event = threading.Event()

  def stop(self) -> None:
    self.stop_event.set()

  def recover_expired(self) -> dict[str, int]:
    report = self.jobs.recover_expired()
    if report["retried_count"] or report["failed_count"]:
      logger.warning("Recovered expired analysis jobs: %s", report)
    return report

  def run_once(self) -> bool:
    job = self.jobs.claim(self.worker_id, lease_seconds=self.lease_seconds)
    if not job:
      return False

    job_id = str(job["id"])
    video_id = str(job["video_id"])
    heartbeat = _LeaseHeartbeat(
      jobs=self.jobs,
      job_id=job_id,
      worker_id=self.worker_id,
      lease_seconds=self.lease_seconds,
    )
    logger.info("Worker %s claimed analysis job %s for video %s.", self.worker_id, job_id, video_id)
    heartbeat.start()
    try:
      duration_value = self.jobs.video_duration_ms(video_id)
      duration_ms = duration_value if isinstance(duration_value, int) else None
      timeout_seconds = analysis_timeout_seconds(
        duration_ms,
        normal_timeout_seconds=self.normal_timeout_seconds,
        max_timeout_seconds=self.max_timeout_seconds,
        long_clip_multiplier=self.long_clip_timeout_multiplier,
      )

      def report_stage(stage: str) -> None:
        if stage not in PUBLIC_ANALYSIS_STAGES:
          return
        try:
          if not self.jobs.progress(job_id, self.worker_id, stage):
            logger.error("Worker %s lost analysis job %s while reporting %s.", self.worker_id, job_id, stage)
        except Exception:
          logger.exception("Unable to persist stage %s for analysis job %s.", stage, job_id)

      report_stage("downloading")
      outcome = self.runner.run(
        video_id,
        timeout_seconds=timeout_seconds,
        on_stage=report_stage,
      )
      if not outcome.succeeded:
        next_status = self.jobs.fail(
          job_id,
          self.worker_id,
          outcome.error or "Unknown analysis failure.",
          failure_class=outcome.failure_class or "analysis_runtime",
          retryable=outcome.retryable,
        )
        logger.warning("Analysis job failure event=analysis_job_failure job_id=%s next_status=%s failure_class=%s", job_id, next_status or "unknown", outcome.failure_class)
        return True
    except Exception as error:
      logger.exception("Analysis worker failed while supervising job %s for video %s.", job_id, video_id)
      failure_class, retryable = classify_analysis_failure(type(error).__name__, str(error))
      next_status = self.jobs.fail(
        job_id,
        self.worker_id,
        str(error),
        failure_class=failure_class,
        retryable=retryable,
      )
      logger.warning("Analysis job failure event=analysis_job_failure job_id=%s next_status=%s failure_class=%s", job_id, next_status or "unknown", failure_class)
    else:
      if not self.jobs.complete(job_id, self.worker_id):
        logger.error("Analysis job %s completed work after losing its lease.", job_id)
      else:
        logger.info("Analysis job %s completed.", job_id)
    finally:
      heartbeat.stop()
    return True

  def run_forever(self) -> None:
    logger.info("Starting durable analysis worker %s.", self.worker_id)
    try:
      self.recover_expired()
    except Exception:
      logger.exception("Unable to perform initial expired-job recovery.")
    next_recovery_at = time.monotonic() + self.recovery_seconds
    while not self.stop_event.is_set():
      try:
        worked = self.run_once()
      except Exception:
        logger.exception("Analysis worker cycle failed; retrying after the poll interval.")
        worked = False

      if time.monotonic() >= next_recovery_at:
        try:
          self.recover_expired()
        except Exception:
          logger.exception("Unable to recover expired analysis jobs; the worker will retry.")
        next_recovery_at = time.monotonic() + self.recovery_seconds

      if not worked and self.stop_event.wait(self.poll_seconds):
        break
    logger.info("Stopped durable analysis worker %s.", self.worker_id)


def main() -> None:
  parser = argparse.ArgumentParser(description="Run the durable Peso video analysis worker.")
  parser.add_argument("--once", action="store_true", help="Claim at most one available job and exit.")
  args = parser.parse_args()
  from ..services.security_logging import configure_security_logging
  configure_security_logging()
  worker = AnalysisWorker(
    lease_seconds=_positive_int_env("ANALYSIS_WORKER_LEASE_SECONDS", DEFAULT_LEASE_SECONDS),
    poll_seconds=_positive_float_env("ANALYSIS_WORKER_POLL_SECONDS", DEFAULT_POLL_SECONDS),
    recovery_seconds=_positive_float_env("ANALYSIS_WORKER_RECOVERY_SECONDS", DEFAULT_RECOVERY_SECONDS),
    normal_timeout_seconds=_positive_int_env(
      "ANALYSIS_NORMAL_TIMEOUT_SECONDS",
      DEFAULT_NORMAL_TIMEOUT_SECONDS,
    ),
    max_timeout_seconds=_positive_int_env(
      "ANALYSIS_MAX_TIMEOUT_SECONDS",
      DEFAULT_MAX_TIMEOUT_SECONDS,
    ),
    long_clip_timeout_multiplier=_positive_float_env(
      "ANALYSIS_LONG_CLIP_TIMEOUT_MULTIPLIER",
      DEFAULT_LONG_CLIP_TIMEOUT_MULTIPLIER,
    ),
  )

  def stop_worker(_signal: int, _frame: FrameType | None) -> None:
    worker.stop()

  signal.signal(signal.SIGINT, stop_worker)
  signal.signal(signal.SIGTERM, stop_worker)
  if args.once:
    worker.recover_expired()
    worker.run_once()
    return
  worker.run_forever()


if __name__ == "__main__":
  main()
