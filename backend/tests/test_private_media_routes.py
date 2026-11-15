from __future__ import annotations

from datetime import datetime, timedelta, timezone
import asyncio
import importlib
import os
from types import SimpleNamespace
from threading import Event
import unittest
from unittest.mock import Mock, patch

import httpx
from fastapi import HTTPException

from app.services.auth import VerifiedAuthContext, get_current_auth_context
from app.services.private_media import IssuedMediaGrant
from app.services.private_media_stream import PrivateMediaAsset
from app.routes import private_media as routes

OWNER = '00000000-0000-0000-0000-000000000001'
SESSION = '00000000-0000-0000-0000-000000000002'
VIDEO = '00000000-0000-0000-0000-000000000003'
ORIGIN = 'https://usepeso.com'
API = 'https://api.usepeso.com'
PATH = '/private-media/video/' + VIDEO + '/'
BROWSER_PATH = '/private-media/session/' + SESSION + '/video/' + VIDEO + '/'
TOKEN = 'A' * 43
DATA = b'0123456789' * 200


class Bytes(httpx.AsyncByteStream):
  def __init__(self, data): self.data = data
  async def __aiter__(self): yield self.data
  async def aclose(self): pass


class PrivateMediaRoutesTest(unittest.IsolatedAsyncioTestCase):
  async def asyncSetUp(self):
    with patch.dict(os.environ, {'BACKEND_CORS_ORIGINS': ORIGIN, 'SUPABASE_URL': 'https://storage.invalid',
      'SUPABASE_SERVICE_ROLE_KEY': 'synthetic-offline', 'CLEANUP_JOB_TOKEN': 'synthetic-offline'}):
      from app.services.config import get_settings
      get_settings.cache_clear()
      main = importlib.reload(importlib.import_module('app.main'))
    self.app = main.app
    self.app.dependency_overrides[get_current_auth_context] = lambda: VerifiedAuthContext(OWNER, SESSION, 2000000000)
    self.settings = SimpleNamespace(private_media_enabled=True, private_media_public_origin=API,
      private_media_browser_origins=(ORIGIN,), cors_origins=(ORIGIN,), upload_storage_provider='supabase')
    self.service = Mock()
    self.service.issue.return_value = IssuedMediaGrant(TOKEN, datetime.now(timezone.utc) + timedelta(seconds=120))
    self.service.revoke_global_session.return_value = {'scope': 'global',
      'completed_at': datetime.now(timezone.utc).isoformat(), 'replayed': False}
    self.service.revoke_local_session.return_value = {'scope': 'local', 'owner_id': OWNER, 'session_id': SESSION,
      'completed_at': datetime.now(timezone.utc).isoformat(), 'replayed': False}
    self.service.accept_session.return_value = {'owner_id': OWNER, 'session_id': SESSION, 'accepted': True}
    self.service.session_cookie_paths.return_value = ([PATH], None)
    self.service.authorize_asset.return_value = PrivateMediaAsset(
      url='https://storage.invalid/private/x?token=synthetic-storage-secret', owner_id=OWNER,
      size_bytes=len(DATA), content_type='video/mp4')
    self.patches = [patch.object(routes, 'get_settings', return_value=self.settings),
      patch.object(routes, 'PrivateMediaService', return_value=self.service)]
    self.upstream = []
    def respond(request):
      self.upstream.append(request)
      body = DATA
      headers = {'Content-Length': str(len(DATA))}
      status = 200
      if request.method == 'GET' and request.headers.get('range'):
        first, last = map(int, request.headers['range'][6:].split('-'))
        body = DATA[first:last + 1]
        headers.update({'Content-Length': str(len(body)), 'Content-Range': f'bytes {first}-{last}/{len(DATA)}'})
        status = 206
      return httpx.Response(status, headers=headers, stream=Bytes(b'' if request.method == 'HEAD' else body))
    self.pool = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    self.patches.append(patch('app.services.private_media_stream.get_pooled_async_http_client', return_value=self.pool))
    for item in self.patches: item.start()
    self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=API)

  async def asyncTearDown(self):
    await self.client.aclose()
    await self.pool.aclose()
    for item in reversed(self.patches): item.stop()
    self.app.dependency_overrides.clear()

  def private(self, response, status):
    self.assertEqual(response.status_code, status, response.text[:200])
    self.assertEqual(response.headers['cache-control'], 'private, no-store')
    self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
    self.assertNotIn('synthetic-storage-secret', str(response.headers) + response.text)

  async def issue(self, transport='browser', headers=None, path=None):
    return await self.client.post(path or (BROWSER_PATH if transport == 'browser' else PATH) + 'session', headers=headers if headers is not None else {'Origin': ORIGIN},
      json={'transport': transport, 'asset_kinds': ['playback', 'thumbnail']})

  async def test_browser_issue_has_host_only_scoped_secure_cookie_and_no_json_token(self):
    response = await self.issue()
    self.private(response, 200)
    cookie = response.headers['set-cookie']
    for value in ('__Secure-peso-media=', 'HttpOnly', 'Secure', 'SameSite=strict', 'Path=' + BROWSER_PATH):
      self.assertIn(value, cookie)
    self.assertNotIn('Domain=', cookie)
    self.assertNotIn(TOKEN, response.text)
    self.assertEqual(response.json()['urls']['playback'], API + BROWSER_PATH + 'playback')
    self.assertEqual(response.json()['urls']['thumbnail'], API + BROWSER_PATH + 'thumbnail')
    self.service.issue.assert_called_once()

  async def test_browser_cookie_issuer_must_match_media_host(self):
    self.settings.private_media_public_origin = 'https://media.usepeso.com'
    self.private(await self.issue(), 503)
    self.service.issue.assert_not_called()

  async def test_tls_termination_matches_host_without_trusting_forwarded_headers(self):
    response = await self.client.post('http://api.usepeso.com' + BROWSER_PATH + 'session', headers={'Origin': ORIGIN},
      json={'transport': 'browser', 'asset_kinds': ['playback']})
    self.private(response, 200)
    self.assertIn('Secure', response.headers['set-cookie'])
    self.assertEqual(response.json()['urls']['playback'], API + BROWSER_PATH + 'playback')
    self.service.issue.reset_mock()
    response = await self.client.post('http://wrong-host.invalid' + BROWSER_PATH + 'session',
      headers={'Origin': ORIGIN, 'X-Forwarded-Host': 'api.usepeso.com', 'X-Forwarded-Proto': 'https'},
      json={'transport': 'browser', 'asset_kinds': ['playback']})
    self.private(response, 503)
    self.service.issue.assert_not_called()

  async def test_native_issue_returns_only_media_grant_without_cookie(self):
    response = await self.issue('native', headers={})
    self.private(response, 200)
    self.assertEqual(response.json()['media_grant'], TOKEN)
    self.assertNotIn('set-cookie', response.headers)

  async def test_browser_cannot_select_native_transport(self):
    for headers in ({'Origin': ORIGIN}, {'Sec-Fetch-Site': 'same-site'}, {'Sec-Fetch-Mode': 'cors'}):
      with self.subTest(headers=headers):
        self.private(await self.issue('native', headers=headers), 403)
    self.service.issue.assert_not_called()

  async def test_browser_issue_requires_exact_origin(self):
    for origin in ('https://evil.invalid', 'https://usepeso.com.evil.invalid', 'null', 'http://usepeso.com', ''):
      with self.subTest(origin=origin):
        self.private(await self.issue(headers={'Origin': origin}), 403)
    self.service.issue.assert_not_called()

  async def test_disabled_feature_fails_closed(self):
    self.settings.private_media_enabled = False
    self.private(await self.issue(), 503)
    self.private(await self.client.get(PATH + 'playback', headers={routes.GRANT_HEADER: TOKEN}), 503)
    self.service.issue.assert_not_called()
    self.service.authorize_asset.assert_not_called()

  async def test_invalid_configuration_fails_closed(self):
    for origin in ('http://api.usepeso.com', 'https://evil.invalid', 'https://api.usepeso.com:443',
                    'https://api.usepeso.com/path', 'https://user@api.usepeso.com', 'https://['):
      self.settings.private_media_public_origin = origin
      with self.subTest(origin=origin):
        self.private(await self.issue(), 503)
    self.settings.private_media_public_origin = API
    for origins in ((), ('https://evil.invalid',), ('https://main.usepeso.com',)):
      self.settings.private_media_browser_origins = origins
      with self.subTest(origins=origins):
        self.private(await self.issue(), 503)
    self.service.issue.assert_not_called()

  async def test_non_supabase_storage_fails_closed(self):
    self.settings.upload_storage_provider = 'azure'
    self.private(await self.issue(), 503)
    self.service.issue.assert_not_called()

  async def test_query_credentials_rejected_before_issuer_or_authorizer(self):
    self.private(await self.issue(path=PATH + 'session?token=' + TOKEN), 400)
    self.private(await self.client.get(PATH + 'playback?media_grant=' + TOKEN, headers={routes.GRANT_HEADER: TOKEN}), 400)
    self.service.issue.assert_not_called()
    self.service.authorize_asset.assert_not_called()
    self.assertEqual(self.upstream, [])

  async def test_validation_unknown_route_and_wrong_method_are_no_store(self):
    self.private(await self.client.post(PATH + 'session', json={'transport': 'browser', 'asset_kinds': [], 'extra': TOKEN}), 422)
    self.private(await self.client.get('/private-media/unknown'), 404)
    self.private(await self.client.delete(PATH + 'playback'), 405)

  async def test_browser_cookie_get_and_each_range_reauthorize_without_gzip(self):
    await self.issue()
    headers = {'Origin': ORIGIN, 'Accept-Encoding': 'gzip'}
    response = await self.client.get(BROWSER_PATH + 'playback', headers=headers)
    self.private(response, 200)
    self.assertEqual(response.content, DATA)
    self.assertNotIn('content-encoding', response.headers)
    response = await self.client.get(BROWSER_PATH + 'playback', headers={**headers, 'Range': 'bytes=100-1499'})
    self.private(response, 206)
    self.assertEqual(response.content, DATA[100:1500])
    self.assertEqual(response.headers['content-range'], f'bytes 100-1499/{len(DATA)}')
    self.assertNotIn('content-encoding', response.headers)
    self.assertEqual(self.service.authorize_asset.call_count, 2)
    self.assertEqual(response.headers['access-control-allow-origin'], ORIGIN)
    self.assertIn('Content-Range', response.headers['access-control-expose-headers'])
    self.assertEqual(self.upstream[-1].headers['accept-encoding'], 'identity')
    self.assertNotIn(routes.GRANT_HEADER, self.upstream[-1].headers)
    self.assertNotIn('cookie', self.upstream[-1].headers)

  async def test_head_reauthorizes_and_returns_no_body(self):
    response = await self.client.head(PATH + 'playback', headers={routes.GRANT_HEADER: TOKEN, 'Range': 'bytes=3-5'})
    self.private(response, 200)
    self.assertEqual(response.content, b'')
    self.assertEqual(response.headers['content-length'], str(len(DATA)))
    self.assertEqual(self.upstream[0].method, 'HEAD')
    self.assertNotIn('range', self.upstream[0].headers)

  async def test_revocation_denies_next_range_without_upstream(self):
    headers = {routes.GRANT_HEADER: TOKEN}
    self.private(await self.client.get(PATH + 'playback', headers=headers), 200)
    self.service.authorize_asset.side_effect = HTTPException(403, 'Private media unavailable.')
    self.private(await self.client.get(PATH + 'playback', headers={**headers, 'Range': 'bytes=0-9'}), 403)
    self.assertEqual(len(self.upstream), 1)

  async def test_ambiguous_account_or_browser_native_credentials_are_rejected(self):
    cases = [({routes.GRANT_HEADER: TOKEN, 'Authorization': 'Bearer synthetic-account-token'}, 401),
      ({routes.GRANT_HEADER: TOKEN, 'Origin': ORIGIN}, 403),
      ({routes.GRANT_HEADER: TOKEN, 'Sec-Fetch-Site': 'same-site'}, 403),
      ({routes.GRANT_HEADER: TOKEN, 'Cookie': routes.COOKIE + '=' + TOKEN}, 400),
      ({'Origin': ORIGIN}, 409), ({'Cookie': routes.COOKIE + '=' + TOKEN}, 403)]
    for headers, status in cases:
      with self.subTest(headers=headers):
        self.private(await self.client.get(PATH + 'playback', headers=headers), status)
    self.service.authorize_asset.assert_not_called()
    self.assertEqual(self.upstream, [])

  async def test_ordinary_api_responses_still_compress(self):
    @self.app.get('/synthetic-compression-check')
    def response(): return {'data': 'x' * 3000}
    response = await self.client.get('/synthetic-compression-check', headers={'Accept-Encoding': 'gzip'})
    self.assertEqual(response.status_code, 200)
    self.assertEqual(response.headers['content-encoding'], 'gzip')
    self.assertEqual(response.json()['data'], 'x' * 3000)

  async def test_browser_global_logout_returns_committed_receipt_without_provider_logout(self):
    response = await self.client.post('/private-media/logout', headers={'Origin': ORIGIN}, json={'transport': 'browser'})
    self.private(response, 200)
    self.assertEqual(response.json(), {**self.service.revoke_global_session.return_value, 'owner_id': OWNER,
      'session_id': SESSION, 'next_cursor': None, 'cookie_cleanup_complete': True})
    self.service.revoke_global_session.assert_called_once_with(VerifiedAuthContext(OWNER, SESSION, 2000000000))
    self.assertIn('Max-Age=0', response.headers['set-cookie'])
    self.service.session_cookie_paths.assert_called_once_with(VerifiedAuthContext(OWNER, SESSION, 2000000000), None, all_sessions=True)
    self.assertEqual(self.upstream, [])

  async def test_native_global_logout_and_replay_are_explicit(self):
    self.service.revoke_global_session.return_value['replayed'] = True
    response = await self.client.post('/private-media/logout', json={'transport': 'native'})
    self.private(response, 200)
    self.assertTrue(response.json()['replayed'])
    self.assertNotIn(TOKEN, response.text)

  async def test_logout_cannot_select_owner_session_scope_or_request_id(self):
    for field in ('user_id', 'session_id', 'scope', 'request_id'):
      with self.subTest(field=field):
        response = await self.client.post('/private-media/logout', json={'transport': 'native', field: OWNER})
        self.private(response, 422)
    self.service.revoke_global_session.assert_not_called()

  async def test_logout_enforces_transport_origin_and_default_disable(self):
    for transport, headers in [('browser', {}), ('browser', {'Origin': 'https://evil.invalid'}),
                                ('native', {'Origin': ORIGIN}), ('native', {'Sec-Fetch-Mode': 'cors'})]:
      with self.subTest(transport=transport, headers=headers):
        self.private(await self.client.post('/private-media/logout', headers=headers, json={'transport': transport}), 403)
    self.settings.private_media_enabled = False
    self.private(await self.client.post('/private-media/logout', json={'transport': 'native'}), 503)
    self.service.revoke_global_session.assert_not_called()

  async def test_logout_requires_verified_auth_context(self):
    async def denied(): raise HTTPException(401, 'Invalid bearer token.')
    self.app.dependency_overrides[get_current_auth_context] = denied
    self.private(await self.client.post('/private-media/logout', json={'transport': 'native'}), 401)
    self.service.revoke_global_session.assert_not_called()

  async def test_unexpected_media_service_initialization_failure_is_safe_no_store(self):
    with patch.object(routes, 'PrivateMediaService', side_effect=RuntimeError('synthetic-initialization-secret')):
      responses = [await self.issue(), await self.client.get(PATH + 'playback', headers={routes.GRANT_HEADER: TOKEN}),
        await self.client.post('/private-media/logout', json={'transport': 'native'})]
    for response in responses:
      self.private(response, 503)
      self.assertNotIn('synthetic-initialization-secret', response.text)
    self.assertEqual(self.upstream, [])

  async def test_logout_rpc_denial_does_not_report_success(self):
    self.service.revoke_global_session.side_effect = HTTPException(403, 'Private media unavailable.')
    response = await self.client.post('/private-media/logout', json={'transport': 'native'})
    self.private(response, 403)
    self.assertNotIn('completed_at', response.json())

  async def test_replacement_revokes_exact_verified_outgoing_context_and_clears_matching_paths(self):
    archive_path = '/private-media/archive/00000000-0000-0000-0000-000000000004/'
    untouched = '/private-media/video/00000000-0000-0000-0000-000000000005/'
    for path in (PATH, archive_path, untouched):
      self.client.cookies.set(routes.COOKIE, TOKEN, domain='api.usepeso.com', path=path)
    self.service.session_cookie_paths.return_value = ([archive_path, PATH], None)
    response = await self.client.post('/private-media/session-replacement', headers={'Origin': ORIGIN}, json={'transport': 'browser'})
    self.private(response, 200)
    self.assertEqual(response.json(), {**self.service.revoke_local_session.return_value,
      'next_cursor': None, 'cookie_cleanup_complete': True})
    self.service.revoke_local_session.assert_called_once_with(VerifiedAuthContext(OWNER, SESSION, 2000000000))
    self.service.revoke_global_session.assert_not_called()
    self.service.session_cookie_paths.assert_called_once_with(VerifiedAuthContext(OWNER, SESSION, 2000000000), None, all_sessions=False)
    headers = response.headers.get_list('set-cookie')
    self.assertEqual(len(headers), 2)
    for value, path in zip(headers, (archive_path, PATH)):
      for expected in ('__Secure-peso-media=', 'Path=' + path, 'Max-Age=0', 'HttpOnly', 'Secure', 'SameSite=strict'):
        self.assertIn(expected, value)
      self.assertNotIn('Domain=', value)
    remaining = [(cookie.name, cookie.path) for cookie in self.client.cookies.jar]
    self.assertEqual(remaining, [(routes.COOKIE, untouched)])

  async def test_replacement_page_continuation_and_replay_do_not_report_final_early(self):
    cursor = 'video:' + VIDEO
    self.service.revoke_local_session.return_value['replayed'] = True
    self.service.session_cookie_paths.return_value = ([PATH] * 32, cursor)
    response = await self.client.post('/private-media/session-replacement', headers={'Origin': ORIGIN}, json={'transport': 'browser'})
    self.private(response, 200)
    self.assertEqual(len(response.headers.get_list('set-cookie')), 32)
    self.assertFalse(response.json()['cookie_cleanup_complete'])
    self.assertEqual(response.json()['next_cursor'], cursor)
    self.assertTrue(response.json()['replayed'])
    self.service.session_cookie_paths.return_value = ([], None)
    response = await self.client.post('/private-media/session-replacement', headers={'Origin': ORIGIN}, json={'transport': 'browser', 'cursor': cursor})
    self.private(response, 200)
    self.assertTrue(response.json()['cookie_cleanup_complete'])
    self.service.session_cookie_paths.assert_called_with(VerifiedAuthContext(OWNER, SESSION, 2000000000), cursor, all_sessions=False)

  async def test_global_cookie_pages_replay_same_receipt_and_clear_all_owner_inventory(self):
    cursor = 'archive:' + VIDEO
    self.service.revoke_global_session.return_value['replayed'] = True
    self.service.session_cookie_paths.return_value = ([PATH] * 32, cursor)
    first = await self.client.post('/private-media/logout', headers={'Origin': ORIGIN}, json={'transport': 'browser'})
    self.private(first, 200)
    self.assertEqual(first.json()['scope'], 'global')
    self.assertFalse(first.json()['cookie_cleanup_complete'])
    self.assertEqual(first.json()['next_cursor'], cursor)
    self.assertEqual(len(first.headers.get_list('set-cookie')), 32)
    self.service.accept_session.return_value = {'owner_id': OWNER, 'session_id': SESSION, 'accepted': True}
    self.service.session_cookie_paths.return_value = ([PATH], None)
    final = await self.client.post('/private-media/logout', headers={'Origin': ORIGIN}, json={'transport': 'browser', 'cursor': cursor})
    self.private(final, 200)
    self.assertEqual(first.json()['completed_at'], final.json()['completed_at'])
    self.assertTrue(final.json()['replayed'])
    self.assertTrue(final.json()['cookie_cleanup_complete'])
    self.service.session_cookie_paths.assert_called_with(VerifiedAuthContext(OWNER, SESSION, 2000000000), cursor, all_sessions=True)
    self.service.revoke_local_session.assert_not_called()

  async def test_native_replacement_has_final_bound_receipt_without_cookie_inventory(self):
    response = await self.client.post('/private-media/session-replacement', json={'transport': 'native'})
    self.private(response, 200)
    self.assertEqual(set(response.json()), {'scope', 'owner_id', 'session_id', 'completed_at', 'replayed', 'next_cursor', 'cookie_cleanup_complete'})
    self.assertTrue(response.json()['cookie_cleanup_complete'])
    self.assertNotIn('set-cookie', response.headers)
    self.service.session_cookie_paths.assert_not_called()

  async def test_both_revocations_reject_identity_selection_and_bad_cursor_before_commit(self):
    for endpoint in ('logout', 'session-replacement'):
      for field in ('owner_id', 'user_id', 'session_id', 'scope', 'request_id', 'paths', 'resource_id'):
        with self.subTest(endpoint=endpoint, field=field):
          self.private(await self.client.post('/private-media/' + endpoint, json={'transport': 'native', field: OWNER}), 422)
      for cursor in ('video:00000000-0000-0000-0000-000000000000', 'video:' + VIDEO.upper().replace('000003','00000A'), 'other:' + VIDEO, '/arbitrary/path', 'video:' + VIDEO + '?token=x'):
        with self.subTest(endpoint=endpoint, cursor=cursor):
          self.private(await self.client.post('/private-media/' + endpoint, headers={'Origin': ORIGIN}, json={'transport': 'browser', 'cursor': cursor}), 422)
      self.private(await self.client.post('/private-media/' + endpoint, json={'transport': 'native', 'cursor': 'video:' + VIDEO}), 400)
    self.service.revoke_local_session.assert_not_called()
    self.service.revoke_global_session.assert_not_called()

  async def test_replacement_rejects_wrong_origin_host_disabled_and_unverified_context(self):
    for endpoint in ('logout', 'session-replacement'):
      self.private(await self.client.post('/private-media/' + endpoint, headers={'Origin': 'https://evil.invalid'}, json={'transport': 'browser'}), 403)
      self.private(await self.client.post('https://wrong.invalid/private-media/' + endpoint,
        headers={'Origin': ORIGIN, 'X-Forwarded-Host': 'api.usepeso.com'}, json={'transport': 'browser'}), 503)
    async def denied(): raise HTTPException(401, 'Invalid bearer token.')
    self.app.dependency_overrides[get_current_auth_context] = denied
    self.private(await self.client.post('/private-media/session-replacement', json={'transport': 'native'}), 401)
    self.service.revoke_local_session.assert_not_called()
    self.service.revoke_global_session.assert_not_called()

  async def test_replacement_unknown_commit_or_inventory_failure_does_not_return_completion(self):
    self.service.revoke_local_session.side_effect = HTTPException(503, 'Private media unavailable.')
    response = await self.client.post('/private-media/session-replacement', json={'transport': 'native'})
    self.private(response, 503)
    self.assertNotIn('completed_at', response.json())
    self.service.session_cookie_paths.assert_not_called()
    self.service.revoke_local_session.side_effect = None
    self.service.session_cookie_paths.side_effect = RuntimeError('synthetic-inventory-secret')
    response = await self.client.post('/private-media/session-replacement', headers={'Origin': ORIGIN}, json={'transport': 'browser'})
    self.private(response, 503)
    self.assertNotIn('synthetic-inventory-secret', response.text)
    self.assertNotIn('completed_at', response.json())

  async def test_incoming_acceptance_uses_only_verified_context_and_issues_no_cookie_or_media(self):
    for transport, headers in (('browser', {'Origin': ORIGIN}), ('native', {})):
      with self.subTest(transport=transport):
        response = await self.client.post('/private-media/session-acceptance', headers=headers, json={'transport': transport})
        self.private(response, 200)
        self.assertEqual(response.json(), {'owner_id': OWNER, 'session_id': SESSION, 'accepted': True})
        self.assertNotIn('set-cookie', response.headers)
    self.assertEqual(self.service.accept_session.call_count, 2)
    self.service.accept_session.assert_called_with(VerifiedAuthContext(OWNER, SESSION, 2000000000))
    self.service.issue.assert_not_called()
    self.service.revoke_local_session.assert_not_called()
    self.service.revoke_global_session.assert_not_called()
    self.service.session_cookie_paths.assert_not_called()

  async def test_incoming_acceptance_rejects_identity_selectors_and_wrong_origin_host(self):
    for field in ('owner_id', 'user_id', 'session_id', 'scope', 'cursor', 'request_id', 'accepted'):
      with self.subTest(field=field):
        self.private(await self.client.post('/private-media/session-acceptance',
          json={'transport': 'native', field: OWNER}), 422)
    self.private(await self.client.post('/private-media/session-acceptance',
      headers={'Origin': 'https://evil.invalid'}, json={'transport': 'browser'}), 403)
    self.private(await self.client.post('https://wrong.invalid/private-media/session-acceptance',
      headers={'Origin': ORIGIN, 'X-Forwarded-Host': 'api.usepeso.com'}, json={'transport': 'browser'}), 503)
    self.private(await self.client.post('/private-media/session-acceptance',
      headers={'Origin': ORIGIN}, json={'transport': 'native'}), 403)
    self.service.accept_session.assert_not_called()

  async def test_incoming_acceptance_denial_and_unverified_or_disabled_context_never_acknowledge(self):
    for code in (403, 503):
      self.service.accept_session.side_effect = HTTPException(code, 'Private media unavailable.')
      response = await self.client.post('/private-media/session-acceptance', json={'transport': 'native'})
      self.private(response, code)
      self.assertNotIn('accepted', response.json())
    self.service.accept_session.reset_mock()
    self.settings.private_media_enabled = False
    self.private(await self.client.post('/private-media/session-acceptance', json={'transport': 'native'}), 503)
    self.settings.private_media_enabled = True
    async def denied(): raise HTTPException(401, 'Invalid bearer token.')
    self.app.dependency_overrides[get_current_auth_context] = denied
    self.private(await self.client.post('/private-media/session-acceptance', json={'transport': 'native'}), 401)
    self.service.accept_session.assert_not_called()

  async def test_private_media_settings_are_disabled_by_default(self):
    from app.services.config import get_settings
    with patch.dict(os.environ, {'SUPABASE_URL': 'https://storage.invalid', 'SUPABASE_SERVICE_ROLE_KEY': 'synthetic-offline',
      'CLEANUP_JOB_TOKEN': 'synthetic-offline', 'PRIVATE_MEDIA_ENABLED': 'false', 'PRIVATE_MEDIA_PUBLIC_ORIGIN': '',
      'PRIVATE_MEDIA_BROWSER_ORIGINS': ''}):
      get_settings.cache_clear()
      settings = get_settings()
      self.assertFalse(settings.private_media_enabled)
      self.assertEqual(settings.private_media_public_origin, '')
      self.assertEqual(settings.private_media_browser_origins, ())
      get_settings.cache_clear()

  async def test_authorization_capacity_rejects_without_storage_bytes(self):
    for _ in range(16): self.assertTrue(routes._authorization_slots.acquire(blocking=False))
    try:
      self.private(await self.client.get(PATH + 'playback', headers={routes.GRANT_HEADER: TOKEN}), 429)
      self.service.authorize_asset.assert_not_called()
      self.assertEqual(self.upstream, [])
    finally:
      for _ in range(16): routes._authorization_slots.release()

  async def test_timed_out_thread_retains_slot_until_finished_and_receives_cancellation(self):
    started, release, finished = Event(), Event(), Event()
    observed = []
    def authorize(*args, is_cancelled):
      started.set()
      try:
        release.wait(2)
        observed.append(is_cancelled())
        return self.service.authorize_asset.return_value
      finally:
        finished.set()
    self.service.authorize_asset.side_effect = authorize
    with patch('app.services.private_media_stream._AUTH_TIMEOUT_SECONDS', 0.04):
      try:
        response = await self.client.get(PATH + 'playback', headers={routes.GRANT_HEADER: TOKEN})
        self.assertTrue(started.is_set())
        self.private(response, 504)
        self.assertFalse(finished.is_set())
        held = 0
        while routes._authorization_slots.acquire(blocking=False): held += 1
        for _ in range(held): routes._authorization_slots.release()
        self.assertEqual(held, 15)
        self.assertEqual(self.upstream, [])
      finally:
        release.set()
        for _ in range(100):
          if finished.is_set(): break
          await asyncio.sleep(0.01)
    self.assertTrue(finished.is_set())
    self.assertEqual(observed, [True])


if __name__ == '__main__':
  unittest.main()
