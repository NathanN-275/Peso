from __future__ import annotations

import base64
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.jobs.upload_reservation_cleanup import cleanup_upload_reservations
from app.routes.upload_reservations import router
from app.services.auth import get_current_user_id
from app.services.config import Settings
from app.services.upload_reservations import UploadReservationRepository
from app.services.storage_service import StorageService
from app.services import supabase_client


USER = '33333333-3333-3333-3333-333333333333'
RESERVATION = '11111111-1111-1111-1111-111111111111'
PATH = f'{USER}/source/{RESERVATION}.mp4'
SETTINGS = Settings(backend_env='test', supabase_url='https://example.supabase.co',
                    supabase_service_role_key='synthetic-test', upload_reservations_enabled=True,
                    upload_storage_provider='supabase')


class SourceWriteRepositoryTest(unittest.TestCase):
  def setUp(self):
    self.client = MagicMock()
    self.repository = object.__new__(UploadReservationRepository)
    self.repository.client = self.client
    self.fields = dict(attempt_id=str(uuid4()), user_id=USER, reservation_id=RESERVATION,
                       bucket='videos', storage_path=PATH, content_type='video/mp4', size_bytes=100)

  def test_fresh_exact_admission_is_required_before_dispatch(self):
    self.client.rpc.return_value.execute.return_value.data = [{**self.fields, 'state': 'dispatching'}]
    self.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{**self.fields, 'state': 'dispatching'}]
    self.repository.admit_source_write(**self.fields)
    self.client.rpc.assert_called_once_with('admit_private_media_source_write',
                                           {'p_' + key: value for key, value in self.fields.items()})

  def test_returned_but_uncommitted_or_uncertain_admission_does_not_authorize_dispatch(self):
    row = {**self.fields, 'state': 'dispatching'}
    self.client.rpc.return_value.execute.return_value.data = [row]
    read = self.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute
    for data in (None, [], [row, row], [{**row, 'state': 'succeeded'}]):
      with self.subTest(data=data), self.assertRaises(RuntimeError):
        read.return_value.data = data
        self.repository.admit_source_write(**self.fields)
    self.client.reset_mock()
    read.side_effect = TimeoutError('synthetic lost persisted read')
    with self.assertRaises(TimeoutError): self.repository.admit_source_write(**self.fields)
    self.client.rpc.assert_called_once()

  def test_admission_rejects_missing_duplicate_malformed_or_replayed_receipt(self):
    good = {**self.fields, 'state': 'dispatching'}
    cases = [None, {}, [], [good, good], [True], [{**good, 'state': 'succeeded'}]]
    for key, value in self.fields.items():
      cases.extend([[{**good, key: None}], [{**good, key: str(value) + 'changed'}]])
    cases.append([{**good, 'size_bytes': True}])
    for data in cases:
      with self.subTest(data=data):
        self.client.rpc.return_value.execute.return_value.data = data
        with self.assertRaises(RuntimeError):
          self.repository.admit_source_write(**self.fields)

  def test_uncertain_admission_is_not_retried(self):
    self.client.rpc.return_value.execute.side_effect = TimeoutError('synthetic lost response')
    with self.assertRaises(TimeoutError): self.repository.admit_source_write(**self.fields)
    self.client.rpc.assert_called_once()

  def test_persisted_receipt_cannot_replace_one_byte_with_boolean_true(self):
    self.fields['size_bytes'] = 1
    row = {**self.fields, 'state': 'dispatching'}
    self.client.rpc.return_value.execute.return_value.data = [row]
    self.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [{**row, 'size_bytes': True}]
    with self.assertRaises(RuntimeError): self.repository.admit_source_write(**self.fields)

  def test_success_observation_requires_exact_true_and_never_retries(self):
    for data in (None, False, 1, 'true', [True], {}):
      with self.subTest(data=data), self.assertRaises(RuntimeError):
        self.client.rpc.return_value.execute.return_value.data = data
        self.repository.observe_source_write_success(**self.fields)
    self.client.reset_mock()
    self.client.rpc.return_value.execute.return_value.data = True
    self.repository.observe_source_write_success(**self.fields)
    self.client.rpc.assert_called_once_with('observe_private_media_source_write_success',
                                           {'p_' + key: value for key, value in self.fields.items()})

  def cleanup(self, pending):
    self.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = pending
    result = self.repository.mark_blob_deleted(PATH, confirmed_after_expiry=True)
    return result, self.client.table.return_value.update.call_args.args[0]

  def test_pending_attempt_records_delete_observation_without_releasing_capacity(self):
    result, fields = self.cleanup([{'attempt_id': self.fields['attempt_id']}])
    self.assertFalse(result)
    self.assertIn('blob_deleted_at', fields)
    self.assertNotIn('cleanup_confirmed_at', fields)

  def test_legacy_no_attempt_cleanup_retains_existing_confirmation(self):
    result, fields = self.cleanup([])
    self.assertTrue(result)
    self.assertIn('cleanup_confirmed_at', fields)

  def test_unknown_attempt_query_does_not_mutate_cleanup_or_release_capacity(self):
    for data in (None, {}, False):
      with self.subTest(data=data):
        self.client.reset_mock()
        with self.assertRaises(RuntimeError): self.cleanup(data)
        self.client.table.return_value.update.assert_not_called()

  def test_ordinary_delete_observation_does_not_claim_confirmation(self):
    self.assertFalse(self.repository.mark_blob_deleted(PATH))
    self.client.table.return_value.select.assert_not_called()
    self.assertNotIn('cleanup_confirmed_at', self.client.table.return_value.update.call_args.args[0])


class SourceWriteRouteTest(unittest.TestCase):
  def setUp(self):
    self.events = []
    self.repository = MagicMock()
    self.repository.require_owned.return_value = {
      'id': RESERVATION, 'user_id': USER, 'blob_path': PATH, 'state': 'issued',
      'expires_at': (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
      'requested_bytes': 100, 'content_type': 'video/mp4',
    }
    self.storage = MagicMock()
    self.repository.admit_source_write.side_effect = lambda *_a, **_kw: self.events.append('admit')
    self.storage.create_file.side_effect = lambda *_a, **_kw: self.events.append('upload')
    self.repository.observe_source_write_success.side_effect = lambda *_a, **_kw: self.events.append('observe')
    self.app = FastAPI()
    self.app.include_router(router)
    self.app.dependency_overrides[get_current_user_id] = lambda: USER

  def put(self, body=b'synthetic', **settings):
    with patch('app.routes.upload_reservations.get_settings', return_value=replace(SETTINGS, **settings)), patch(
      'app.routes.upload_reservations.UploadReservationRepository', return_value=self.repository,
    ), patch('app.routes.upload_reservations.StorageService', return_value=self.storage):
      return TestClient(self.app).put(f'/upload-reservations/{RESERVATION}/content', content=body,
                                     headers={'Content-Type': 'video/mp4', 'If-None-Match': '*'})

  def test_validated_body_admitted_before_single_create_then_exact_success_observation(self):
    self.assertEqual(self.put().status_code, 204)
    self.assertEqual(self.events, ['admit', 'upload', 'observe'])
    args, fields = self.repository.admit_source_write.call_args
    self.assertEqual(args[1:], (USER, RESERVATION))
    self.assertEqual(fields, dict(bucket='videos', storage_path=PATH, content_type='video/mp4', size_bytes=9))
    self.assertEqual(self.repository.observe_source_write_success.call_args, self.repository.admit_source_write.call_args)
    self.assertFalse(self.storage.create_file.call_args.args[1].exists())

  def test_configured_bucket_is_bound_to_admission(self):
    self.assertEqual(self.put(video_bucket='private-videos').status_code, 204)
    self.assertEqual(self.repository.admit_source_write.call_args.kwargs['bucket'], 'private-videos')

  def test_lost_denied_or_mismatched_admission_prevents_external_dispatch(self):
    for error in (TimeoutError('lost admission'), RuntimeError('duplicate dispatch'), RuntimeError('mismatch')):
      with self.subTest(error=error):
        self.repository.admit_source_write.side_effect = error
        self.assertEqual(self.put().status_code, 503)
        self.storage.create_file.assert_not_called()
        self.repository.observe_source_write_success.assert_not_called()

  def test_upload_timeout_preserves_pending_attempt_and_never_records_success_or_replays(self):
    self.storage.create_file.side_effect = TimeoutError('unknown write outcome')
    self.assertEqual(self.put().status_code, 503)
    self.repository.admit_source_write.assert_called_once()
    self.storage.create_file.assert_called_once()
    self.repository.observe_source_write_success.assert_not_called()
    self.repository.reject.assert_not_called()

  def test_lost_success_receipt_does_not_retry_upload_or_revoke_the_attempt(self):
    self.repository.observe_source_write_success.side_effect = TimeoutError('lost observation')
    self.assertEqual(self.put().status_code, 503)
    self.storage.create_file.assert_called_once()
    self.repository.observe_source_write_success.assert_called_once()
    self.repository.reject.assert_not_called()

  def test_body_failure_never_creates_an_attempt(self):
    for body, code in ((b'', 400), (b'x' * 101, 413)):
      with self.subTest(code=code):
        self.assertEqual(self.put(body).status_code, code)
        self.repository.admit_source_write.assert_not_called()
        self.storage.create_file.assert_not_called()

  def test_expired_pre_body_check_never_creates_an_attempt(self):
    self.repository.require_owned.return_value['expires_at'] = '2000-01-01T00:00:00+00:00'
    self.assertEqual(self.put().status_code, 410)
    self.repository.admit_source_write.assert_not_called()
    self.storage.create_file.assert_not_called()


class SourceWriteCleanupJobTest(unittest.TestCase):
  def test_pending_source_keeps_cleanup_count_pending_and_other_reservations_progress(self):
    repository, storage = MagicMock(), MagicMock()
    repository.expire_due.return_value = [{'blob_path': PATH}, {'blob_path': f'{USER}/source/other.mp4'}]
    repository.mark_blob_deleted.side_effect = [False, True]
    with patch('app.jobs.upload_reservation_cleanup.get_settings', return_value=SETTINGS), patch(
      'app.jobs.upload_reservation_cleanup.UploadReservationRepository', return_value=repository,
    ), patch('app.jobs.upload_reservation_cleanup.StorageService', return_value=storage):
      self.assertEqual(cleanup_upload_reservations(), 1)
    self.assertEqual(storage.delete.call_count, 2)
    repository.purge_cleaned_tombstones.assert_called_once()


class SourceWriteTransportTest(unittest.TestCase):
  def test_source_file_closes_after_upload_timeout(self):
    storage = object.__new__(StorageService)
    storage.client = MagicMock(); storage.bucket = 'videos'
    storage.client.storage.from_.return_value.upload.side_effect = TimeoutError('unknown outcome')
    with TemporaryDirectory() as directory:
      path = Path(directory)/'synthetic.mp4';path.write_bytes(b'synthetic')
      with self.assertRaises(TimeoutError): storage.create_file(PATH, path, 'video/mp4')
    handle = storage.client.storage.from_.return_value.upload.call_args.args[1]
    self.assertTrue(handle.closed)

  def test_real_storage_sdk_does_not_follow_redirect_or_resend_upload_body(self):
    requests = []
    class Handler(BaseHTTPRequestHandler):
      def do_POST(self):
        requests.append((self.path, self.rfile.read(int(self.headers['Content-Length']))))
        if len(requests)==1:
          self.send_response(307)
          self.send_header('Location', '/storage/v1/object/videos/redirected.mp4')
          payload = b'{"message":"synthetic redirect","error":"redirect","statusCode":307}'
        else:
          self.send_response(200)
          payload = b'{"Key":"videos/redirected.mp4"}'
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers();self.wfile.write(payload)
      def log_message(self, *_args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True);thread.start()
    supabase_client.get_supabase_admin_client.cache_clear()
    client = None
    try:
      synthetic_key = '.'.join(base64.urlsafe_b64encode(part).decode().rstrip('=') for part in (
        b'{"alg":"HS256"}', b'{"role":"service_role"}', b'synthetic-local-test-only',
      ))
      configured = replace(SETTINGS, supabase_url=f'http://127.0.0.1:{server.server_port}',
                           supabase_service_role_key=synthetic_key)
      with patch.object(supabase_client, 'get_settings', return_value=configured):
        client = supabase_client.get_supabase_admin_client()
      self.assertFalse(client.storage.session.follow_redirects)
      storage = object.__new__(StorageService);storage.client=client;storage.bucket='videos'
      with TemporaryDirectory() as directory:
        path=Path(directory)/'synthetic.mp4';path.write_bytes(b'synthetic-source-body')
        with self.assertRaises(Exception) as error: storage.create_file(PATH,path,'video/mp4')
        self.assertIn('synthetic redirect',str(error.exception))
      self.assertEqual(len(requests),1)
      self.assertIn(b'synthetic-source-body',requests[0][1])
    finally:
      if client is not None: client.storage.session.close()
      supabase_client.get_supabase_admin_client.cache_clear()
      server.shutdown();server.server_close();thread.join(timeout=2)
