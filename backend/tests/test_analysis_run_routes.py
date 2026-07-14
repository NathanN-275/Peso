from __future__ import annotations

import tempfile
import unittest
import zipfile
from io import BytesIO
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

  def test_authenticated_user_can_save_local_feedback_and_export_a_review_bundle(self) -> None:
    self._authenticate_as(USER_ID)
    feedback = self.client.get(f"/dev/analysis-runs/{self.trace.run_id}/feedback")
    self.assertEqual(feedback.status_code, 200)
    self.assertEqual(feedback.json()["annotations"], [])

    save = self.client.put(
      f"/dev/analysis-runs/{self.trace.run_id}/feedback",
      json={
        "annotations": [
          {
            "id": "right-knee-occlusion",
            "status": "bad",
            "start_ms": 4000,
            "end_ms": 4600,
            "systems": ["automatic_pose"],
            "issue_types": ["drift"],
            "landmarks": ["right_knee"],
            "expected_behaviors": ["hold_last_reliable", "interpolate_briefly"],
            "severity": "metric_changing",
            "notes": "Do not swap to the left knee when the plate blocks the view.",
            "keyframes": [{"timestamp_ms": 4200, "source_frame_index": 126}],
            "corrections": [
              {
                "timestamp_ms": 4200,
                "source_frame_index": 126,
                "target": "right_knee",
                "x": 0.42,
                "y": 0.71,
                "visibility": "occluded",
              },
            ],
          },
        ],
      },
    )
    self.assertEqual(save.status_code, 200)
    self.assertEqual(save.json()["annotations"][0]["corrections"][0]["target"], "right_knee")
    self.assertTrue((self.service.feedback_dir / f"{self.trace.run_id}.json").is_file())

    export = self.client.get(f"/dev/analysis-runs/{self.trace.run_id}/feedback/export")
    self.assertEqual(export.status_code, 200)
    self.assertIn("peso-analysis-feedback", export.headers["content-disposition"])
    with zipfile.ZipFile(BytesIO(export.content)) as archive:
      self.assertEqual(
        set(archive.namelist()),
        {"summary.json", "trace.json", "stage-events.csv", "frame-timeline.csv", "feedback.json", "feedback-summary.md"},
      )
      feedback_payload = archive.read("feedback.json").decode("utf-8")
      trace_payload = archive.read("trace.json").decode("utf-8")
      self.assertIn("right_knee", feedback_payload)
      self.assertIn("Do not swap", archive.read("feedback-summary.md").decode("utf-8"))
      self.assertNotIn(USER_ID, trace_payload)
      self.assertNotIn("11111111-1111-1111-1111-111111111111", trace_payload)

  def test_authenticated_user_cannot_access_another_users_run(self) -> None:
    self._authenticate_as(OTHER_USER_ID)

    self.assertEqual(self.client.get("/dev/analysis-runs").json(), {"runs": []})
    self.assertEqual(self.client.get(f"/dev/analysis-runs/{self.trace.run_id}").status_code, 404)
    self.assertEqual(self.client.get(f"/dev/analysis-runs/{self.trace.run_id}/events").status_code, 404)
    self.assertEqual(self.client.get(f"/dev/analysis-runs/{self.trace.run_id}/export").status_code, 404)
    self.assertEqual(self.client.get(f"/dev/analysis-runs/{self.trace.run_id}/feedback").status_code, 404)
    self.assertEqual(self.client.put(f"/dev/analysis-runs/{self.trace.run_id}/feedback", json={"annotations": []}).status_code, 404)
    self.assertEqual(self.client.get(f"/dev/analysis-runs/{self.trace.run_id}/feedback/export").status_code, 404)
