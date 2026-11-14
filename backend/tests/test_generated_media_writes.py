from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.services.generated_media_writes import write_generated_media


USER = "33333333-3333-3333-3333-333333333333"
VIDEO = "11111111-1111-1111-1111-111111111111"
JOB = "55555555-5555-5555-5555-555555555555"
SOURCE = f"{USER}/source/{VIDEO}.mov"
LEASE = {"p_job_id": JOB, "p_worker_id": "worker", "p_attempt_count": 2}


class GeneratedMediaWritesTest(unittest.TestCase):
  def setUp(self):
    settings = patch('app.services.generated_media_writes.get_settings', return_value=SimpleNamespace(
      max_user_reserved_bytes=300, object_storage_limit_bytes=500,
    ))
    settings.start();self.addCleanup(settings.stop)
    self.directory = TemporaryDirectory();self.addCleanup(self.directory.cleanup)
    self.file = Path(self.directory.name)/"synthetic.jpg";self.file.write_bytes(b"synthetic")
    self.video = {"id": VIDEO, "user_id": USER, "storage_path": SOURCE,
                  "save_state": "saved", "is_saved": True}
    self.storage = MagicMock();self.storage.bucket = "videos"
    self.events = []
    self.admitted = lambda row: [dict(row)]
    self.persisted = lambda row: [dict(row)]
    self.observed = True
    def rpc(name, parameters):
      if name == "admit_private_media_generated_write":
        self.assertEqual(parameters['p_max_user_bytes'],300)
        self.assertEqual(parameters['p_max_global_bytes'],500)
        self.row = {**{key[2:]: value for key, value in parameters.items()
                      if key not in {'p_max_user_bytes','p_max_global_bytes'}}, "state": "dispatching"}
        return SimpleNamespace(execute=self.admit)
      self.assertEqual(name, "observe_private_media_generated_write_success")
      self.assertEqual(parameters, {"p_" + key: value for key, value in self.row.items() if key != "state"})
      return SimpleNamespace(execute=self.observe)
    self.storage.client.rpc.side_effect = rpc
    self.storage.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect = self.readback
    self.storage.create_file.side_effect = lambda *_args, **_kwargs: self.events.append("upload")

  def admit(self):
    self.events.append("admit")
    return SimpleNamespace(data=self.admitted(self.row))

  def readback(self):
    self.events.append("readback")
    return SimpleNamespace(data=self.persisted(self.row))

  def observe(self):
    self.events.append("observe")
    return SimpleNamespace(data=self.observed)

  def write(self, purpose="thumbnail", **changes):
    fields = dict(video=self.video, purpose=purpose, local_path=self.file, storage=self.storage,
                  analysis_lease=None if purpose == "thumbnail_backfill" else LEASE)
    fields.update(changes)
    return write_generated_media(**fields)

  def test_fresh_committed_exact_attempt_precedes_create_only_upload_and_success_observation(self):
    path = self.write()
    self.assertEqual(self.events, ["admit", "readback", "upload", "observe"])
    self.assertEqual(self.row, dict(attempt_id=self.row["attempt_id"], user_id=USER, video_id=VIDEO,
      purpose="thumbnail", bucket="videos", storage_path=path, source_path=SOURCE,
      content_type="image/jpeg", size_bytes=9, job_id=JOB, worker_id="worker", attempt_count=2, state="dispatching"))
    self.assertEqual(str(UUID(self.row["attempt_id"])), self.row["attempt_id"])
    self.assertTrue(path.endswith(f"{VIDEO}-{self.row['attempt_id']}-thumb-v3.jpg"))
    self.storage.create_file.assert_called_once_with(path, self.file, "image/jpeg", cache_control="31536000")
    self.storage.upload_file.assert_not_called();self.storage.delete_storage_path.assert_not_called()
    self.storage.client.table.assert_called_once_with("private_media_generated_writes")

  def test_playback_and_saved_thumbnail_backfill_bind_their_exact_context(self):
    for purpose, mime, suffix in (("playback", "video/mp4", "h264-720p-v1.mp4"),
                                  ("thumbnail_backfill", "image/jpeg", "thumb-v3.jpg")):
      with self.subTest(purpose=purpose):
        path = self.write(purpose)
        self.assertEqual(self.row["purpose"], purpose)
        self.assertEqual(self.row["content_type"], mime)
        self.assertTrue(path.endswith(suffix))
        self.assertEqual(self.row["job_id"], None if purpose == "thumbnail_backfill" else JOB)
        self.assertEqual(self.row["worker_id"], None if purpose == "thumbnail_backfill" else "worker")
        self.assertEqual(self.row["attempt_count"], None if purpose == "thumbnail_backfill" else 2)

  def test_independent_generations_never_reuse_a_path(self):
    first, second = self.write(), self.write()
    self.assertNotEqual(first, second)
    self.assertEqual(self.storage.create_file.call_count, 2)

  def test_bucket_and_actual_source_and_size_are_not_inferred_from_a_filename(self):
    self.storage.bucket = "private-video-bucket"
    self.video["storage_path"] = f"{USER}/uploads/actual-source.mov"
    self.file.write_bytes(b"x"*17)
    self.write()
    self.assertEqual(self.row["bucket"], "private-video-bucket")
    self.assertEqual(self.row["source_path"], self.video["storage_path"])
    self.assertEqual(self.row["size_bytes"], 17)

  def test_lost_or_denied_admission_never_reads_back_or_uploads_or_retries(self):
    def failed(_row): raise TimeoutError("lost admission response")
    self.admitted = failed
    with self.assertRaises(TimeoutError): self.write()
    self.assertEqual(self.events, ["admit"])
    self.storage.client.rpc.assert_called_once();self.storage.create_file.assert_not_called()

  def test_missing_duplicate_unknown_fields_or_malformed_admission_cannot_dispatch(self):
    for changed in (None, {}, [], True, [True], "receipt"):
      with self.subTest(changed=changed):
        self.admitted = lambda _row, changed=changed: changed
        with self.assertRaises(RuntimeError): self.write()
    for transform in (lambda row: [row, row], lambda row: [{**row, "unknown": "field"}],
                      lambda row: [{**row, "state": "succeeded"}]):
      self.admitted = transform
      with self.assertRaises(RuntimeError): self.write()
    self.storage.client.table.assert_not_called();self.storage.create_file.assert_not_called()

  def test_every_wrong_admission_binding_prevents_upload(self):
    fields = ("attempt_id", "user_id", "video_id", "purpose", "bucket", "storage_path",
              "source_path", "content_type", "size_bytes", "job_id", "worker_id", "attempt_count")
    for key in fields:
      with self.subTest(key=key):
        self.admitted = lambda row, key=key: [{**row, key: "wrong"}]
        with self.assertRaises(RuntimeError): self.write()
    self.storage.create_file.assert_not_called();self.storage.client.table.assert_not_called()

  def test_rollback_missing_malformed_or_mismatched_readback_never_dispatches(self):
    for transform in (lambda _row: [], lambda _row: None, lambda _row: {},
                      lambda row: [row, row], lambda row: [{**row, "source_path": SOURCE+"changed"}],
                      lambda row: [{**row, "state": "succeeded"}]):
      with self.subTest(transform=transform):
        self.persisted = transform
        with self.assertRaises(RuntimeError): self.write()
    self.storage.create_file.assert_not_called()

  def test_equal_truthy_readback_cannot_substitute_boolean_for_integer(self):
    self.file.write_bytes(b"x")
    self.persisted = lambda row: [{**row, "size_bytes": True}]
    with self.assertRaises(RuntimeError): self.write()
    self.storage.create_file.assert_not_called()

  def test_uncertain_readback_never_retries_or_dispatches(self):
    def failed(_row): raise TimeoutError("readback unavailable")
    self.persisted = failed
    with self.assertRaises(TimeoutError): self.write()
    self.assertEqual(self.events, ["admit", "readback"])
    self.storage.client.rpc.assert_called_once();self.storage.create_file.assert_not_called()

  def test_upload_failure_retains_pending_attempt_without_success_or_compensating_delete(self):
    self.storage.create_file.side_effect = TimeoutError("unknown upload outcome")
    with self.assertRaises(TimeoutError): self.write()
    self.storage.client.rpc.assert_called_once();self.storage.create_file.assert_called_once()
    self.storage.delete_storage_path.assert_not_called()

  def test_lost_success_acknowledgement_never_replays_upload_or_deletes_generated_bytes(self):
    for value in (None, False, 1, "true", [True], {}):
      with self.subTest(value=value):
        self.observed = value
        with self.assertRaises(RuntimeError): self.write()
    self.assertEqual(self.storage.create_file.call_count, 6)
    self.assertEqual(self.storage.client.rpc.call_count, 12)
    self.storage.delete_storage_path.assert_not_called()

  def test_invalid_owner_video_source_or_purpose_is_denied_before_admission(self):
    for changes, error in (({"user_id": "invalid"}, ValueError),
                           ({"id": "00000000-0000-0000-0000-000000000000"}, ValueError),
                           ({"storage_path": f"{JOB}/source/foreign.mp4"}, HTTPException)):
      with self.subTest(changes=changes), self.assertRaises(error):
        self.write(video={**self.video, **changes})
    with self.assertRaises(ValueError): self.write(purpose="archive")
    self.storage.client.rpc.assert_not_called();self.storage.create_file.assert_not_called()

  def test_unbound_malformed_or_cross_purpose_analysis_context_is_denied(self):
    for binding in (None, {}, {**LEASE, "extra": "context"}, {**LEASE, "p_job_id": "not-a-job"},
                    {**LEASE, "p_worker_id": " worker"}, {**LEASE, "p_attempt_count": True},
                    {**LEASE, "p_attempt_count": 0}):
      with self.subTest(binding=binding), self.assertRaises(ValueError): self.write(analysis_lease=binding)
    with self.assertRaises(ValueError): self.write("thumbnail_backfill", analysis_lease=LEASE)
    self.storage.client.rpc.assert_not_called();self.storage.create_file.assert_not_called()

  def test_empty_or_missing_generated_file_is_denied_before_admission(self):
    self.file.write_bytes(b"")
    with self.assertRaises(ValueError): self.write()
    self.file.unlink()
    with self.assertRaises(FileNotFoundError): self.write()
    self.storage.client.rpc.assert_not_called()


if __name__ == "__main__":
  unittest.main()
