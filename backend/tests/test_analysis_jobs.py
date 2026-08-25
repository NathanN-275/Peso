from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from app.jobs.analysis_worker import (
  AnalysisRunOutcome,
  AnalysisWorker,
  analysis_timeout_seconds,
  classify_analysis_failure,
)
from app.services.analysis_job_repository import AnalysisJobRepository


VIDEO_ID = "11111111-1111-1111-1111-111111111111"
JOB_ID = "55555555-5555-5555-5555-555555555555"


class AnalysisJobRepositoryTest(unittest.TestCase):
  def test_readiness_probe_selects_every_required_observability_column(self) -> None:
    client = MagicMock()
    query = client.table.return_value.select.return_value.limit.return_value
    query.execute.return_value.data = []

    with patch(
      "app.services.analysis_job_repository.get_supabase_admin_client",
      return_value=client,
    ):
      AnalysisJobRepository().check_readiness()

    client.table.assert_called_once_with("analysis_jobs")
    selected_columns = client.table.return_value.select.call_args.args[0]
    self.assertIn("stage", selected_columns)
    self.assertIn("stage_timestamps", selected_columns)
    self.assertIn("last_heartbeat_at", selected_columns)
    self.assertIn("failure_class", selected_columns)
    client.table.return_value.select.return_value.limit.assert_called_once_with(1)

  def test_enqueue_calls_atomic_database_rpc(self) -> None:
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = [
      {"id": JOB_ID, "video_id": VIDEO_ID, "status": "queued", "attempt_count": 0}
    ]

    with patch(
      "app.services.analysis_job_repository.get_supabase_admin_client",
      return_value=client,
    ):
      job = AnalysisJobRepository().enqueue(VIDEO_ID)

    client.rpc.assert_called_once_with(
      "enqueue_video_analysis_job",
      {"p_video_id": VIDEO_ID, "p_allow_completed": False},
    )
    self.assertEqual(job["id"], JOB_ID)

  def test_latest_for_videos_keeps_only_newest_job_per_video(self) -> None:
    client = MagicMock()
    query = client.table.return_value.select.return_value.in_.return_value.order.return_value
    query.execute.return_value.data = [
      {"id": "new", "video_id": VIDEO_ID, "created_at": "2026-08-17T12:00:00Z"},
      {"id": "old", "video_id": VIDEO_ID, "created_at": "2026-08-16T12:00:00Z"},
    ]

    with patch(
      "app.services.analysis_job_repository.get_supabase_admin_client",
      return_value=client,
    ):
      jobs = AnalysisJobRepository().latest_for_videos([VIDEO_ID])

    self.assertEqual(jobs[VIDEO_ID]["id"], "new")

  def test_progress_and_failure_use_observability_rpcs(self) -> None:
    client = MagicMock()
    client.rpc.return_value.execute.side_effect = [
      MagicMock(data=True),
      MagicMock(data="failed"),
    ]

    with patch(
      "app.services.analysis_job_repository.get_supabase_admin_client",
      return_value=client,
    ):
      repository = AnalysisJobRepository()
      self.assertTrue(repository.progress(JOB_ID, "worker-test", "pose"))
      self.assertEqual(
        repository.fail(
          JOB_ID,
          "worker-test",
          "bad video",
          failure_class="invalid_video",
          retryable=False,
        ),
        "failed",
      )

    self.assertEqual(client.rpc.call_args_list[0].args[0], "report_video_analysis_job_progress")
    self.assertEqual(client.rpc.call_args_list[1].args[0], "record_video_analysis_job_failure")


class AnalysisWorkerTest(unittest.TestCase):
  def test_successful_job_completes_after_analysis(self) -> None:
    jobs = MagicMock()
    jobs.claim.return_value = {"id": JOB_ID, "video_id": VIDEO_ID, "attempt_count": 1}
    jobs.complete.return_value = True
    analyzer = MagicMock()
    worker = AnalysisWorker(
      jobs=jobs,
      analyzer=analyzer,
      worker_id="worker-test",
      lease_seconds=60,
    )

    self.assertTrue(worker.run_once())

    analyzer.assert_called_once_with(VIDEO_ID)
    jobs.complete.assert_called_once_with(JOB_ID, "worker-test")
    jobs.fail.assert_not_called()

  def test_failed_job_is_returned_to_database_retry_policy(self) -> None:
    jobs = MagicMock()
    jobs.claim.return_value = {"id": JOB_ID, "video_id": VIDEO_ID, "attempt_count": 1}
    jobs.fail.return_value = "retry_wait"
    analyzer = MagicMock(side_effect=RuntimeError("pose failed"))
    worker = AnalysisWorker(
      jobs=jobs,
      analyzer=analyzer,
      worker_id="worker-test",
      lease_seconds=60,
    )

    self.assertTrue(worker.run_once())

    jobs.fail.assert_called_once_with(
      JOB_ID,
      "worker-test",
      "pose failed",
      failure_class="analysis_runtime",
      retryable=True,
    )
    jobs.complete.assert_not_called()

  def test_deterministic_invalid_video_failure_does_not_retry(self) -> None:
    jobs = MagicMock()
    jobs.claim.return_value = {"id": JOB_ID, "video_id": VIDEO_ID, "attempt_count": 1}
    jobs.fail.return_value = "failed"
    analyzer = MagicMock(side_effect=RuntimeError("Unable to open uploaded video."))
    worker = AnalysisWorker(jobs=jobs, analyzer=analyzer, worker_id="worker-test")

    self.assertTrue(worker.run_once())

    jobs.fail.assert_called_once_with(
      JOB_ID,
      "worker-test",
      "Unable to open uploaded video.",
      failure_class="invalid_video",
      retryable=False,
    )

  def test_worker_persists_runner_stages_and_uses_scaled_timeout(self) -> None:
    jobs = MagicMock()
    jobs.claim.return_value = {"id": JOB_ID, "video_id": VIDEO_ID, "attempt_count": 1}
    jobs.video_duration_ms.return_value = 120_000
    jobs.progress.return_value = True
    jobs.complete.return_value = True
    runner = MagicMock()

    def run(_video_id, *, timeout_seconds, on_stage):
      self.assertEqual(timeout_seconds, 360)
      on_stage("pose")
      on_stage("barbell_tracking")
      on_stage("saving")
      return AnalysisRunOutcome(True)

    runner.run.side_effect = run
    worker = AnalysisWorker(jobs=jobs, runner=runner, worker_id="worker-test")

    self.assertTrue(worker.run_once())

    self.assertEqual(
      [call.args[2] for call in jobs.progress.call_args_list],
      ["downloading", "pose", "barbell_tracking", "saving"],
    )
    jobs.complete.assert_called_once_with(JOB_ID, "worker-test")

  def test_idle_worker_does_not_run_analysis(self) -> None:
    jobs = MagicMock()
    jobs.claim.return_value = None
    analyzer = MagicMock()
    worker = AnalysisWorker(jobs=jobs, analyzer=analyzer, worker_id="worker-test")

    self.assertFalse(worker.run_once())
    analyzer.assert_not_called()

  def test_worker_recovers_expired_leases(self) -> None:
    jobs = MagicMock()
    jobs.recover_expired.return_value = {"retried_count": 1, "failed_count": 2}
    worker = AnalysisWorker(jobs=jobs, analyzer=MagicMock(), worker_id="worker-test")

    self.assertEqual(worker.recover_expired(), {"retried_count": 1, "failed_count": 2})

  def test_worker_retries_after_transient_claim_failure(self) -> None:
    jobs = MagicMock()
    jobs.recover_expired.return_value = {"retried_count": 0, "failed_count": 0}
    worker = AnalysisWorker(
      jobs=jobs,
      analyzer=MagicMock(),
      worker_id="worker-test",
      poll_seconds=0.1,
    )

    def claim_then_stop(*_args, **_kwargs):
      if jobs.claim.call_count == 1:
        raise RuntimeError("temporary database outage")
      worker.stop()
      return None

    jobs.claim.side_effect = claim_then_stop

    worker.run_forever()

    self.assertEqual(jobs.claim.call_count, 2)

  def test_timeout_policy_is_bounded_and_timeout_is_deterministic(self) -> None:
    self.assertEqual(analysis_timeout_seconds(30_000), 180)
    self.assertEqual(analysis_timeout_seconds(120_000), 360)
    self.assertEqual(analysis_timeout_seconds(600_000), 600)
    self.assertEqual(classify_analysis_failure("TimeoutError", "worker timed out"), ("analysis_timeout", False))


if __name__ == "__main__":
  unittest.main()
