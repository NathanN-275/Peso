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
