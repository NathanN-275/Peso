from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.analysis_runs import _trace_service, router
from app.services.analysis_trace import AnalysisTraceService
from app.services.auth import get_current_user_id


USER_ID = "33333333-3333-3333-3333-333333333333"
OTHER_USER_ID = "44444444-4444-4444-4444-444444444444"


class AnalysisRunRoutesTest(unittest.TestCase):
  def setUp(self) -> None:
    self.temporary_directory = tempfile.TemporaryDirectory()
    self.service = AnalysisTraceService(
      enabled=True,
      trace_dir=Path(self.temporary_directory.name) / "traces",
      max_runs=20,
    )
    self.trace = self.service.start(
      video_id="11111111-1111-1111-1111-111111111111",
      user_id=USER_ID,
      exercise_type="back_squat",
      view_type="side",
      model_version="trace-test-model",
    )
    self.trace.stage("pose_estimation", 123)
    self.trace.complete({"diagnostics": {"pose_backend": "mediapipe"}}, {"pose_estimation": 123})
    self.app = FastAPI()
    self.app.include_router(router)
    self.app.dependency_overrides[_trace_service] = lambda: self.service
    self.client = TestClient(self.app)

  def tearDown(self) -> None:
    self.client.close()
    self.temporary_directory.cleanup()

  def _authenticate_as(self, user_id: str) -> None:
    self.app.dependency_overrides[get_current_user_id] = lambda: user_id

  def test_authenticated_user_can_list_detail_stream_and_export_owned_run(self) -> None:
    self._authenticate_as(USER_ID)

    listing = self.client.get("/dev/analysis-runs")
    detail = self.client.get(f"/dev/analysis-runs/{self.trace.run_id}")
    stream = self.client.get(f"/dev/analysis-runs/{self.trace.run_id}/events")
    export = self.client.get(f"/dev/analysis-runs/{self.trace.run_id}/export")

    self.assertEqual(listing.status_code, 200)
    self.assertEqual(listing.json()["runs"][0]["run_id"], self.trace.run_id)
    self.assertEqual(detail.status_code, 200)
    self.assertEqual(detail.json()["status"], "completed")
    self.assertEqual(detail.json()["video_id"], "11111111-1111-1111-1111-111111111111")
    self.assertEqual(stream.status_code, 200)
    self.assertIn("analysis_started", stream.text)
    self.assertEqual(export.status_code, 200)
    self.assertEqual(export.headers["content-type"], "application/zip")
    self.assertIn("attachment;", export.headers["content-disposition"])

  def test_authenticated_user_cannot_access_another_users_run(self) -> None:
    self._authenticate_as(OTHER_USER_ID)

    self.assertEqual(self.client.get("/dev/analysis-runs").json(), {"runs": []})
    self.assertEqual(self.client.get(f"/dev/analysis-runs/{self.trace.run_id}").status_code, 404)
    self.assertEqual(self.client.get(f"/dev/analysis-runs/{self.trace.run_id}/events").status_code, 404)
    self.assertEqual(self.client.get(f"/dev/analysis-runs/{self.trace.run_id}/export").status_code, 404)
