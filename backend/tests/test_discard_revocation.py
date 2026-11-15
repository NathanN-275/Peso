from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from uuid import UUID

from fastapi import HTTPException

from app.routes.videos import discard_video
from app.services.storage_cleanup import StorageCleanupService
from app.services.video_repository import VideoRepository
from test_storage_cleanup import FakeStorage, USER_ID, OTHER_USER_ID, settings

VIDEO = '11111111-1111-1111-1111-111111111111'
OTHER_VIDEO = '22222222-2222-2222-2222-222222222222'


def snapshot():
  return {'video_id': VIDEO, 'user_id': USER_ID, 'delete_metadata': False,
          'storage_paths': [f'{USER_ID}/source.mp4'],
          'archive_paths': [f'{USER_ID}/archive.zip'],
          'export_prefixes': [f'{USER_ID}/exports/{VIDEO}-']}


class DiscardRevocationTest(unittest.TestCase):
  def setUp(self):
    self.events = []
    self.row = {'id': VIDEO, 'user_id': USER_ID, 'discarded_at': None, 'is_saved': True}
    self.pending = None
    self.repository = VideoRepository.__new__(VideoRepository)
    self.repository.client = MagicMock()
    self.repository.get_video = MagicMock(side_effect=lambda _id: self.row)
    self.repository.mark_discarded = MagicMock(side_effect=AssertionError('legacy mutation'))
    self.repository.delete_video_with_analysis = MagicMock(side_effect=AssertionError('metadata must remain'))
    self.repository.complete_deletion = MagicMock(side_effect=self.complete)
    self.returned = [snapshot()]
    def execute():
      self.events.append('revoke.commit')
      self.row.update(discarded_at='2026-10-27T20:00:00Z', is_saved=False)
      self.pending = deepcopy(snapshot())
      return SimpleNamespace(data=deepcopy(self.returned))
    self.repository.client.rpc.return_value.execute.side_effect = execute
    self.storage = FakeStorage()
    self.archives = FakeStorage()
    original_list = self.storage.list_storage_prefix
    def listing(prefix):
      self.events.append('storage.list')
      return original_list(prefix)
    self.storage.list_storage_prefix = MagicMock(side_effect=listing)
    for storage, label in [(self.storage, 'video.delete'), (self.archives, 'archive.delete')]:
      original_delete = storage.delete_storage_path
      def delete(path, *, original_delete=original_delete, label=label):
        self.events.append(label)
        original_delete(path)
      storage.delete_storage_path = MagicMock(side_effect=delete)
    self.factory = MagicMock(side_effect=lambda **kwargs: StorageCleanupService(
      repository=kwargs['repository'], storage=self.storage, archive_storage=self.archives, settings=settings()))

  def complete(self, task):
    self.events.append('finalize')
    self.assertEqual(task, self.pending)
    self.pending = None
    return True

  def run_route(self):
    with (
      patch('app.routes.videos.VideoRepository', return_value=self.repository),
      patch('app.routes.videos.StorageCleanupService', self.factory),
      patch('app.routes.videos.AnalysisJobRepository') as jobs,
      patch('app.routes.videos.StorageService') as legacy_storage,
    ):
      try:
        return discard_video(UUID(VIDEO), USER_ID)
      finally:
        jobs.assert_not_called()
        legacy_storage.assert_not_called()
        self.repository.mark_discarded.assert_not_called()
        self.repository.delete_video_with_analysis.assert_not_called()

  def test_commits_atomic_revoke_before_storage_and_finalizes_before_success(self):
    response = self.run_route()
    self.assertTrue(response.discarded)
    self.assertEqual(self.events, ['revoke.commit', 'storage.list', 'video.delete', 'archive.delete', 'finalize'])
    self.repository.client.rpc.assert_called_once_with('revoke_video_media', {
      'p_user_id': USER_ID, 'p_video_ids': [VIDEO], 'p_delete_metadata': False})
    self.assertIsNotNone(self.row['discarded_at'])
    self.assertFalse(self.row['is_saved'])
    self.assertIsNone(self.pending)

  def test_missing_or_foreign_video_is_denied_before_revoke_or_storage(self):
    for row, expected in [(None, 404), ({'id': VIDEO, 'user_id': OTHER_USER_ID}, 403)]:
      with self.subTest(row=row):
        self.row = row
        with self.assertRaises(HTTPException) as raised:
          self.run_route()
        self.assertEqual(raised.exception.status_code, expected)
        self.repository.client.rpc.assert_not_called()
        self.factory.assert_not_called()
        self.assertEqual(self.events, [])

  def test_rpc_failure_has_no_storage_io_or_legacy_fallback(self):
    self.repository.client.rpc.return_value.execute.side_effect = RuntimeError('missing RPC or busy job')
    with self.assertRaises(HTTPException) as raised:
      self.run_route()
    self.assertEqual(raised.exception.status_code, 503)
    self.factory.assert_not_called()
    self.assertEqual(self.events, [])
    self.assertIsNone(self.row['discarded_at'])

  def test_malformed_revocation_contract_never_constructs_cleanup(self):
    malformed = [None, {}, [], [snapshot(), snapshot()], [None]]
    for key, value in [('video_id', OTHER_VIDEO), ('user_id', OTHER_USER_ID), ('delete_metadata', True),
                       ('delete_metadata', 0), ('export_prefixes', []),
                       ('export_prefixes', [f'{USER_ID}/exports/']),
                       ('storage_paths', [f'{OTHER_USER_ID}/bad.mp4']),
                       ('archive_paths', [f'{USER_ID}/../bad.zip']), ('archive_paths', 'bad')]:
      task = snapshot(); task[key] = value; malformed.append([task])
    missing = snapshot(); del missing['storage_paths']; malformed.append([missing])
    for returned in malformed:
      with self.subTest(returned=returned):
        self.returned = returned
        with self.assertRaises(HTTPException) as raised:
          self.run_route()
        self.assertEqual(raised.exception.status_code, 503)
        self.factory.assert_not_called()
        self.storage.list_storage_prefix.assert_not_called()
        self.storage.delete_storage_path.assert_not_called()
        self.archives.delete_storage_path.assert_not_called()

  def test_listing_failure_retains_revocation_and_task_then_same_id_retry_succeeds(self):
    self.storage.list_storage_prefix.side_effect = RuntimeError('offline')
    with self.assertRaises(HTTPException) as raised:
      self.run_route()
    self.assertEqual(raised.exception.status_code, 503)
    self.assertIsNotNone(self.row['discarded_at'])
    self.assertIsNotNone(self.pending)
    self.storage.delete_storage_path.assert_not_called()
    self.archives.delete_storage_path.assert_not_called()
    self.storage.list_storage_prefix.side_effect = lambda _: []
    self.assertTrue(self.run_route().discarded)
    self.assertIsNone(self.pending)

  def test_bucket_failure_retains_revocation_and_task_then_same_id_retry_succeeds(self):
    for storage in (self.storage, self.archives):
      with self.subTest(bucket=storage):
        original = storage.delete_storage_path.side_effect
        storage.delete_storage_path.side_effect = RuntimeError('offline')
        with self.assertRaises(HTTPException) as raised:
          self.run_route()
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIsNotNone(self.row['discarded_at'])
        self.assertIsNotNone(self.pending)
        before = self.repository.complete_deletion.call_count
        storage.delete_storage_path.side_effect = original
        self.assertTrue(self.run_route().discarded)
        self.assertEqual(self.repository.complete_deletion.call_count, before + 1)
        self.assertIsNone(self.pending)

  def test_failed_or_stale_finalization_never_reports_success(self):
    for failure in (False, RuntimeError('database unavailable')):
      with self.subTest(failure=failure):
        self.repository.complete_deletion.side_effect = failure if isinstance(failure, Exception) else None
        self.repository.complete_deletion.return_value = failure
        with self.assertRaises(HTTPException) as raised:
          self.run_route()
        self.assertEqual(raised.exception.status_code, 503)
        self.assertIsNotNone(self.row['discarded_at'])
        self.assertIsNotNone(self.pending)
    self.repository.complete_deletion.side_effect = self.complete
    self.assertTrue(self.run_route().discarded)

  def test_discard_is_independent_of_private_media_feature_flag(self):
    with patch.dict('os.environ', {'PRIVATE_MEDIA_ENABLED': 'false'}):
      self.assertTrue(self.run_route().discarded)
    self.assertEqual(self.events[0], 'revoke.commit')


if __name__ == '__main__':
  unittest.main()
