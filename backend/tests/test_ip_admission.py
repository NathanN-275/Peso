from unittest import TestCase
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.services.config import Settings
from app.services.ip_admission import client_ip, enforce_us_ip
from app.routes.upload_reservations import router
from app.services.auth import get_current_user_id


class IpAdmissionTest(TestCase):
  def test_direct_caller_cannot_forge_forwarding_header(self):
    self.assertEqual(client_ip('198.51.100.10', '8.8.8.8', ('10.0.0.0/8',)), '198.51.100.10')

  def test_trusted_chain_uses_nearest_untrusted_hop_not_attacker_prefix(self):
    self.assertEqual(client_ip('10.0.0.2', '8.8.8.8, 198.51.100.10, 10.0.0.1', ('10.0.0.0/8',)), '198.51.100.10')

  def test_ipv6_and_missing_malformed_or_all_trusted_chain(self):
    self.assertEqual(client_ip('::1', '2001:db8::1', ('::1/128',)), '2001:db8::1')
    for header in (None, '', 'invalid', '10.0.0.1', ','.join(['10.0.0.1']*17)):
      with self.subTest(header=header), self.assertRaises(ValueError):
        client_ip('10.0.0.2', header, ('10.0.0.0/8',))

  def test_country_header_does_not_override_lookup_and_no_reservation_is_created(self):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: 'test-user'
    settings = Settings(backend_env='test', supabase_url='https://example.supabase.co',
                        supabase_service_role_key='test', us_ip_beta_enabled=True)
    client = MagicMock()
    client.rpc.return_value.execute.return_value.data = False
    with patch('app.services.ip_admission.get_settings', return_value=settings), patch(
      'app.services.ip_admission.get_supabase_admin_client', return_value=client), patch(
      'app.routes.upload_reservations.UploadReservationRepository') as repository:
      response = TestClient(app, client=('198.51.100.10', 1234)).post('/upload-reservations',
        headers={'CF-IPCountry':'US', 'X-Forwarded-For':'8.8.8.8'}, json={})
    self.assertEqual(response.status_code, 403)
    repository.assert_not_called()
    client.rpc.assert_called_once_with('is_us_beta_ip', {'p_ip':'198.51.100.10'})

  def test_only_explicit_true_allows_and_provider_failure_denies(self):
    request = Request({'type':'http', 'client':('198.51.100.10',1234), 'headers':[]})
    settings = Settings(backend_env='test', supabase_url='https://example.supabase.co',
                        supabase_service_role_key='test', us_ip_beta_enabled=True)
    client = MagicMock()
    with patch('app.services.ip_admission.get_settings', return_value=settings), patch(
      'app.services.ip_admission.get_supabase_admin_client', return_value=client):
      for result in (False, None, [], 'true'):
        client.rpc.return_value.execute.return_value.data = result
        with self.subTest(result=result), self.assertRaises(HTTPException) as error:
          enforce_us_ip(request)
        self.assertEqual(error.exception.status_code, 403)
      client.rpc.return_value.execute.return_value.data = True
      enforce_us_ip(request)
      client.rpc.return_value.execute.side_effect = RuntimeError('unavailable')
      with self.assertRaises(HTTPException) as error:
        enforce_us_ip(request)
      self.assertEqual(error.exception.status_code, 503)
