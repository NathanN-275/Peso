from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.routes.budget_admission import IntakeMeasurement, evaluate_budget_admission
from app.services.config import Settings, get_settings


class IntakeStopTest(TestCase):
  def setUp(self):
    self.settings = Settings(backend_env='test', supabase_url='https://example.supabase.co',
                             supabase_service_role_key='test', budget_shutdown_token='test-token',
                             intake_stop_projected_monthly_usd=50,
                             object_storage_limit_bytes=1000, storage_block_ratio=0.95)
    self.client = MagicMock()
    self.patch_settings = patch('app.routes.budget_admission.get_settings', return_value=self.settings)
    self.patch_client = patch('app.routes.budget_admission.get_supabase_admin_client', return_value=self.client)
    self.patch_settings.start()
    self.patch_client.start()
    self.addCleanup(self.patch_settings.stop)
    self.addCleanup(self.patch_client.stop)

  def sample(self, **overrides):
    return IntakeMeasurement(**{'observed_at': datetime.now(timezone.utc),
      'projected_monthly_usd': Decimal('10'), 'storage_used_bytes': 100, **overrides})

  def test_alert_does_not_stop_below_selected_threshold(self):
    result = evaluate_budget_admission(self.sample(projected_monthly_usd=Decimal('35')), 'test-token')
    self.assertEqual(result, {'stop_triggered': False, 'reasons': [], 'spend_alert': True})
    self.client.rpc.assert_not_called()

  def test_equality_at_spend_or_storage_threshold_stops_intake(self):
    for sample, reason in [(self.sample(projected_monthly_usd=Decimal('50')), 'projected_spend'),
                           (self.sample(storage_used_bytes=950), 'storage_pressure')]:
      with self.subTest(reason=reason):
        self.client.reset_mock()
        result = evaluate_budget_admission(sample, 'test-token')
        self.assertTrue(result['stop_triggered'])
        self.assertEqual(result['reasons'], [reason])
        self.client.rpc.assert_called_once_with('disable_video_upload_admission', {})

  def test_healthy_measurement_never_reenables_a_previous_stop(self):
    evaluate_budget_admission(self.sample(storage_used_bytes=950), 'test-token')
    self.client.reset_mock()
    self.assertFalse(evaluate_budget_admission(self.sample(), 'test-token')['stop_triggered'])
    self.client.rpc.assert_not_called()

  def test_wrong_token_and_missing_threshold_cannot_change_admission(self):
    with self.assertRaises(HTTPException) as error:
      evaluate_budget_admission(self.sample(), 'wrong')
    self.assertEqual(error.exception.status_code, 401)
    with patch('app.routes.budget_admission.get_settings', return_value=replace(self.settings, intake_stop_projected_monthly_usd=None)):
      with self.assertRaises(HTTPException) as error:
        evaluate_budget_admission(self.sample(), 'test-token')
    self.assertEqual(error.exception.status_code, 503)
    self.client.rpc.assert_not_called()

  def test_stale_and_future_measurements_are_rejected(self):
    for delta in (-301, 31):
      with self.subTest(delta=delta), self.assertRaises(HTTPException) as error:
        evaluate_budget_admission(self.sample(observed_at=datetime.now(timezone.utc)+timedelta(seconds=delta)), 'test-token')
      self.assertEqual(error.exception.status_code, 422)
    self.client.rpc.assert_not_called()

  def test_invalid_measurements_are_not_treated_as_zero(self):
    for changes in ({'projected_monthly_usd': 'NaN'}, {'projected_monthly_usd': -1},
                    {'storage_used_bytes': -1}, {'storage_used_bytes': True}, {'observed_at': datetime.now()}):
      with self.subTest(changes=changes), self.assertRaises(ValidationError):
        self.sample(**changes)

  def test_database_failure_is_not_reported_as_success(self):
    self.client.rpc.return_value.execute.side_effect = RuntimeError('unavailable')
    with self.assertRaises(RuntimeError):
      evaluate_budget_admission(self.sample(storage_used_bytes=950), 'test-token')

  def test_unreviewed_or_invalid_config_does_not_silently_choose_a_threshold(self):
    environment = {'BACKEND_ENV': 'test', 'SUPABASE_URL': 'https://example.supabase.co',
                   'SUPABASE_SERVICE_ROLE_KEY': 'test', 'CLEANUP_JOB_TOKEN': 'test'}
    self.addCleanup(get_settings.cache_clear)
    with patch.dict(os.environ, environment, clear=True):
      get_settings.cache_clear()
      self.assertIsNone(get_settings().intake_stop_projected_monthly_usd)
      for value in ('0', '-1', '51', 'nan', '35.5'):
        os.environ['INTAKE_STOP_PROJECTED_MONTHLY_USD'] = value
        get_settings.cache_clear()
        with self.subTest(value=value), self.assertRaises(RuntimeError):
          get_settings()
      os.environ['INTAKE_STOP_PROJECTED_MONTHLY_USD'] = '35'
      get_settings.cache_clear()
      self.assertEqual(get_settings().intake_stop_projected_monthly_usd, 35)
