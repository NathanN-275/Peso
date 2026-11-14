from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import textwrap
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from app.services.config import get_settings
from app.services import legacy_storage


ENVIRONMENT = {
  'BACKEND_ENV': 'test',
  'SUPABASE_URL': 'https://example.supabase.co',
  'SUPABASE_SERVICE_ROLE_KEY': 'synthetic-test',
  'CLEANUP_JOB_TOKEN': 'synthetic-cleanup',
  'PESO_RUNTIME_PROFILE': 'web-mvp',
}


class WebMvpConfigurationTest(unittest.TestCase):
  def tearDown(self):
    get_settings.cache_clear()

  def settings(self, **changes):
    with patch.dict(os.environ, {**ENVIRONMENT, **changes}, clear=True):
      get_settings.cache_clear()
      return get_settings()

  def test_mvp_defaults_to_supabase_without_azure_configuration(self):
    settings = self.settings()
    self.assertEqual(settings.runtime_profile, 'web-mvp')
    self.assertEqual(settings.upload_storage_provider, 'supabase')
    self.assertEqual(settings.azure_blob_account_url, '')
    self.assertIsNone(settings.azure_managed_identity_client_id)

  def test_mvp_allows_explicit_supabase_and_ignores_empty_azure_variables(self):
    settings = self.settings(UPLOAD_STORAGE_PROVIDER='supabase', AZURE_CLIENT_ID='', AZURE_BLOB_ACCOUNT_URL=' ')
    self.assertEqual(settings.upload_storage_provider, 'supabase')

  def test_mvp_rejects_other_upload_providers_even_when_uploads_are_disabled(self):
    for provider in ('azure', 'other', 'AZURE'):
      with self.subTest(provider=provider), self.assertRaisesRegex(RuntimeError, 'requires Supabase'):
        self.settings(UPLOAD_STORAGE_PROVIDER=provider, UPLOAD_RESERVATIONS_ENABLED='false')

  def test_mvp_rejects_active_azure_configuration_without_disclosing_its_values(self):
    for name in ('AZURE_BLOB_ACCOUNT_URL', 'AZURE_BLOB_SOURCE_CONTAINER', 'AZURE_CLIENT_ID',
                 'AZURE_MANAGED_IDENTITY_CLIENT_ID', 'AZURE_TENANT_ID', 'AZURE_CLIENT_SECRET', 'AZURE_UNRECOGNIZED'):
      with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'AZURE_.*unavailable') as error:
        self.settings(**{name: 'synthetic-sensitive-value'})
      self.assertNotIn('synthetic-sensitive-value', str(error.exception))

  def test_unknown_runtime_profile_fails_instead_of_selecting_legacy_defaults(self):
    for profile in ('web_mvp', 'production', 'web-mvp-extra'):
      with self.subTest(profile=profile), self.assertRaisesRegex(RuntimeError, 'PESO_RUNTIME_PROFILE'):
        self.settings(PESO_RUNTIME_PROFILE=profile)

  def test_legacy_default_and_explicit_azure_configuration_remain_available_separately(self):
    for profile in ('', 'legacy'):
      settings = self.settings(PESO_RUNTIME_PROFILE=profile, AZURE_BLOB_ACCOUNT_URL='https://pesofixture.blob.core.windows.net')
      self.assertEqual(settings.runtime_profile, 'legacy')
      self.assertEqual(settings.upload_storage_provider, 'azure')
      self.assertEqual(settings.azure_blob_account_url, 'https://pesofixture.blob.core.windows.net')


class OptionalLegacyStorageTest(unittest.TestCase):
  def test_mvp_denies_before_the_adapter_can_be_imported(self):
    with patch.object(legacy_storage, 'get_settings', return_value=SimpleNamespace(runtime_profile='web-mvp')):
      with self.assertRaisesRegex(RuntimeError, 'web-mvp'):
        legacy_storage.get_azure_blob_storage()

  def test_missing_legacy_adapter_has_a_clear_runtime_error(self):
    with patch.object(legacy_storage, 'get_settings', return_value=SimpleNamespace(runtime_profile='legacy')), patch.dict(
      sys.modules, {'app.services.azure_blob_storage': None},
    ):
      with self.assertRaisesRegex(RuntimeError, 'unavailable in this runtime image'):
        legacy_storage.get_azure_blob_storage()

  def test_legacy_profile_uses_the_separate_adapter(self):
    adapter = ModuleType('app.services.azure_blob_storage')
    adapter.get_azure_blob_storage = MagicMock(return_value=object())
    with patch.object(legacy_storage, 'get_settings', return_value=SimpleNamespace(runtime_profile='legacy')), patch.dict(
      sys.modules, {'app.services.azure_blob_storage': adapter},
    ):
      self.assertIs(legacy_storage.get_azure_blob_storage(), adapter.get_azure_blob_storage.return_value)
    adapter.get_azure_blob_storage.assert_called_once()


class WebMvpAbsentAzureRuntimeTest(unittest.TestCase):
  def test_api_worker_storage_upload_and_cleanup_work_without_importing_the_azure_adapter_or_sdks(self):
    # A fresh interpreter avoids imported test doubles or a cached legacy adapter.
    script = textwrap.dedent('''
      import importlib.abc
      import socket
      import sys
      from unittest.mock import MagicMock, patch
      attempts = []
      class RejectAzure(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
          if fullname == 'app.services.azure_blob_storage' or fullname == 'azure' or fullname.startswith('azure.'):
            attempts.append(fullname)
            raise AssertionError('The MVP tried to import Azure: ' + fullname)
      sys.meta_path.insert(0, RejectAzure())
      def no_network(*args, **kwargs):
        raise AssertionError('The offline MVP test attempted networking.')
      with patch.object(socket.socket, 'connect', no_network), patch.object(socket, 'create_connection', no_network):
        import app.main
        import app.jobs.analysis_worker
        import app.jobs.upload_reservation_cleanup as cleanup
        from app.routes.upload_reservations import CreateUploadReservationRequest, create_upload_reservation, _get_upload_storage
        from app.services.config import get_settings
        from app.services.legacy_storage import get_azure_blob_storage
        from app.services.storage_service import StorageService
        settings = get_settings()
        assert settings.runtime_profile == 'web-mvp' and settings.upload_storage_provider == 'supabase'
        client = MagicMock()
        bucket = client.storage.from_.return_value
        bucket.info.return_value = {'size': 12, 'contentType': 'video/mp4'}
        bucket.create_signed_url.return_value = {'signedURL': 'https://synthetic.invalid/private-video'}
        bucket.list.return_value = []
        path = '33333333-3333-3333-3333-333333333333/source/11111111-1111-1111-1111-111111111111.mp4'
        with patch('app.services.storage_service.get_supabase_admin_client', return_value=client):
          storage = _get_upload_storage(settings)
          assert isinstance(storage, StorageService)
          assert storage.get_object_info(path)['size'] == 12
          assert storage.create_signed_url(path) == 'https://synthetic.invalid/private-video'
          storage.delete_storage_path(path)
          bucket.remove.assert_called_once_with([path])
          assert storage.list_storage_objects_recursive('owner') == []
          reservation_repository = MagicMock()
          reservation_repository.reserve.return_value = {}
          with patch('app.routes.upload_reservations.UploadReservationRepository', return_value=reservation_repository):
            request = CreateUploadReservationRequest(file_name='synthetic.mp4', content_type='video/mp4', size_bytes=12,
                                                     exercise_type='squat', view_type='side')
            contract = create_upload_reservation(request, '33333333-3333-3333-3333-333333333333')
          assert contract.upload_authentication == 'bearer'
          assert contract.upload_url == f'/upload-reservations/{contract.reservation_id}/content'
          pending = MagicMock()
          pending.expire_due.return_value = [{'blob_path': path}]
          pending.mark_blob_deleted.return_value = False
          bucket.remove.reset_mock()
          with patch('app.jobs.upload_reservation_cleanup.UploadReservationRepository', return_value=pending):
            assert cleanup.cleanup_upload_reservations() == 0
          bucket.remove.assert_called_once_with([path])
          pending.mark_blob_deleted.assert_called_once_with(path, confirmed_after_expiry=True)
        try:
          get_azure_blob_storage()
        except RuntimeError as error:
          assert 'web-mvp' in str(error)
        else:
          raise AssertionError('MVP permitted Azure adapter use.')
      assert attempts == [], attempts
      assert not any(name == 'azure' or name.startswith('azure.') or name == 'app.services.azure_blob_storage' for name in sys.modules)
      print('MVP API, worker, Supabase storage/upload and pending cleanup passed with Azure imports denied.')
    ''')
    environment = {**ENVIRONMENT, 'UPLOAD_RESERVATIONS_ENABLED': 'true', 'PATH': os.defpath, 'PYTHONPATH': str(Path(__file__).resolve().parents[1]),
                   'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1'}
    result = subprocess.run([sys.executable, '-c', script], env=environment, capture_output=True, text=True, timeout=45)
    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
    self.assertIn('pending cleanup passed with Azure imports denied', result.stdout)
