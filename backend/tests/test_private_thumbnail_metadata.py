from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.routes import videos

OWNER = '11111111-1111-4111-8111-111111111111'
VIDEO = '22222222-2222-4222-8222-222222222222'
JOB = '33333333-3333-4333-8333-333333333333'


class PrivateThumbnailMetadataTest(unittest.TestCase):
  def setUp(self):
    self.video = dict(id=VIDEO, user_id=OWNER, exercise_type='squat', view_type='side', status='completed',
                      save_state='saved', storage_state='available', thumbnail_path=f'{OWNER}/thumbnails/current.jpg',
                      created_at='2026-11-03T12:00:00+00:00')
    self.storage = MagicMock()
    self.storage.create_signed_url.side_effect = AssertionError('Metadata reads must not mint a media capability.')
    self.settings = SimpleNamespace(private_media_enabled=True, max_user_in_progress_videos=3)
    self.patch = patch.object(videos, 'get_settings', return_value=self.settings)
    self.patch.start(); self.addCleanup(self.patch.stop)

  def test_saved_projection_returns_availability_without_provider_path_url_or_storage_calls(self):
    result = videos._saved_video_response(video=self.video, analysis=None, storage=self.storage, user_id=OWNER)
    self.assertTrue(result.thumbnail_available)
    self.assertIsNone(result.thumbnail_path); self.assertIsNone(result.thumbnail_url)
    self.assertIsNone(result.video_url); self.assertIsNone(result.storage_path)
    self.assertEqual(self.storage.mock_calls, [])

  def test_missing_pruned_or_discarded_preview_is_unavailable_without_signing(self):
    for changes in [dict(thumbnail_path=None), dict(storage_state='pruned'), dict(discarded_at='2026-11-03T12:01:00+00:00')]:
      with self.subTest(changes=changes):
        result = videos._saved_video_response(video={**self.video, **changes}, analysis=None, storage=self.storage, user_id=OWNER)
        self.assertFalse(result.thumbnail_available); self.assertIsNone(result.thumbnail_url)
    self.assertEqual(self.storage.mock_calls, [])

  def test_actual_saved_list_page_and_overview_share_the_metadata_only_boundary(self):
    repository = MagicMock()
    repository.list_saved_videos.return_value = [self.video]
    repository.list_saved_videos_page.return_value = [self.video]
    repository.get_latest_analysis_results.return_value = {}
    repository.get_analysis_result.return_value = None
    with patch.object(videos, 'VideoRepository', return_value=repository), patch.object(videos, 'StorageService', return_value=self.storage):
      results = [videos.list_saved_videos(OWNER)[0], videos.list_saved_videos_page(None, 20, None, OWNER).items[0],
                 videos.get_saved_video_overview(OWNER).groups[0].preview_items[0]]
    for result in results:
      self.assertTrue(result.thumbnail_available); self.assertIsNone(result.thumbnail_url); self.assertIsNone(result.thumbnail_path)
    self.assertEqual(self.storage.mock_calls, [])

  def test_actual_activity_endpoint_does_not_sign_a_preview(self):
    repository, jobs = MagicMock(), MagicMock()
    repository.list_analysis_activity_videos.return_value = [{**self.video, 'save_state':'pending'}]
    repository.count_user_in_progress_videos.return_value = 0
    jobs.latest_for_videos.return_value = {VIDEO:dict(id=JOB, video_id=VIDEO, status='completed', stage='ready', created_at=self.video['created_at'])}
    with patch.object(videos, 'VideoRepository', return_value=repository), patch.object(videos, 'AnalysisJobRepository', return_value=jobs), patch.object(videos, 'StorageService', return_value=self.storage):
      result = videos.get_analysis_activity(OWNER)
    self.assertEqual(len(result.items), 1); self.assertTrue(result.items[0].thumbnail_available)
    self.assertIsNone(result.items[0].thumbnail_url); self.assertEqual(self.storage.mock_calls, [])


if __name__ == '__main__':
  unittest.main()
