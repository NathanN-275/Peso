from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.analysis.pipeline import _finalize_storage_assets


VIDEO_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "33333333-3333-3333-3333-333333333333"
JOB_ID = "55555555-5555-5555-5555-555555555555"
ATTEMPT_ID = "77777777-7777-7777-7777-777777777777"
OTHER_USER_ID = "44444444-4444-4444-4444-444444444444"
ORIGINAL_PATH = f"{USER_ID}/uploads/{VIDEO_ID}.mov"
THUMBNAIL_PATH = f"{USER_ID}/thumbnails/{VIDEO_ID}-{ATTEMPT_ID}-thumb-v3.jpg"
PLAYBACK_PATH = f"{USER_ID}/playback/{VIDEO_ID}-{ATTEMPT_ID}-h264-720p-v1.mp4"
BINDING = {"p_job_id": JOB_ID, "p_worker_id": "worker", "p_attempt_count": 2}


class VideoAssetFinalizationTest(unittest.TestCase):
  def setUp(self):
    self.video = {"id": VIDEO_ID, "user_id": USER_ID, "storage_path": ORIGINAL_PATH,
                  "tracking_setup": "compact-json-metadata-only"}
    self.repository, self.storage = MagicMock(), MagicMock()
    self.repository.analysis_write_binding.return_value = dict(BINDING)
    self.generated = patch("app.analysis.pipeline.write_generated_media",
                           side_effect=lambda **fields: THUMBNAIL_PATH if fields["purpose"] == "thumbnail" else PLAYBACK_PATH).start()
    self.addCleanup(patch.stopall)

  def finalize(self):
    _finalize_storage_assets(video=self.video, video_id=VIDEO_ID, source_path=Path("/tmp/source.mov"),
                             repository=self.repository, storage=self.storage)

  def test_skips_playback_and_original_delete_when_thumbnail_generation_fails(self):
    with patch("app.analysis.pipeline.create_video_thumbnail", side_effect=RuntimeError("thumbnail failed")), patch(
      "app.analysis.pipeline.compress_video_for_playback") as compress:
      self.finalize()
    compress.assert_not_called();self.generated.assert_not_called()
    self.storage.delete_storage_path.assert_not_called();self.repository.update_video.assert_not_called()

  def test_does_not_delete_original_when_playback_compression_fails(self):
    with patch("app.analysis.pipeline.create_video_thumbnail"), patch(
      "app.analysis.pipeline.compress_video_for_playback", side_effect=RuntimeError("compression failed")):
      self.finalize()
    self.repository.update_video.assert_called_once_with(VIDEO_ID, {"thumbnail_path": THUMBNAIL_PATH})
    self.storage.delete_storage_path.assert_not_called()

  def test_publishes_exact_attempt_paths_and_observes_original_delete_only_after_confirmed_metadata(self):
    events = []
    def publish(_video_id, fields):
      events.append("thumbnail" if "thumbnail_path" in fields else "playback")
      return {"id": VIDEO_ID, **fields}
    self.repository.update_video.side_effect = publish
    self.storage.delete_storage_path.side_effect = lambda _path: events.append("delete")
    with patch("app.analysis.pipeline.create_video_thumbnail"), patch("app.analysis.pipeline.compress_video_for_playback"):
      self.finalize()
    self.assertEqual(events, ["thumbnail", "playback", "delete"])
    self.assertEqual([call.kwargs["purpose"] for call in self.generated.call_args_list], ["thumbnail", "playback"])
    for call in self.generated.call_args_list:
      self.assertEqual(call.kwargs["video"], self.video)
      self.assertEqual(call.kwargs["analysis_lease"], BINDING)
      self.assertIs(call.kwargs["storage"], self.storage)
    self.repository.update_video.assert_any_call(VIDEO_ID, {"thumbnail_path": THUMBNAIL_PATH})
    playback = self.repository.update_video.call_args_list[1].args[1]
    self.assertEqual(playback["playback_path"], PLAYBACK_PATH)
    self.assertEqual(playback["original_storage_path"], ORIGINAL_PATH)
    self.storage.upload_file.assert_not_called();self.storage.create_file.assert_not_called()
    self.storage.delete_storage_path.assert_called_once_with(ORIGINAL_PATH)

  def test_lost_thumbnail_publication_keeps_generated_bytes_and_skips_playback(self):
    self.repository.update_video.side_effect = TimeoutError("possibly committed thumbnail")
    with patch("app.analysis.pipeline.create_video_thumbnail"), patch("app.analysis.pipeline.compress_video_for_playback") as compress:
      self.finalize()
    self.generated.assert_called_once();compress.assert_not_called()
    self.storage.delete_storage_path.assert_not_called()

  def test_lost_playback_publication_preserves_generated_artifact_and_original(self):
    self.repository.update_video.side_effect = [{"thumbnail_path": THUMBNAIL_PATH}, TimeoutError("possibly committed playback")]
    with patch("app.analysis.pipeline.create_video_thumbnail"), patch("app.analysis.pipeline.compress_video_for_playback"):
      self.finalize()
    self.assertEqual(self.generated.call_count, 2)
    self.storage.delete_storage_path.assert_not_called()

  def test_unknown_generated_upload_prevents_metadata_publication_or_deletion(self):
    self.generated.side_effect = TimeoutError("unknown generated write")
    with patch("app.analysis.pipeline.create_video_thumbnail"), patch("app.analysis.pipeline.compress_video_for_playback") as compress:
      self.finalize()
    self.repository.update_video.assert_not_called();self.storage.delete_storage_path.assert_not_called()
    compress.assert_not_called()

  def test_missing_analysis_binding_stops_before_generation(self):
    self.repository.analysis_write_binding.side_effect = RuntimeError("unbound")
    with patch("app.analysis.pipeline.create_video_thumbnail") as thumbnail, self.assertRaises(RuntimeError):
      self.finalize()
    thumbnail.assert_not_called();self.generated.assert_not_called()

  def test_rejects_wrong_source_owner_or_video_before_work(self):
    for changed, error in (({"storage_path": f"{OTHER_USER_ID}/uploads/{VIDEO_ID}.mov"}, HTTPException),
                           ({"id": JOB_ID}, ValueError)):
      with self.subTest(changed=changed), patch("app.analysis.pipeline.create_video_thumbnail") as thumbnail:
        self.video.update(changed)
        with self.assertRaises(error): self.finalize()
        thumbnail.assert_not_called();self.generated.assert_not_called()
        self.video.update(id=VIDEO_ID, storage_path=ORIGINAL_PATH)


if __name__ == "__main__":
  unittest.main()
