from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.jobs.analysis_queue import AnalysisJobQueue


class AnalysisJobQueueTest(unittest.TestCase):
  def setUp(self) -> None:
    self.client = MagicMock()
    self.client.rpc.return_value.execute.return_value = SimpleNamespace(
      data=[
        {
          "id": "job-1",
          "video_id": "video-1",
          "status": "queued",
          "attempt_count": 0,
        }
      ]
    )
    self.client_patch = patch("app.jobs.analysis_queue.get_supabase_admin_client", return_value=self.client)
    self.client_patch.start()
    self.addCleanup(self.client_patch.stop)

  def test_enqueue_hides_rpc_details_and_allows_explicit_reanalysis(self) -> None:
    job = AnalysisJobQueue().enqueue("video-1", reanalyze=True)

    self.client.rpc.assert_called_once_with(
      "enqueue_video_analysis_job",
      {"p_video_id": "video-1", "p_allow_completed": True},
    )
    self.assertEqual(job.id, "job-1")
    self.assertEqual(job.video_id, "video-1")
    self.assertEqual(job.status, "queued")

  def test_claim_returns_none_without_available_work(self) -> None:
    self.client.rpc.return_value.execute.return_value = SimpleNamespace(data=[])

    job = AnalysisJobQueue().claim("worker-1", 900)

    self.client.rpc.assert_called_once_with(
      "claim_video_analysis_job",
      {"p_worker_id": "worker-1", "p_lease_seconds": 900},
    )
    self.assertIsNone(job)

  def test_complete_and_cancel_return_database_confirmation(self) -> None:
    queue = AnalysisJobQueue()
    self.client.rpc.return_value.execute.return_value = SimpleNamespace(data=True)

    self.assertTrue(queue.complete("job-1", "worker-1"))

    self.client.rpc.assert_called_with(
      "complete_video_analysis_job",
      {"p_job_id": "job-1", "p_worker_id": "worker-1"},
    )

    self.client.rpc.return_value.execute.return_value = SimpleNamespace(data=1)
    self.assertEqual(queue.cancel_for_video("video-1"), 1)
    self.client.rpc.assert_called_with(
      "cancel_video_analysis_jobs",
      {"p_video_id": "video-1"},
    )
