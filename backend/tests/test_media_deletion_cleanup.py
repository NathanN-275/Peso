from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import MagicMock, patch

from app.services.storage_cleanup import StorageCleanupService
from app.services.video_repository import VideoRepository
from test_storage_cleanup import FakeRepository, FakeStorage, NOW, USER_ID, OTHER_USER_ID, settings

VIDEO_ID = '11111111-1111-1111-1111-111111111111'


def task():
  return {'video_id': VIDEO_ID, 'user_id': USER_ID,
          'storage_paths': [f'{USER_ID}/original.mp4'],
          'archive_paths': [f'{USER_ID}/archive.zip'],
          'export_prefixes': [f'{USER_ID}/exports/{VIDEO_ID}-'], 'delete_metadata': True}


class MediaDeletionCleanupTest(unittest.TestCase):
  def setUp(self):
    self.repository = FakeRepository()
    self.snapshot = task()
    self.repository.pending_deletions[VIDEO_ID] = self.snapshot
    self.storage = FakeStorage()
    self.archive_storage = FakeStorage()
    self.service = StorageCleanupService(self.repository, self.storage, settings(),
                                         archive_storage=self.archive_storage)

  def test_targeted_cleanup_does_not_scan_storage_retention_or_other_tasks(self):
    other = task(); other['video_id'] = '22222222-2222-2222-2222-222222222222'
    self.repository.pending_deletions[other['video_id']] = other
    with (
      patch.object(self.repository, 'list_pending_deletions', side_effect=AssertionError('global task scan')),
      patch.object(self.repository, 'list_expired_pending_videos', side_effect=AssertionError('retention scan')),
      patch.object(self.repository, 'list_storage_referenced_videos', side_effect=AssertionError('reference scan')),
      patch.object(self.storage, 'list_storage_objects_recursive', side_effect=AssertionError('global storage scan')),
    ):
      report = self.service.process_deletions([self.snapshot])
    self.assertFalse(report.errors)
    self.assertEqual(report.deleted_count, 1)
    self.assertEqual(list(self.repository.pending_deletions), [other['video_id']])

  def test_targeted_cleanup_validates_all_tasks_before_storage_io(self):
    bad = task(); bad['video_id'] = 'invalid'
    for tasks in (None, [], [self.snapshot, bad], [self.snapshot, self.snapshot]):
      with self.subTest(tasks=tasks), patch.object(self.storage, 'list_storage_prefix') as listed:
        report = self.service.process_deletions(tasks)
      self.assertTrue(report.errors)
      self.assertEqual(report.deleted_count, 0)
      listed.assert_not_called()
      self.assertEqual(self.storage.deleted_paths, [])
      self.assertEqual(self.archive_storage.deleted_paths, [])
      self.assertIn(VIDEO_ID, self.repository.pending_deletions)

  def test_targeted_dry_run_preserves_both_buckets_and_snapshot(self):
    report = self.service.process_deletions([self.snapshot], dry_run=True)
    self.assertFalse(report.errors)
    self.assertEqual(report.deleted_count, 0)
    self.assertEqual(report.storage_objects, 2)
    self.assertEqual(self.storage.deleted_paths, [])
    self.assertEqual(self.archive_storage.deleted_paths, [])
    self.assertIn(VIDEO_ID, self.repository.pending_deletions)

  def test_deletes_separate_buckets_and_acknowledges_exact_snapshot(self):
    shared_name = f'{USER_ID}/same-name.mp4'
    self.snapshot['storage_paths'] = [shared_name]
    self.snapshot['archive_paths'] = [shared_name]
    self.repository.complete_deletion = MagicMock(return_value=True)
    report = self.service.run(now=NOW)
    self.assertEqual(self.storage.deleted_paths, [shared_name])
    self.assertEqual(self.archive_storage.deleted_paths, [shared_name])
    self.assertEqual(report.storage_objects, 2)
    self.assertEqual(report.deleted_count, 1)
    self.repository.complete_deletion.assert_called_once_with(self.snapshot)

  def test_validates_entire_snapshot_before_listing_or_deleting(self):
    invalid = [
      ('storage_paths', [f'{OTHER_USER_ID}/bad']), ('archive_paths', [f'{OTHER_USER_ID}/bad']),
      ('archive_paths', [None]), ('archive_paths', 'not-an-array'),
      ('export_prefixes', [f'{USER_ID}/exports/']), ('export_prefixes', [None]),
      ('delete_metadata', 'false'), ('video_id', 'invalid'), ('user_id', 'invalid'),
    ]
    for key, value in invalid:
      with self.subTest(key=key, value=value):
        self.snapshot.clear(); self.snapshot.update(task()); self.snapshot[key] = value
        with patch.object(self.storage, 'list_storage_prefix') as listed:
          report = self.service.run(now=NOW)
        listed.assert_not_called()
        self.assertTrue(report.errors)
        self.assertEqual(self.storage.deleted_paths, [])
        self.assertEqual(self.archive_storage.deleted_paths, [])
        self.assertIn(VIDEO_ID, self.repository.pending_deletions)

  def test_listed_export_outside_exact_prefix_rejects_both_buckets(self):
    with patch.object(self.storage, 'list_storage_prefix', return_value=[f'{USER_ID}/another-video.mp4']):
      report = self.service.run(now=NOW)
    self.assertTrue(report.errors)
    self.assertEqual(self.storage.deleted_paths, [])
    self.assertEqual(self.archive_storage.deleted_paths, [])

  def test_export_listing_failure_keeps_task_without_any_deletion(self):
    with patch.object(self.storage, 'list_storage_prefix', side_effect=RuntimeError('offline')):
      report = self.service.run(now=NOW)
    self.assertTrue(report.errors)
    self.assertEqual(self.storage.deleted_paths, [])
    self.assertEqual(self.archive_storage.deleted_paths, [])
    self.assertIn(VIDEO_ID, self.repository.pending_deletions)

  def test_archive_failure_retries_both_buckets_and_keeps_snapshot(self):
    before = deepcopy(self.snapshot)
    with patch.object(self.archive_storage, 'delete_storage_path', side_effect=RuntimeError('offline')):
      failed = self.service.run(now=NOW)
    self.assertTrue(failed.errors)
    self.assertEqual(failed.deleted_count, 0)
    self.assertEqual(self.repository.pending_deletions[VIDEO_ID], before)
    self.assertEqual(self.service.run(now=NOW).deleted_count, 1)
    self.assertEqual(self.repository.pending_deletions, {})

  def test_original_failure_cannot_be_acknowledged_after_successful_archive_delete(self):
    with patch.object(self.storage, 'delete_storage_path', side_effect=RuntimeError('offline')):
      report = self.service.run(now=NOW)
    self.assertEqual(report.deleted_count, 0)
    self.assertIn(VIDEO_ID, self.repository.pending_deletions)
    self.assertEqual(self.archive_storage.deleted_paths, self.snapshot['archive_paths'])

  def test_stale_finalization_retains_task_and_reports_retry(self):
    self.repository.complete_deletion = MagicMock(return_value=False)
    report = self.service.run(now=NOW)
    self.assertEqual(report.deleted_count, 0)
    self.assertTrue(report.errors)
    self.assertIn(VIDEO_ID, self.repository.pending_deletions)

  def test_finalization_failure_retains_task(self):
    self.repository.complete_deletion = MagicMock(side_effect=RuntimeError('offline'))
    report = self.service.run(now=NOW)
    self.assertEqual(report.deleted_count, 0)
    self.assertTrue(report.errors)
    self.assertIn(VIDEO_ID, self.repository.pending_deletions)

  def test_dry_run_never_constructs_archive_client_or_finalizes(self):
    self.service.archive_storage = None
    self.repository.complete_deletion = MagicMock()
    with patch('app.services.storage_cleanup.StorageService') as constructor:
      report = self.service.run(now=NOW, dry_run=True)
    constructor.assert_not_called()
    self.repository.complete_deletion.assert_not_called()
    self.assertFalse(report.errors)
    self.assertEqual(report.storage_objects, 2)
    self.assertEqual(self.storage.deleted_paths, [])
    self.assertEqual(self.archive_storage.deleted_paths, [])

  def test_archive_client_is_bound_to_archive_bucket(self):
    self.service.archive_storage = None
    with patch('app.services.storage_cleanup.StorageService', return_value=self.archive_storage) as constructor:
      report = self.service.run(now=NOW)
    constructor.assert_called_once_with(bucket='saved-lift-exports')
    self.assertEqual(report.deleted_count, 1)
    self.assertEqual(self.archive_storage.deleted_paths, self.snapshot['archive_paths'])

  def test_archive_client_failure_prevents_both_bucket_deletions(self):
    self.service.archive_storage = None
    with patch('app.services.storage_cleanup.StorageService', side_effect=RuntimeError('offline')):
      report = self.service.run(now=NOW)
    self.assertTrue(report.errors)
    self.assertEqual(self.storage.deleted_paths, [])
    self.assertEqual(self.archive_storage.deleted_paths, [])
    self.assertIn(VIDEO_ID, self.repository.pending_deletions)

  def test_empty_storage_snapshots_can_be_acknowledged(self):
    self.snapshot.update(storage_paths=[], archive_paths=[], export_prefixes=[])
    report = self.service.run(now=NOW)
    self.assertFalse(report.errors)
    self.assertEqual(report.deleted_count, 1)


class MediaDeletionRepositoryTest(unittest.TestCase):
  def setUp(self):
    self.client = MagicMock()
    with patch('app.services.video_repository.get_supabase_admin_client', return_value=self.client):
      self.repository = VideoRepository()

  def test_discard_revocation_has_no_table_fallback_and_returns_exact_task(self):
    item = task(); item['delete_metadata'] = False
    self.client.rpc.return_value.execute.return_value.data = [item]
    self.assertEqual(self.repository.revoke_for_discard(VIDEO_ID, USER_ID), item)
    self.client.rpc.assert_called_once_with('revoke_video_media', {
      'p_user_id': USER_ID, 'p_video_ids': [VIDEO_ID], 'p_delete_metadata': False})
    self.client.table.assert_not_called()
    self.client.rpc.return_value.execute.side_effect = RuntimeError('missing RPC')
    with self.assertRaises(RuntimeError):
      self.repository.revoke_for_discard(VIDEO_ID, USER_ID)
    self.client.table.assert_not_called()

  def test_selects_complete_task_contract(self):
    self.repository.list_pending_deletions()
    self.client.table.assert_called_once_with('video_deletion_outbox')
    self.client.table.return_value.select.assert_called_once_with(
      'video_id,user_id,storage_paths,archive_paths,export_prefixes,delete_metadata')

  def test_finalization_rpc_uses_exact_snapshot_and_requires_boolean_true(self):
    snapshot = task()
    for value in (True, False, None, [], [True], {'completed': True}, 'true'):
      with self.subTest(value=value):
        self.client.rpc.return_value.execute.return_value.data = value
        self.assertIs(self.repository.complete_deletion(snapshot), value is True)
    self.client.rpc.assert_called_with('complete_video_media_deletion', {
      'p_video_id': VIDEO_ID, 'p_user_id': USER_ID,
      'p_storage_paths': snapshot['storage_paths'], 'p_archive_paths': snapshot['archive_paths'],
      'p_export_prefixes': snapshot['export_prefixes'], 'p_delete_metadata': True})
    self.client.table.assert_not_called()


if __name__ == '__main__':
  unittest.main()
