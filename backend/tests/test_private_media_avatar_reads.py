from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from fastapi import HTTPException
from app.routes import private_media as routes
from app.services.private_media_stream import PrivateMediaAsset
import test_private_media_service as service_fixture
from test_private_media_service import OWNER, SESSION, VIDEO, ATTEMPT, TOKEN, future
import test_private_media_routes as route_fixture
from test_private_media_routes import ORIGIN, API, DATA

PATH = '/private-media/avatar/' + VIDEO + '/'
BROWSER_PATH = '/private-media/session/' + SESSION + '/avatar/' + VIDEO + '/'
LEGACY = 'Re-upload your profile picture to finish the security update.'


def avatar(**changes):
  return dict(user_id=OWNER, session_id=SESSION, resource_kind='avatar', resource_id=VIDEO,
    expires_at=future(), attempt_id=ATTEMPT, provider='supabase', bucket='profile-avatars',
    storage_path=f'{OWNER}/avatar-{ATTEMPT}.jpg', content_type='image/jpeg', size_bytes=10,
    content_sha256='a' * 64, published_at=future(-1), **changes)


class AvatarReadServiceTest(unittest.TestCase):
  setUp = service_fixture.PrivateMediaServiceTest.setUp

  def prepare(self):
    self.db.rpc_rows = [avatar()]
    self.storage.create_signed_url.return_value = f'https://storage.invalid/storage/v1/object/sign/profile-avatars/{OWNER}/avatar-{ATTEMPT}.jpg?token=synthetic'

  def test_avatar_issue_uses_dedicated_rpc_with_verified_context_and_exact_scope(self):
    self.db.rpc_rows = [dict(resource_kind='avatar', resource_id=VIDEO, expires_at=future())]
    result = self.service.issue(self.context, 'avatar', VIDEO, ['avatar'])
    name, args = self.db.calls[0]
    self.assertEqual(name, 'issue_private_media_avatar_grant')
    self.assertEqual(set(args), {'p_user_id','p_session_id','p_token_hash','p_resource_id','p_jwt_expires_at'})
    self.assertEqual((args['p_user_id'], args['p_session_id'], args['p_resource_id']), (OWNER,SESSION,VIDEO))
    self.assertNotIn(result.token, repr(self.db.calls))
    self.factory.assert_not_called()

  def test_avatar_issue_requires_one_exact_avatar_asset_and_exact_rpc_shape(self):
    for assets in (['playback'], ['archive'], ['avatar','avatar'], ['avatar','thumbnail']):
      with self.subTest(assets=assets), self.assertRaises(HTTPException):
        self.service.issue(self.context, 'avatar', VIDEO, assets)
    self.assertEqual(self.db.calls, [])
    self.db.rpc_rows = [dict(resource_kind='avatar', resource_id=VIDEO, expires_at=future(), storage_path='private')]
    with self.assertRaises(HTTPException) as caught:
      self.service.issue(self.context, 'avatar', VIDEO, ['avatar'])
    self.assertEqual(caught.exception.status_code, 503)

  def test_only_dedicated_avatar_issue_legacy_code_is_actionable(self):
    class Error(Exception): code = 'P0002'
    self.db.error = Error('SYNTHETIC path and private response')
    with self.assertRaises(HTTPException) as caught:
      self.service.issue(self.context, 'avatar', VIDEO, ['avatar'])
    self.assertEqual((caught.exception.status_code, caught.exception.detail), (409, LEGACY))
    for action in (lambda: self.service.issue(self.context, 'video', VIDEO, ['playback']),
                   lambda: self.service.authorize_asset(TOKEN, 'avatar', VIDEO, 'avatar')):
      with self.assertRaises(HTTPException) as caught: action()
      self.assertEqual(caught.exception.status_code, 503)
      self.assertNotIn('SYNTHETIC', str(caught.exception.detail))
    self.factory.assert_not_called()

  def test_exact_retained_avatar_reads_without_video_or_profile_table_fallback(self):
    self.prepare()
    result = self.service.authorize_asset(TOKEN, 'avatar', VIDEO, 'avatar')
    self.assertEqual(self.db.calls, [('authorize_private_media_avatar_grant', {'p_token_hash': __import__('hashlib').sha256(TOKEN.encode()).hexdigest(), 'p_resource_id': VIDEO})])
    self.assertEqual((result.owner_id,result.size_bytes,result.content_type,result.download_name), (OWNER,10,'image/jpeg',None))
    self.factory.assert_called_once_with(bucket='profile-avatars')
    self.storage.get_object_info.assert_called_once_with(f'{OWNER}/avatar-{ATTEMPT}.jpg')
    self.storage.create_signed_url.assert_called_once_with(f'{OWNER}/avatar-{ATTEMPT}.jpg', expires_in=60)

  def test_malformed_retained_avatar_contract_never_opens_storage(self):
    self.prepare(); original = avatar()
    changes = [dict(user_id=SESSION),dict(user_id='invalid'),dict(session_id='invalid'),dict(resource_id=OWNER),
      dict(resource_kind='video'),dict(expires_at=future(-1)),dict(attempt_id='invalid'),dict(provider='azure'),
      dict(bucket='videos'),dict(storage_path=OWNER+'/legacy.jpg'),dict(content_type='image/png'),
      dict(size_bytes=True),dict(size_bytes=0),dict(size_bytes=524289),dict(size_bytes='10'),
      dict(content_sha256='A'*64),dict(content_sha256='bad'),dict(published_at=None),dict(published_at=future(60))]
    for updates in changes:
      self.db.rpc_rows = [{**original, **updates}]
      with self.subTest(updates=updates), self.assertRaises(HTTPException):
        self.service.authorize_asset(TOKEN, 'avatar', VIDEO, 'avatar')
    for field in original:
      row = dict(original); del row[field]; self.db.rpc_rows = [row]
      with self.subTest(missing=field), self.assertRaises(HTTPException):
        self.service.authorize_asset(TOKEN, 'avatar', VIDEO, 'avatar')
    self.db.rpc_rows = [{**original,'unexpected':'private'}]
    with self.assertRaises(HTTPException): self.service.authorize_asset(TOKEN, 'avatar', VIDEO, 'avatar')
    self.factory.assert_not_called()

  def test_avatar_length_metadata_failure_and_cancellation_never_sign(self):
    self.prepare()
    for info in ({'size':11},{'size':0},{'size':True},{},None):
      self.storage.get_object_info.return_value = info
      with self.subTest(info=info), self.assertRaises(HTTPException):
        self.service.authorize_asset(TOKEN, 'avatar', VIDEO, 'avatar')
    self.storage.create_signed_url.assert_not_called()
    self.storage.get_object_info.return_value={'size':10}
    stopped = False
    def rpc(name, values):
      nonlocal stopped
      stopped=True
      return [avatar()]
    self.service._rpc=rpc; self.factory.reset_mock()
    with self.assertRaises(HTTPException):
      self.service.authorize_asset(TOKEN,'avatar',VIDEO,'avatar',is_cancelled=lambda:stopped)
    self.factory.assert_not_called()

  def test_avatar_provider_url_is_bound_to_the_exact_retained_object(self):
    self.prepare()
    for url in (f'https://storage.invalid/storage/v1/object/sign/profile-avatars/{SESSION}/avatar-{ATTEMPT}.jpg?token=synthetic',
                f'https://storage.invalid/storage/v1/object/sign/profile-avatars/{OWNER}/avatar-{ATTEMPT}.jpg/other?token=synthetic',
                f'https://storage.invalid/storage/v1/object/sign/profile-avatars/{OWNER}%2Favatar-{ATTEMPT}.jpg?token=synthetic',
                f'https://storage.invalid/storage/v1/object/sign/profile-avatars/%30{OWNER[1:]}/avatar-{ATTEMPT}.jpg?token=synthetic',
                f'https://storage.invalid/storage/v1/object/sign/profile-avatars/{OWNER}/avatar-{ATTEMPT}.jpg?token=synthetic#fragment'):
      self.storage.create_signed_url.return_value=url
      with self.subTest(url=url), self.assertRaises(HTTPException):
        self.service.authorize_asset(TOKEN,'avatar',VIDEO,'avatar')

  def test_avatar_cookie_inventory_validates_and_orders_all_three_retained_kinds(self):
    self.db.rpc_rows = [dict(resource_kind=k,resource_id=VIDEO) for k in ['archive','avatar','video']]
    self.assertEqual(self.service.session_cookie_paths(self.context,None),
      ([f'/private-media/{k}/{VIDEO}/' for k in ['archive','avatar','video']],None))
    self.db.rpc_rows=[dict(resource_kind='video',resource_id=VIDEO)]
    self.service.session_cookie_paths(self.context,'avatar:'+VIDEO)
    self.assertEqual(self.db.calls[-1][1]['p_after_kind'],'avatar')
    self.db.rpc_rows=[dict(resource_kind='avatar',resource_id=VIDEO)]
    with self.assertRaises(HTTPException): self.service.session_cookie_paths(self.context,'avatar:'+VIDEO)


class AvatarReadRoutesTest(unittest.IsolatedAsyncioTestCase):
  asyncSetUp = route_fixture.PrivateMediaRoutesTest.asyncSetUp
  asyncTearDown = route_fixture.PrivateMediaRoutesTest.asyncTearDown
  private = route_fixture.PrivateMediaRoutesTest.private

  async def issue(self, transport='native', headers=None):
    return await self.client.post((BROWSER_PATH if transport == 'browser' else PATH)+'session',headers=headers or {},json={'transport':transport,'asset_kinds':['avatar']})

  def prepare_bytes(self):
    self.service.authorize_asset.return_value = PrivateMediaAsset(
      url='https://storage.invalid/private/x?token=synthetic-storage-secret',owner_id=OWNER,
      size_bytes=len(DATA),content_type='image/jpeg')

  async def test_native_avatar_issue_binds_current_revision_and_has_media_only_token(self):
    response=await self.issue();self.private(response,200)
    self.assertEqual(response.json()['resource_kind'],'avatar')
    self.assertEqual(response.json()['resource_id'],VIDEO)
    self.assertEqual(response.json()['urls'],{'avatar':API+PATH+'avatar'})
    self.assertEqual(response.json()['media_grant'],TOKEN)
    self.assertNotIn('set-cookie',response.headers)
    self.assertEqual(self.service.issue.call_args.args[1:],('avatar',VIDEO,['avatar']))

  async def test_browser_avatar_issue_cookie_is_hostonly_exact_revision_scope(self):
    response=await self.issue('browser',{'Origin':ORIGIN});self.private(response,200)
    cookie=response.headers['set-cookie']
    for text in ('Path='+BROWSER_PATH,'Secure','HttpOnly','SameSite=strict'):self.assertIn(text,cookie)
    self.assertNotIn('Domain=',cookie);self.assertNotIn(TOKEN,response.text)

  async def test_legacy_avatar_returns_exact_actionable_error_without_cookie_or_capability(self):
    self.service.issue.side_effect=HTTPException(409,LEGACY)
    response=await self.issue();self.private(response,409)
    self.assertEqual(response.json(),{'detail':LEGACY})
    self.assertNotIn('set-cookie',response.headers);self.assertNotIn(TOKEN,response.text)

  async def test_native_avatar_get_head_range_have_no_account_or_provider_credentials(self):
    self.prepare_bytes();headers={routes.GRANT_HEADER:TOKEN}
    response=await self.client.get(PATH+'avatar',headers=headers);self.private(response,200)
    self.assertEqual(response.content,DATA);self.assertEqual(response.headers['content-type'],'image/jpeg')
    self.assertNotIn('content-encoding',response.headers)
    response=await self.client.head(PATH+'avatar',headers=headers);self.private(response,200)
    self.assertEqual(response.content,b'');self.assertEqual(response.headers['content-length'],str(len(DATA)))
    response=await self.client.get(PATH+'avatar',headers={**headers,'Range':'bytes=3-19'});self.private(response,206)
    self.assertEqual(response.content,DATA[3:20])
    self.assertEqual(self.service.authorize_asset.call_count,3)
    for request in self.upstream:
      self.assertNotIn(routes.GRANT_HEADER,request.headers);self.assertNotIn('authorization',request.headers);self.assertNotIn('cookie',request.headers)

  async def test_browser_avatar_bytes_require_exact_origin_and_issuing_host(self):
    self.prepare_bytes();await self.issue('browser',{'Origin':ORIGIN})
    self.private(await self.client.get(BROWSER_PATH+'avatar',headers={'Origin':ORIGIN}),200)
    self.private(await self.client.get(BROWSER_PATH+'avatar',headers={'Origin':'https://evil.invalid'}),403)
    self.private(await self.client.get('https://wrong.invalid'+BROWSER_PATH+'avatar',headers={'Origin':ORIGIN,'Cookie':routes.COOKIE+'='+TOKEN,'X-Forwarded-Host':'api.usepeso.com'}),503)
    self.assertEqual(self.service.authorize_asset.call_count,1)

  async def test_avatar_mixed_account_cookie_header_query_credentials_never_authorize(self):
    for headers,status in [({routes.GRANT_HEADER:TOKEN,'Authorization':'Bearer synthetic'},401),
      ({routes.GRANT_HEADER:TOKEN,'Origin':ORIGIN},403),({routes.GRANT_HEADER:TOKEN,'Cookie':routes.COOKIE+'='+TOKEN},400)]:
      with self.subTest(headers=headers):self.private(await self.client.get(PATH+'avatar',headers=headers),status)
    self.private(await self.client.get(PATH+'avatar?token='+TOKEN,headers={routes.GRANT_HEADER:TOKEN}),400)
    self.service.authorize_asset.assert_not_called();self.assertEqual(self.upstream,[])

  async def test_logout_avatar_cursor_is_accepted_and_retained_path_is_cleared(self):
    self.service.session_cookie_paths.return_value=([PATH],None)
    response=await self.client.post('/private-media/session-replacement',headers={'Origin':ORIGIN},
      json={'transport':'browser','cursor':'avatar:'+VIDEO})
    self.private(response,200);self.assertIn('Path='+PATH,response.headers['set-cookie'])
    self.assertEqual(self.service.session_cookie_paths.call_args.args[1],'avatar:'+VIDEO)
