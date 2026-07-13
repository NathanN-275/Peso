from __future__ import annotations

import unittest
import os
from unittest.mock import MagicMock, patch

from app.jobs.analysis_queue import AnalysisJob
from app.jobs.worker import AnalysisWorker, _load_env_file


class AnalysisWorkerTest(unittest.TestCase):
  def test_run_once_claims_analyzes_and_completes_a_job(self) -> None:
    queue = MagicMock()
    job = AnalysisJob(
      id="job-1",
      video_id="video-1",
      status="processing",
      attempt_count=1,
    )
    queue.claim.return_value = job
    worker = AnalysisWorker(queue=queue, worker_id="worker-1", lease_seconds=900)

    with patch("app.jobs.worker.analyze_video") as analyze:
      did_process_work = worker.run_once()

    self.assertTrue(did_process_work)
    queue.recover_expired.assert_called_once_with()
    queue.claim.assert_called_once_with("worker-1", 900)
    analyze.assert_called_once_with("video-1", manage_status=False)
    queue.complete.assert_called_once_with("job-1", "worker-1")
    queue.fail.assert_not_called()

  def test_run_once_retries_a_failed_job_without_crashing_the_worker(self) -> None:
    queue = MagicMock()
    job = AnalysisJob(
      id="job-1",
      video_id="video-1",
      status="processing",
      attempt_count=1,
    )
    queue.claim.return_value = job
    worker = AnalysisWorker(queue=queue, worker_id="worker-1", lease_seconds=900)

    with patch("app.jobs.worker.analyze_video", side_effect=RuntimeError("storage unavailable")):
      did_process_work = worker.run_once()

    self.assertTrue(did_process_work)
    queue.complete.assert_not_called()
    queue.fail.assert_called_once_with("job-1", "worker-1", "storage unavailable")

  def test_run_once_returns_false_when_no_job_is_available(self) -> None:
    queue = MagicMock()
    queue.claim.return_value = None
    worker = AnalysisWorker(queue=queue, worker_id="worker-1", lease_seconds=900)

    self.assertFalse(worker.run_once())
    queue.recover_expired.assert_called_once_with()
    queue.complete.assert_not_called()

  def test_worker_env_file_fills_missing_values_without_overriding_shell_config(self) -> None:
    with (
      patch.dict(os.environ, {"SUPABASE_URL": "shell-url"}, clear=True),
      patch("app.jobs.worker.Path.is_file", return_value=True),
      patch(
        "app.jobs.worker.Path.read_text",
        return_value="SUPABASE_URL=file-url\nSUPABASE_SERVICE_ROLE_KEY='file-key'\n# comment\n",
      ),
    ):
      _load_env_file(".env")

      self.assertEqual(os.environ["SUPABASE_URL"], "shell-url")
      self.assertEqual(os.environ["SUPABASE_SERVICE_ROLE_KEY"], "file-key")
