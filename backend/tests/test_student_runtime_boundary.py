import os
import unittest
from unittest.mock import patch
from app.services.config import get_settings


class StudentRuntimeBoundaryTest(unittest.TestCase):
  def tearDown(self):
    get_settings.cache_clear()

  def test_student_rejects_production_or_missing_database_before_client_creation(self):
    for url in ['', 'https://jfgiydtrskpqxyorvvbc.supabase.co', 'https://iseqgaewjpjcxrndibep.supabase.co.evil.test']:
      with patch.dict(os.environ, {'BACKEND_ENV': 'development', 'PESO_DEPLOYMENT_ENVIRONMENT': 'student', 'SUPABASE_URL': url}, clear=True):
        get_settings.cache_clear()
        with self.assertRaisesRegex(RuntimeError, 'isolated peso-staging'):
          get_settings()

  def test_student_accepts_the_permanent_project(self):
    with patch.dict(os.environ, {'BACKEND_ENV': 'development', 'PESO_DEPLOYMENT_ENVIRONMENT': 'student',
      'SUPABASE_URL': 'https://iseqgaewjpjcxrndibep.supabase.co', 'SUPABASE_SERVICE_ROLE_KEY': 'test',
      'CLEANUP_JOB_TOKEN': 'test'}, clear=True):
      get_settings.cache_clear()
      self.assertEqual(get_settings().supabase_url, 'https://iseqgaewjpjcxrndibep.supabase.co')

  def test_render_student_accepts_supabase_upload_reservations_without_azure_credentials(self):
    with patch.dict(os.environ, {
      'BACKEND_ENV': 'production',
      'PESO_DEPLOYMENT_ENVIRONMENT': 'student',
      'SUPABASE_URL': 'https://iseqgaewjpjcxrndibep.supabase.co',
      'SUPABASE_SERVICE_ROLE_KEY': 'test',
      'CLEANUP_JOB_TOKEN': 'test',
      'BACKEND_CORS_ORIGINS': 'https://main--peso-webapp.netlify.app',
      'UPLOAD_RESERVATIONS_ENABLED': 'true',
      'UPLOAD_STORAGE_PROVIDER': 'supabase',
    }, clear=True):
      get_settings.cache_clear()
      settings = get_settings()
    self.assertTrue(settings.upload_reservations_enabled)
    self.assertEqual(settings.upload_storage_provider, 'supabase')
    self.assertEqual(settings.azure_blob_account_url, '')

  def test_production_cannot_select_supabase_uploads_outside_student(self):
    with patch.dict(os.environ, {
      'BACKEND_ENV': 'production',
      'SUPABASE_URL': 'https://example.supabase.co',
      'SUPABASE_SERVICE_ROLE_KEY': 'test',
      'CLEANUP_JOB_TOKEN': 'test',
      'BACKEND_CORS_ORIGINS': 'https://app.example.com',
      'UPLOAD_RESERVATIONS_ENABLED': 'true',
      'UPLOAD_STORAGE_PROVIDER': 'supabase',
    }, clear=True):
      get_settings.cache_clear()
      with self.assertRaisesRegex(RuntimeError, 'restricted to the Student environment'):
        get_settings()
