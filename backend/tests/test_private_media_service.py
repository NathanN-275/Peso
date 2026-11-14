from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from types import SimpleNamespace
from threading import Event
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.services import private_media as media
from test_archive_writes import published_archive
from app.services.auth import VerifiedAuthContext

OWNER = '00000000-0000-0000-0000-000000000001'
SESSION = '00000000-0000-0000-0000-000000000002'
VIDEO = '00000000-0000-0000-0000-000000000003'
ATTEMPT = '00000000-0000-0000-0000-000000000005'
ANALYSIS = '00000000-0000-0000-0000-000000000004'
TOKEN = 'A' * 43


def future(seconds=120):
  return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


class Database:
  def __init__(self):
    self.calls = []
    self.rows = {'videos': [{'id': VIDEO, 'user_id': OWNER, 'storage_path': OWNER + '/original.mp4',
      'playback_path': OWNER + '/playback.mp4', 'thumbnail_path': OWNER + '/thumbnail.jpg',
      'is_saved': True, 'save_state': 'saved'}], 'analysis_results': [{'id': ANALYSIS}],
      'saved_lift_export_jobs': [{'id': VIDEO, 'user_id': OWNER, 'status': 'completed',
        'expires_at': future(), 'archive_path': OWNER + '/archive.zip'}]}
    self.rpc_rows = [{'user_id': OWNER, 'session_id': SESSION, 'resource_kind': 'video',
      'resource_id': VIDEO, 'expires_at': future()}]
    self.export_rows = [dict(attempt_id=ATTEMPT,user_id=OWNER,video_id=VIDEO,purpose='analyzed_export',bucket='videos',
      storage_path=f'{OWNER}/exports/{VIDEO}-{ANALYSIS}-pose-{ATTEMPT}-h264-v1.mp4',source_path=OWNER+'/playback.mp4',
      content_type='video/mp4',size_bytes=10,job_id=None,worker_id=None,attempt_count=None,
      analysis_id=ANALYSIS,analysis_model_version='fixture',analysis_snapshot_hash='a'*64,variant='pose',
      state='succeeded',published_at=future(-1),cache_expires_at=future())]
    self.archive_row=published_archive(OWNER,VIDEO,VIDEO,ATTEMPT)
    self.rows["saved_lift_export_jobs"][0]["archive_path"]=self.archive_row["storage_path"]
    self.error = None

  def rpc(self, name, values):
    self.calls.append((name, values))
    if self.error:
      raise self.error
    return SimpleNamespace(execute=lambda: SimpleNamespace(data=self.archive_row if name == "read_private_media_archive" else self.export_rows if name == "read_private_media_export" else self.rpc_rows))

  def table(self, table):
    self.calls.append(('table', table))
    db = self
    class Query:
      def select(self, *args): return self
      def eq(self, *args):
        db.calls.append(('eq', args))
        return self
      def limit(self, *args): return self
      def order(self, *args, **kwargs): return self
      def execute(self): return SimpleNamespace(data=db.rows[table])
    return Query()


class PrivateMediaServiceTest(unittest.TestCase):
  def setUp(self):
    self.db = Database()
    self.storage = Mock()
    self.storage.get_object_info.return_value = {'metadata': {'size': '10'}}
    self.storage.create_signed_url.return_value = 'https://storage.invalid/storage/v1/object/sign/videos/owned?token=synthetic-private-secret'
    self.factory = Mock(return_value=self.storage)
    self.service = media.PrivateMediaService(client=self.db, storage_factory=self.factory)
    self.settings = SimpleNamespace(video_bucket='videos', supabase_url='https://storage.invalid')
    self.patch_settings = patch.object(media, 'get_settings', return_value=self.settings)
    self.patch_settings.start()
    self.addCleanup(self.patch_settings.stop)
    self.context = VerifiedAuthContext(OWNER, SESSION, int(datetime.now(timezone.utc).timestamp()) + 600)

  def authorize(self, asset='playback', kind='video'):
    return self.service.authorize_asset(TOKEN, kind, VIDEO, asset)

  def test_issue_stores_only_sha256_and_verified_context(self):
    grant = self.service.issue(self.context, 'video', VIDEO, ['playback', 'thumbnail'])
    name, args = self.db.calls[0]
    self.assertEqual(name, 'issue_private_media_grant')
    self.assertEqual(len(grant.token), 43)
    self.assertEqual(args['p_token_hash'], hashlib.sha256(grant.token.encode()).hexdigest())
    self.assertEqual(args['p_user_id'], OWNER)
    self.assertEqual(args['p_session_id'], SESSION)
    self.assertNotIn(grant.token, repr(grant) + repr(self.db.calls))
    self.factory.assert_not_called()

  def test_issue_rejects_invalid_assets_before_rpc(self):
    for assets in ([], ['playback', 'playback'], ['archive'], ['unknown'], [None], [['playback']]):
      with self.subTest(assets=assets), self.assertRaises(HTTPException):
        self.service.issue(self.context, 'video', VIDEO, assets)
    self.assertEqual(self.db.calls, [])

  def test_issue_rejects_invalid_expiry_without_rpc(self):
    for expiry in (True, 0, 10**100):
      with self.subTest(expiry=expiry), self.assertRaises(HTTPException) as caught:
        self.service.issue(VerifiedAuthContext(OWNER, SESSION, expiry), 'video', VIDEO, ['playback'])
      self.assertEqual(caught.exception.status_code, 401)
    self.assertEqual(self.db.calls, [])

  def test_issue_rejects_wrong_binding_or_unbounded_expiry(self):
    for updates in ({'resource_id': OWNER}, {'resource_kind': 'archive'}, {'expires_at': future(-1)},
                    {'expires_at': future(301)}, {'expires_at': '2026-01-01'}, {'expires_at': None}):
      self.db.rpc_rows = [{'resource_kind': 'video', 'resource_id': VIDEO, 'expires_at': future(), **updates}]
      with self.subTest(updates=updates), self.assertRaises(HTTPException):
        self.service.issue(self.context, 'video', VIDEO, ['playback'])

  def test_reauthorize_each_request_before_storage(self):
    asset = self.authorize()
    self.assertEqual(asset.size_bytes, 10)
    self.assertEqual(asset.owner_id, OWNER)
    self.assertEqual(asset.content_type, 'video/mp4')
    self.assertIn(('eq', ('user_id', OWNER)), self.db.calls)
    self.storage.get_object_info.assert_called_once_with(OWNER + '/playback.mp4')
    self.storage.create_signed_url.assert_called_once_with(OWNER + '/playback.mp4', expires_in=60)
    self.db.rpc_rows = []
    self.factory.reset_mock()
    with self.assertRaises(HTTPException) as caught:
      self.authorize()
    self.assertEqual(caught.exception.status_code, 403)
    self.factory.assert_not_called()
    self.assertEqual(sum(name == 'authorize_private_media_grant' for name, _ in self.db.calls), 2)

  def test_malformed_credentials_never_call_database_or_storage(self):
    for token in ('', 'A' * 42, 'A' * 42 + 'B', 'A' * 44, 'Bearer synthetic', None):
      with self.subTest(token=token), self.assertRaises(HTTPException) as caught:
        self.service.authorize_asset(token, 'video', VIDEO, 'playback')
      self.assertEqual(caught.exception.status_code, 401)
    self.assertEqual(self.db.calls, [])
    self.factory.assert_not_called()

  def test_bad_grant_binding_expiry_and_session_never_open_storage(self):
    original = dict(self.db.rpc_rows[0])
    for updates in ({'user_id': 'invalid'}, {'session_id': OWNER.upper().replace('1', 'F')},
                    {'resource_id': OWNER}, {'resource_kind': 'archive'}, {'expires_at': future(-1)}):
      self.db.rpc_rows = [{**original, **updates}]
      with self.subTest(updates=updates), self.assertRaises(HTTPException):
        self.authorize()
    self.factory.assert_not_called()

  def test_database_errors_and_malformed_responses_are_sanitized(self):
    for rows in (None, {}, ['synthetic-private-secret'], [None]):
      self.db.rpc_rows = rows
      with self.subTest(rows=rows), self.assertRaises(HTTPException) as caught:
        self.authorize()
      self.assertEqual(caught.exception.status_code, 503)
      self.assertNotIn('synthetic-private-secret', str(caught.exception.detail))
    self.db.error = RuntimeError('synthetic-private-secret')
    with self.assertRaises(HTTPException) as caught:
      self.authorize()
    self.assertEqual(caught.exception.status_code, 503)
    self.factory.assert_not_called()

  def test_tombstoned_pruned_and_wrong_owner_reject_before_storage(self):
    original = dict(self.db.rows['videos'][0])
    for updates in ({'discarded_at': future()}, {'storage_state': 'pruned'}, {'user_id': SESSION}, {'id': SESSION},
                    {'playback_path': SESSION + '/foreign.mp4'}):
      self.db.rows['videos'] = [{**original, **updates}]
      with self.subTest(updates=updates), self.assertRaises(HTTPException):
        self.authorize()
    self.factory.assert_not_called()

  def test_assigned_derivative_failure_never_falls_back(self):
    self.storage.get_object_info.side_effect = RuntimeError('synthetic-private-secret')
    with self.assertRaises(HTTPException) as caught:
      self.authorize()
    self.assertEqual(caught.exception.status_code, 503)
    self.storage.get_object_info.assert_called_once_with(OWNER + '/playback.mp4')
    self.storage.create_signed_url.assert_not_called()

  def test_original_is_used_only_when_no_derivative_is_assigned(self):
    self.db.rows['videos'][0]['playback_path'] = None
    self.authorize()
    self.storage.get_object_info.assert_called_once_with(OWNER + '/original.mp4')

  def test_unknown_or_malformed_object_size_never_signs(self):
    for info in ({}, {'size': True}, {'size': -1}, {'size': 1.2}, {'size': '10junk'}, {'size': 2**63}, None):
      self.storage.get_object_info.return_value = info
      with self.subTest(info=info), self.assertRaises(HTTPException):
        self.authorize()
    self.storage.create_signed_url.assert_not_called()

  def test_zero_size_is_known_metadata(self):
    self.storage.get_object_info.return_value = {'size': 0}
    self.assertEqual(self.authorize().size_bytes, 0)

  def test_signed_url_cannot_redirect_credentials_to_another_host(self):
    for url in ('http://storage.invalid/storage/v1/object/sign/videos/x', 'https://evil.invalid/storage/v1/object/sign/videos/x',
                'https://storage.invalid/other/x', 'https://user:pass@storage.invalid/storage/v1/object/sign/videos/x', 'https://['):
      self.storage.create_signed_url.return_value = url
      with self.subTest(url=url), self.assertRaises(HTTPException):
        self.authorize()

  def test_thumbnail_uses_owned_path_and_fixed_image_type(self):
    asset = self.authorize('thumbnail')
    self.assertEqual(asset.content_type, 'image/jpeg')
    self.storage.get_object_info.assert_called_once_with(OWNER + '/thumbnail.jpg')

  def test_exports_require_saved_state(self):
    self.db.rows['videos'][0]['save_state'] = 'pending'
    for asset in ('export:clean', 'export:pose', 'export:barbell', 'export:pose-barbell'):
      with self.subTest(asset=asset), self.assertRaises(HTTPException):
        self.authorize(asset)
    self.factory.assert_not_called()

  def test_clean_export_preserves_supported_original_video_formats(self):
    row = self.db.rows['videos'][0]
    row['playback_path'] = None
    row['storage_path'] = None
    for suffix, content_type in (('.mp4','video/mp4'),('.mov','video/quicktime'),
                                 ('.m4v','video/x-m4v'),('.webm','video/webm')):
      path = OWNER + '/original' + suffix
      row['original_storage_path'] = path
      with self.subTest(suffix=suffix):
        asset = self.authorize('export:clean')
        self.assertEqual(asset.content_type, content_type)
        self.assertEqual(asset.download_name, 'Saved-Lift-' + VIDEO + suffix)
        self.storage.get_object_info.assert_called_with(path)

  def test_overlay_export_uses_current_analysis_without_generating_in_get(self):
    asset = self.authorize('export:pose')
    self.assertEqual(asset.download_name, 'Saved-Lift-' + VIDEO + '.mp4')
    self.storage.get_object_info.assert_called_once_with(f'{OWNER}/exports/{VIDEO}-{ANALYSIS}-pose-{ATTEMPT}-h264-v1.mp4')

  def test_malformed_export_publication_does_not_open_storage(self):
    self.db.export_rows = [None]
    with self.assertRaises(HTTPException):
      self.authorize('export:pose')
    self.factory.assert_not_called()

  def test_archive_uses_separate_bucket_and_checks_current_expiry(self):
    self.db.rpc_rows[0]['resource_kind'] = 'archive'
    self.storage.create_signed_url.return_value = 'https://storage.invalid/storage/v1/object/sign/saved-lift-exports/x?token=synthetic'
    asset = self.authorize('archive', 'archive')
    self.assertEqual(asset.content_type, 'application/zip')
    self.factory.assert_called_once_with(bucket='saved-lift-exports')
    self.factory.reset_mock()
    self.db.rows['saved_lift_export_jobs'][0]['expires_at'] = future(-1)
    with self.assertRaises(HTTPException):
      self.authorize('archive', 'archive')
    self.factory.assert_not_called()

  def test_archive_missing_or_wrong_published_generation_never_opens_storage(self):
    self.db.rpc_rows[0]['resource_kind']='archive'
    for value in (None,{**self.db.archive_row,'storage_path':OWNER+'/legacy.zip'},
                  {**self.db.archive_row,'size_bytes':True}):
      self.db.archive_row=value
      with self.subTest(value=value),self.assertRaises(HTTPException):self.authorize('archive','archive')
    self.factory.assert_not_called()

  def test_archive_size_must_match_the_published_attempt_before_signing(self):
    self.db.rpc_rows[0]['resource_kind']='archive'
    self.storage.get_object_info.return_value={'size':11}
    with self.assertRaises(HTTPException):self.authorize('archive','archive')
    self.storage.create_signed_url.assert_not_called()

  def test_cancelled_authorization_never_calls_database(self):
    with self.assertRaises(HTTPException):
      self.service.authorize_asset(TOKEN, 'video', VIDEO, 'playback', is_cancelled=lambda: True)
    self.assertEqual(self.db.calls, [])
    self.factory.assert_not_called()

  def test_global_logout_uses_verified_session_as_stable_operation_key(self):
    self.db.rpc_rows = [{'completed_at': datetime.now(timezone.utc).isoformat(), 'replayed': False}]
    result = self.service.revoke_global_session(self.context)
    self.assertEqual(result['scope'], 'global')
    self.assertFalse(result['replayed'])
    name, values = self.db.calls[0]
    self.assertEqual(name, 'revoke_private_media_session_once')
    self.assertEqual(values, {'p_user_id': OWNER, 'p_session_id': SESSION, 'p_scope': 'global', 'p_request_id': SESSION})
    self.factory.assert_not_called()

  def test_global_logout_refresh_keeps_operation_key_and_returns_committed_replay(self):
    completed = datetime.now(timezone.utc).isoformat()
    self.db.rpc_rows = [{'completed_at': completed, 'replayed': False}]
    first = self.service.revoke_global_session(self.context)
    self.db.rpc_rows[0]['replayed'] = True
    second = self.service.revoke_global_session(VerifiedAuthContext(OWNER, SESSION, self.context.expires_at + 600))
    self.assertEqual(self.db.calls[0][1], self.db.calls[1][1])
    self.assertEqual(first['completed_at'], second['completed_at'])
    self.assertTrue(second['replayed'])
    self.factory.assert_not_called()

  def test_global_logout_rejects_bad_receipt_without_storage(self):
    for rows in ([], [{'completed_at': None, 'replayed': False}], [{'completed_at': future(), 'replayed': 1}],
                 [{'completed_at': future()}], [{'completed_at': 'invalid', 'replayed': True}]):
      self.db.rpc_rows = rows
      with self.subTest(rows=rows), self.assertRaises(HTTPException):
        self.service.revoke_global_session(self.context)
    self.factory.assert_not_called()

  def test_global_logout_denial_is_safe_and_has_no_receipt(self):
    class Denied(Exception):
      code = '42501'
    self.db.error = Denied('synthetic-private-secret')
    with self.assertRaises(HTTPException) as caught:
      self.service.revoke_global_session(self.context)
    self.assertEqual(caught.exception.status_code, 403)
    self.assertNotIn('synthetic-private-secret', str(caught.exception.detail))
    self.factory.assert_not_called()

  def test_cancellation_during_rpc_stops_before_metadata_or_storage(self):
    cancelled = Event()
    original = self.service._rpc
    def rpc(*args):
      result = original(*args)
      cancelled.set()
      return result
    with patch.object(self.service, '_rpc', side_effect=rpc), self.assertRaises(HTTPException):
      self.service.authorize_asset(TOKEN, 'video', VIDEO, 'playback', is_cancelled=cancelled.is_set)
    self.assertEqual(len(self.db.calls), 1)
    self.factory.assert_not_called()

  def test_cancellation_during_metadata_stops_before_signing(self):
    cancelled = Event()
    def metadata(path):
      cancelled.set()
      return {'size': 10}
    self.storage.get_object_info.side_effect = metadata
    with self.assertRaises(HTTPException):
      self.service.authorize_asset(TOKEN, 'video', VIDEO, 'playback', is_cancelled=cancelled.is_set)
    self.storage.create_signed_url.assert_not_called()


  def test_replacement_uses_distinct_stable_local_operation_and_binds_receipt(self):
    completed = datetime.now(timezone.utc).isoformat()
    self.db.rpc_rows = [{'completed_at': completed, 'replayed': False}]
    first = self.service.revoke_local_session(self.context)
    self.db.rpc_rows[0]['replayed'] = True
    second = self.service.revoke_local_session(VerifiedAuthContext(OWNER, SESSION, self.context.expires_at + 600))
    self.assertEqual(self.db.calls[0], self.db.calls[1])
    self.assertEqual(self.db.calls[0], ('revoke_private_media_session_once',
      {'p_user_id': OWNER, 'p_session_id': SESSION, 'p_scope': 'local', 'p_request_id': '5946535e-9e75-577b-9bc8-20c5680fdc36'}))
    self.assertNotEqual(self.db.calls[0][1]['p_request_id'], SESSION)
    self.assertEqual(first, {'scope': 'local', 'owner_id': OWNER, 'session_id': SESSION, 'completed_at': completed, 'replayed': False})
    self.assertEqual(second, {**first, 'replayed': True})
    self.service.revoke_local_session(VerifiedAuthContext(OWNER, VIDEO, self.context.expires_at))
    self.assertNotEqual(self.db.calls[0][1]['p_request_id'], self.db.calls[2][1]['p_request_id'])
    self.factory.assert_not_called()

  def test_replacement_rejects_unbound_or_malformed_sql_receipt(self):
    for rows in ([], [{'completed_at': None, 'replayed': False}], [{'completed_at': future(), 'replayed': 1}],
                 [{'completed_at': future(), 'replayed': False, 'owner_id': VIDEO}], [{'completed_at': 'infinity', 'replayed': False}]):
      self.db.rpc_rows = rows
      with self.subTest(rows=rows), self.assertRaises(HTTPException):
        self.service.revoke_local_session(self.context)
    self.factory.assert_not_called()

  def test_cookie_inventory_uses_verified_owner_session_and_exact_path_keyset(self):
    self.db.rpc_rows = [{'resource_kind': 'archive', 'resource_id': VIDEO}, {'resource_kind': 'video', 'resource_id': VIDEO}]
    paths, cursor = self.service.session_cookie_paths(self.context, None)
    self.assertEqual(paths, [f'/private-media/archive/{VIDEO}/', f'/private-media/video/{VIDEO}/'])
    self.assertIsNone(cursor)
    self.assertEqual(self.db.calls[-1], ('private_media_session_cookie_paths',
      {'p_user_id': OWNER, 'p_session_id': SESSION, 'p_after_kind': None, 'p_after_id': None}))
    self.db.rpc_rows = []
    self.service.session_cookie_paths(self.context, 'archive:' + VIDEO, all_sessions=True)
    self.assertEqual(self.db.calls[-1][1], {'p_user_id': OWNER, 'p_session_id': None, 'p_after_kind': 'archive', 'p_after_id': VIDEO})
    self.factory.assert_not_called()

  def test_cookie_inventory_limits_page_to_32_with_lookahead_only_for_continuation(self):
    rows = [{'resource_kind': 'video', 'resource_id': f'00000000-0000-0000-0000-{number:012d}'} for number in range(1, 34)]
    self.db.rpc_rows = rows
    paths, cursor = self.service.session_cookie_paths(self.context, None)
    self.assertEqual(len(paths), 32)
    self.assertEqual(cursor, 'video:' + rows[31]['resource_id'])
    self.assertNotIn(rows[32]['resource_id'], ''.join(paths))
    self.db.rpc_rows = rows[:32]
    self.assertIsNone(self.service.session_cookie_paths(self.context, None)[1])

  def test_cookie_inventory_rejects_bad_cursor_and_untrusted_database_paths(self):
    for cursor in ('bad', 'other:' + VIDEO, 'video:00000000-0000-0000-0000-000000000000', 'video:' + VIDEO + ':extra'):
      with self.subTest(cursor=cursor), self.assertRaises(HTTPException):
        self.service.session_cookie_paths(self.context, cursor)
    self.assertEqual(self.db.calls, [])
    good = {'resource_kind': 'video', 'resource_id': VIDEO}
    for rows in ([good, good], [good] * 34, [{'resource_kind': 'bad', 'resource_id': VIDEO}],
                 [{'resource_kind': 'video', 'resource_id': '../../path'}], [{'resource_kind': ['video'], 'resource_id': VIDEO}],
                 [{**good, 'path': '/arbitrary/'}], [{'resource_kind': 'video', 'resource_id': '00000000-0000-0000-0000-000000000000'}]):
      self.db.rpc_rows = rows
      with self.subTest(rows=rows), self.assertRaises(HTTPException) as error:
        self.service.session_cookie_paths(self.context, None)
      self.assertEqual(error.exception.status_code, 503)
    self.db.rpc_rows = [good]
    with self.assertRaises(HTTPException):
      self.service.session_cookie_paths(self.context, 'video:' + VIDEO)



  def test_incoming_acceptance_requires_literal_live_decision_for_verified_binding(self):
    self.db.rpc_rows = True
    self.assertEqual(self.service.accept_session(self.context), {'owner_id': OWNER, 'session_id': SESSION, 'accepted': True})
    self.assertEqual(self.db.calls, [('private_media_app_session_is_live', {'p_user_id': OWNER, 'p_session_id': SESSION})])
    self.factory.assert_not_called()

  def test_incoming_acceptance_denies_false_missing_or_malformed_decisions(self):
    for result in (False, None, 1, 0, 'true', [], [True], {}, {'accepted': True}):
      with self.subTest(result=result):
        self.db.rpc_rows = result
        with self.assertRaises(HTTPException) as error:
          self.service.accept_session(self.context)
        self.assertEqual(error.exception.status_code, 403)
    self.assertTrue(all(name == 'private_media_app_session_is_live' for name, _ in self.db.calls))
    self.factory.assert_not_called()

  def test_incoming_acceptance_sanitizes_database_failure_and_does_not_acknowledge(self):
    self.db.error = RuntimeError('synthetic-private-database-error')
    with self.assertRaises(HTTPException) as error:
      self.service.accept_session(self.context)
    self.assertEqual(error.exception.status_code, 503)
    self.assertNotIn('synthetic-private', str(error.exception.detail))
    self.factory.assert_not_called()


if __name__ == '__main__':
  unittest.main()
