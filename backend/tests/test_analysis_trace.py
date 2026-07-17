from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from app.services.analysis_trace import AnalysisTraceService


USER_ID = "33333333-3333-3333-3333-333333333333"
OTHER_USER_ID = "44444444-4444-4444-4444-444444444444"
VIDEO_ID = "11111111-1111-1111-1111-111111111111"


class AnalysisTraceServiceTest(unittest.TestCase):
  def setUp(self) -> None:
    self.temporary_directory = tempfile.TemporaryDirectory()
    self.trace_dir = Path(self.temporary_directory.name) / "traces"

  def tearDown(self) -> None:
    self.temporary_directory.cleanup()

  def _service(self, *, max_runs: int = 20) -> AnalysisTraceService:
    return AnalysisTraceService(enabled=True, trace_dir=self.trace_dir, max_runs=max_runs)

  @staticmethod
  def _start(service: AnalysisTraceService, *, user_id: str = USER_ID, video_id: str = VIDEO_ID):
    return service.start(
      video_id=video_id,
      user_id=user_id,
      exercise_type="back_squat",
      view_type="side",
      model_version="trace-test-model",
    )

  def test_successful_trace_is_ordered_atomically_persisted_and_finalized(self) -> None:
    service = self._service()
    trace = self._start(service)
    trace.event("video_loaded", {"status": "uploaded"})
    trace.stage("pose_estimation", 123)
    trace.snapshot("raw_pose", frames=[{"source_frame_index": 0, "timestamp_ms": 0, "landmarks": {}}])
    trace.complete({"diagnostics": {"pose_backend": "mediapipe"}}, {"pose_estimation": 123})

    stored = service.get_run(trace.run_id, USER_ID)

    self.assertIsNotNone(stored)
    assert stored is not None
    self.assertEqual(stored["status"], "completed")
    self.assertEqual(stored["video_id"], VIDEO_ID)
    self.assertIsNotNone(stored["finished_at"])
    self.assertEqual([event["index"] for event in stored["events"]], list(range(len(stored["events"]))))
    self.assertEqual(stored["events"][0]["type"], "analysis_started")
    self.assertEqual(stored["events"][-1]["type"], "analysis_completed")
    self.assertTrue((self.trace_dir / f"{trace.run_id}.json").is_file())

    replayed = list(service.iter_events(trace.run_id, USER_ID))
    self.assertEqual([event["index"] for event in replayed], list(range(len(replayed))))

  def test_failed_trace_preserves_partial_events_and_error(self) -> None:
    service = self._service()
    trace = self._start(service)
    trace.snapshot("pin_fusion", manual_tracking={"tracks": {"upper_back": []}})
    trace.fail(ValueError("pose detector stopped"), {"pin_assistance": 44})

    stored = service.get_run(trace.run_id, USER_ID)

    self.assertIsNotNone(stored)
    assert stored is not None
    self.assertEqual(stored["status"], "failed")
    final_payload = stored["events"][-1]["payload"]
    self.assertEqual(final_payload["error"]["type"], "ValueError")
    self.assertEqual(final_payload["error"]["message"], "pose detector stopped")
    self.assertIn("pin_fusion", [event["payload"].get("name") for event in stored["events"]])

  def test_retention_prunes_oldest_completed_runs_without_removing_running_run(self) -> None:
    service = self._service(max_runs=2)
    first = self._start(service, video_id="video-1")
    first.complete({}, {})
    second = self._start(service, video_id="video-2")
    second.complete({}, {})
    running = self._start(service, video_id="video-running")
    third = self._start(service, video_id="video-3")
    third.complete({}, {})

    runs = service.list_runs(USER_ID)

    self.assertEqual({run["run_id"] for run in runs}, {second.run_id, third.run_id, running.run_id})
    self.assertFalse((self.trace_dir / f"{first.run_id}.json").exists())
    self.assertTrue((self.trace_dir / f"{running.run_id}.json").exists())

  def test_export_contains_only_redacted_diagnostic_artifacts(self) -> None:
    service = self._service()
    trace = self._start(service)
    trace.snapshot(
      "pose_repair",
      frames=[{
        "source_frame_index": 4,
        "timestamp_ms": 220,
        "landmarks": {
          "left_shoulder": {
            "accepted_source": "pose_repair_velocity",
            "pose_repair_reasons": ["occlusion"],
          },
        },
      }],
      signed_url="https://example.supabase.co/signed/never-export",
      nested={
        "authorization": "Bearer never-export",
        "storage_path": "private/never-export.mov",
        "token": "never-export",
        "userId": USER_ID,
        "videoId": VIDEO_ID,
        "playbackUrl": "https://example.supabase.co/playback/never-export",
      },
    )
    trace.complete({"video_id": VIDEO_ID, "user_id": USER_ID}, {})

    archive = service.build_export(trace.run_id, USER_ID)

    self.assertIsNotNone(archive)
    assert archive is not None
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
      self.assertEqual(
        set(bundle.namelist()),
        {"summary.json", "trace.json", "frame-timeline.csv", "stage-events.csv"},
      )
      trace_payload = bundle.read("trace.json").decode("utf-8")
      self.assertNotIn(USER_ID, trace_payload)
      self.assertNotIn(VIDEO_ID, trace_payload)
      self.assertNotIn("never-export", trace_payload)
      self.assertIn("[redacted]", trace_payload)
      summary = json.loads(bundle.read("summary.json"))
      self.assertEqual(summary["status"], "completed")
      self.assertIn("source_frame_index", bundle.read("frame-timeline.csv").decode("utf-8"))
      self.assertIn("duration_ms", bundle.read("stage-events.csv").decode("utf-8"))

  def test_review_projection_keeps_only_dashboard_landmarks_and_bounded_diagnostics(self) -> None:
    service = self._service()
    trace = self._start(service)
    trace.snapshot("raw_pose", frames=[{
      "source_frame_index": 4,
      "timestamp_ms": 220,
      "frame_width": 405,
      "frame_height": 720,
      "landmarks": {
        "right_knee": {"x": 0.4, "y": 0.7, "visibility": 0.9, "z": -0.2},
        "right_eye": {"x": 0.5, "y": 0.2, "visibility": 0.9},
      },
    }])
    trace.snapshot("pin_fusion", manual_tracking={"tracks": {"upper_back": {
      "4": {"x": 0.3, "y": 0.4, "confidence": 0.9, "unneeded": "omit"},
    }}})
    trace.snapshot("barbell_tracking", barbell_path={"available": True, "points": [{"time": 0.22, "x": 0.5, "y": 0.4, "descriptor": "not-for-review"}]}, diagnostics={"frames": list(range(30))})
    trace.complete({}, {})

    review = service.get_review(trace.run_id, USER_ID)

    self.assertIsNotNone(review)
    assert review is not None
    raw = next(event for event in review["events"] if event["payload"].get("name") == "raw_pose")
    self.assertEqual(set(raw["payload"]["frames"][0]["landmarks"]), {"right_knee"})
    pins = next(event for event in review["events"] if event["payload"].get("name") == "pin_fusion")
    self.assertEqual(pins["payload"]["manual_tracking"]["tracks"]["upper_back"]["4"], {"x": 0.3, "y": 0.4, "confidence": 0.9})
    barbell = next(event for event in review["events"] if event["payload"].get("name") == "barbell_tracking")
    self.assertEqual(barbell["payload"]["barbell_path"]["points"][0]["x"], 0.5)
    self.assertNotIn("descriptor", barbell["payload"]["barbell_path"]["points"][0])
    self.assertEqual(barbell["payload"]["diagnostics"]["frames"], {"item_count": 30})

  def test_owner_cannot_read_another_users_trace(self) -> None:
    service = self._service()
    trace = self._start(service)
    trace.complete({}, {})

    self.assertIsNone(service.get_run(trace.run_id, OTHER_USER_ID))
    self.assertIsNone(service.build_export(trace.run_id, OTHER_USER_ID))
    self.assertEqual(service.list_runs(OTHER_USER_ID), [])
