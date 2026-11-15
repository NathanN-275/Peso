from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID
import unittest
from unittest.mock import ANY

from fastapi import HTTPException

from app.routes import private_media as routes
from app.services.private_media import IssuedMediaGrant, VIDEO_ASSETS
import test_private_media_routes as route_fixture
import test_private_media_service as service_fixture
from test_private_media_routes import OWNER, SESSION, VIDEO, ORIGIN, API, TOKEN, DATA

NIL = '00000000-0000-0000-0000-000000000000'
OTHER_SESSION = '00000000-0000-0000-0000-000000000004'
LEGACY = f'/private-media/video/{VIDEO}/'
PATH = f'/private-media/session/{SESSION}/video/{VIDEO}/'


def row(kind='video', resource=VIDEO, session=SESSION):
  return dict(resource_kind=kind, resource_id=resource, cookie_session_id=session)


class BrowserMediaServiceTest(unittest.TestCase):
  setUp = service_fixture.PrivateMediaServiceTest.setUp

  def test_browser_session_binding_denies_all_kinds_before_metadata_or_signing(self):
    for kind, asset in [('video','playback'),('archive','archive'),('avatar','avatar')]:
      self.db.rpc_rows = [dict(user_id=OWNER, session_id=OTHER_SESSION, resource_kind=kind,
                              resource_id=VIDEO, expires_at=service_fixture.future())]
      with self.subTest(kind=kind), self.assertRaises(HTTPException) as failure:
        self.service.authorize_asset(TOKEN, kind, VIDEO, asset, expected_session_id=SESSION)
      self.assertEqual(failure.exception.status_code, 403)
    self.factory.assert_not_called()
    self.assertTrue(all(call[0] != 'table' for call in self.db.calls))
    for value in [NIL, 'invalid', SESSION.upper().replace('00000000','ABCDEF00',1)]:
      before = len(self.db.calls)
      with self.subTest(value=value), self.assertRaises(HTTPException):
        self.service.authorize_asset(TOKEN, 'video', VIDEO, 'playback', expected_session_id=value)
      self.assertEqual(len(self.db.calls), before)

  def test_matching_session_uses_existing_byte_authorization_and_native_has_no_extra_selector(self):
    result = self.service.authorize_asset(TOKEN, 'video', VIDEO, 'playback', expected_session_id=SESSION)
    self.assertEqual(result.owner_id, OWNER)
    self.assertEqual(self.db.calls[0][0], 'authorize_private_media_grant')
    self.assertNotIn('p_session_id', self.db.calls[0][1])
    self.assertEqual(self.factory.call_count, 1)
    self.service.authorize_asset(TOKEN, 'video', VIDEO, 'playback')
    self.assertEqual(self.factory.call_count, 2)

  def test_v2_inventory_binds_owner_scope_and_maps_only_legacy_sentinel_or_exact_session(self):
    self.db.rpc_rows = [row(session=NIL), row()]
    paths, cursor = self.service.session_cookie_paths_v2(self.context, None)
    self.assertEqual((paths,cursor), ([LEGACY, PATH],None))
    self.assertEqual(self.db.calls[0], ('private_media_session_cookie_paths_v2', {
      'p_user_id': OWNER, 'p_session_id': SESSION, 'p_after_kind':None,
      'p_after_id':None, 'p_after_session_id':None}))
    self.db.rpc_rows = [row(session=OTHER_SESSION)]
    with self.assertRaises(HTTPException): self.service.session_cookie_paths_v2(self.context,None)
    paths, _ = self.service.session_cookie_paths_v2(self.context,None,all_sessions=True)
    self.assertEqual(paths,[f'/private-media/session/{OTHER_SESSION}/video/{VIDEO}/'])
    self.assertIsNone(self.db.calls[-1][1]['p_session_id'])

  def test_inventory_page_continues_exact_kind_resource_session_tuple(self):
    self.db.rpc_rows = [row(resource=str(UUID(int=i+1)),session=NIL) for i in range(17)]
    paths, cursor = self.service.session_cookie_paths_v2(self.context,None)
    self.assertEqual(len(paths),16)
    self.assertEqual(cursor, f'video:{UUID(int=16)}:{NIL}')
    self.db.rpc_rows = [row(resource=str(UUID(int=17)),session=NIL)]
    final, continuation = self.service.session_cookie_paths_v2(self.context,cursor)
    self.assertEqual(final,[f'/private-media/video/{UUID(int=17)}/']);self.assertIsNone(continuation)
    self.assertEqual(self.db.calls[-1][1]['p_after_session_id'],NIL)
    self.assertEqual(self.db.calls[-1][1]['p_after_id'],str(UUID(int=16)))
    for cursor in [f'video:{VIDEO}', f'video:{NIL}:{SESSION}', f'Video:{VIDEO}:{SESSION}',
                   f'video:{VIDEO}:bad', f'video:{VIDEO}:{SESSION}:extra', 12]:
      with self.subTest(cursor=cursor), self.assertRaises(HTTPException):
        self.service.session_cookie_paths_v2(self.context,cursor)

  def test_malformed_unordered_duplicate_and_regressive_inventory_never_returns_paths(self):
    cases = [[row(),row()], [row(),row(session=NIL)], [row(resource=NIL)],
             [row(session='invalid')], [{**row(),'owner_id':OWNER}],
             [{key:value for key,value in row().items() if key!='cookie_session_id'}],
             [row(session=None)], [row(kind='owner')], [row()] * 18]
    for rows in cases:
      self.db.rpc_rows=rows
      with self.subTest(rows=rows), self.assertRaises(HTTPException) as failure:
        self.service.session_cookie_paths_v2(self.context,None)
      self.assertEqual(failure.exception.status_code,503)
    self.db.rpc_rows=[row()]
    with self.assertRaises(HTTPException):
      self.service.session_cookie_paths_v2(self.context,f'video:{VIDEO}:{SESSION}')
    self.factory.assert_not_called()


class BrowserMediaRoutesTest(unittest.IsolatedAsyncioTestCase):
  asyncSetUp = route_fixture.PrivateMediaRoutesTest.asyncSetUp
  asyncTearDown = route_fixture.PrivateMediaRoutesTest.asyncTearDown
  private = route_fixture.PrivateMediaRoutesTest.private

  async def issue(self, session=SESSION, kind='video', assets=None, transport='browser', headers=None):
    return await self.client.post(f'/private-media/session/{session}/{kind}/{VIDEO}/session',
      headers={'Origin':ORIGIN} if headers is None else headers,
      json={'transport':transport,'asset_kinds':assets or ['playback']})

  async def test_browser_video_cookie_has_fixed_all_six_existing_assets_and_no_account_or_media_json_credential(self):
    for requested in [['thumbnail'],['playback'],['export:pose'],sorted(VIDEO_ASSETS)]:
      response=await self.issue(assets=requested);self.private(response,200)
      self.assertEqual(set(response.json()['urls']),VIDEO_ASSETS)
      self.assertEqual(response.json()['urls'],{asset:API+PATH+asset.replace(':','%3A') for asset in VIDEO_ASSETS})
      self.assertEqual(self.service.issue.call_args.args[3],sorted(VIDEO_ASSETS))
      self.assertEqual(set(response.json()),{'resource_kind','resource_id','urls','expires_in','expires_at'})
      self.assertNotIn(TOKEN,response.text)
      cookie=response.headers['set-cookie']
      for flag in ['Path='+PATH,'HttpOnly','Secure','SameSite=strict']:self.assertIn(flag,cookie)
      self.assertNotIn('Domain=',cookie)

  async def test_wrong_or_noncanonical_session_fails_before_issuer(self):
    for session,status in [(OTHER_SESSION,403),(NIL,400),('bad',400),('ABCDEF00-0000-0000-0000-000000000002',400)]:
      self.private(await self.issue(session=session),status)
    self.private(await self.issue(transport='native'),403)
    self.service.issue.assert_not_called()

  async def test_invalid_video_assets_never_issue_and_other_kinds_keep_one_asset(self):
    for assets in [['playback','playback'],['archive'],['unknown']]:
      self.private(await self.issue(assets=assets),400)
    self.service.issue.assert_not_called()
    for kind in ['avatar','archive']:
      response=await self.issue(kind=kind,assets=[kind]);self.private(response,200)
      self.assertEqual(set(response.json()['urls']),{kind})
      self.assertEqual(self.service.issue.call_args.args[3],[kind])

  async def test_old_browser_issue_and_bytes_fail_closed_but_native_issuance_unchanged(self):
    for kind,asset in [('video','playback'),('avatar','avatar'),('archive','archive')]:
      path=f'/private-media/{kind}/{VIDEO}/'
      self.private(await self.client.post(path+'session',headers={'Origin':ORIGIN},json={'transport':'browser','asset_kinds':[asset]}),409)
      self.private(await self.client.get(path+asset,headers={'Origin':ORIGIN,'Cookie':routes.COOKIE+'='+TOKEN}),409)
    self.service.issue.assert_not_called();self.service.authorize_asset.assert_not_called()
    response=await self.client.post(LEGACY+'session',json={'transport':'native','asset_kinds':['playback']})
    self.private(response,200);self.assertEqual(response.json()['media_grant'],TOKEN)
    self.assertEqual(set(response.json()['urls']),{'playback'});self.assertNotIn('set-cookie',response.headers)

  async def test_namespaced_get_head_range_bind_cookie_session_and_strip_upstream_credentials(self):
    await self.issue()
    for method,headers,expected in [('GET',{},200),('HEAD',{},200),('GET',{'Range':'bytes=3-19'},206)]:
      response=await self.client.request(method,PATH+'playback',headers={'Origin':ORIGIN,**headers})
      self.private(response,expected)
      self.assertEqual(self.service.authorize_asset.call_args.kwargs['expected_session_id'],SESSION)
    self.assertEqual(self.service.authorize_asset.call_count,3)
    for request in self.upstream:
      for header in ['authorization','cookie',routes.GRANT_HEADER]:self.assertNotIn(header,request.headers)

  async def test_browser_origin_host_credentials_and_query_guards_never_authorize(self):
    cases=[({},403),({'Origin':'https://evil.invalid'},403),({'Origin':ORIGIN},401),
      ({'Origin':ORIGIN,'Cookie':routes.COOKIE+'='+TOKEN,'Authorization':'Bearer synthetic'},401),
      ({'Origin':ORIGIN,routes.GRANT_HEADER:TOKEN},400)]
    for headers,status in cases:self.private(await self.client.get(PATH+'playback',headers=headers),status)
    self.private(await self.client.get('https://wrong.invalid'+PATH+'playback',headers={'Origin':ORIGIN,'Cookie':routes.COOKIE+'='+TOKEN,'X-Forwarded-Host':'api.usepeso.com'}),503)
    self.private(await self.client.get(PATH+'playback?token=synthetic',headers={'Origin':ORIGIN}),400)
    self.service.authorize_asset.assert_not_called();self.assertEqual(self.upstream,[])

  async def test_late_old_cookie_cannot_overwrite_new_session_resource_cookie(self):
    await self.issue()
    newer='B'*42+'A'
    self.app.dependency_overrides[route_fixture.get_current_auth_context]=lambda:route_fixture.VerifiedAuthContext(OWNER,OTHER_SESSION,2000000000)
    self.service.issue.return_value=IssuedMediaGrant(newer,datetime.now(timezone.utc)+timedelta(seconds=120))
    self.private(await self.issue(session=OTHER_SESSION),200)
    # Simulate OLD delayed headers AFTER new session issuance for the same owned video.
    self.client.cookies.set(routes.COOKIE,TOKEN,domain='api.usepeso.com',path=PATH)
    new_path=f'/private-media/session/{OTHER_SESSION}/video/{VIDEO}/'
    self.private(await self.client.get(new_path+'playback',headers={'Origin':ORIGIN}),200)
    self.assertEqual(self.service.authorize_asset.call_args.args[0],newer)
    self.assertEqual(self.service.authorize_asset.call_args.kwargs['expected_session_id'],OTHER_SESSION)
    self.service.authorize_asset.side_effect=HTTPException(403,'Private media unavailable.')
    self.private(await self.client.get(PATH+'playback',headers={'Origin':ORIGIN}),403)

  async def test_v2_cleanup_returns_versioned_receipt_and_expires_legacy_and_session_paths(self):
    for endpoint,scope in [('session-replacement','local'),('logout','global')]:
      self.service.session_cookie_paths_v2.return_value=([LEGACY,PATH],None)
      response=await self.client.post('/private-media/v2/'+endpoint,headers={'Origin':ORIGIN},json={'transport':'browser'})
      self.private(response,200);body=response.json()
      self.assertEqual(set(body),{'scope','completed_at','replayed','owner_id','session_id','next_cursor','cookie_cleanup_complete','cookie_inventory_version'})
      self.assertEqual(body['scope'],scope);self.assertEqual(body['cookie_inventory_version'],2)
      self.assertEqual((body['owner_id'],body['session_id']),(OWNER,SESSION))
      self.assertEqual(body['cookie_cleanup_complete'],True)
      self.service.session_cookie_paths_v2.assert_called_with(route_fixture.VerifiedAuthContext(OWNER,SESSION,2000000000),None,all_sessions=scope=='global')
      self.assertEqual(len(response.headers.get_list('set-cookie')),2)
      for header,path in zip(response.headers.get_list('set-cookie'),[LEGACY,PATH]):
        self.assertIn('Path='+path,header);self.assertIn('Max-Age=0',header)

  async def test_v2_cursor_continuation_and_full_header_page_are_bounded_and_exact(self):
    cursor=f'video:{VIDEO}:{SESSION}'
    paths=[f'/private-media/session/{UUID(int=i+1)}/archive/{VIDEO}/' for i in range(16)]
    self.service.session_cookie_paths_v2.return_value=(paths,cursor)
    first=await self.client.post('/private-media/v2/logout',headers={'Origin':ORIGIN},json={'transport':'browser'})
    self.private(first,200);self.assertFalse(first.json()['cookie_cleanup_complete'])
    self.assertEqual(len(first.headers.get_list('set-cookie')),16)
    header_bytes=sum(len(k)+len(v)+4 for k,v in first.headers.multi_items())
    self.assertLess(header_bytes,5120) # Local serialization bound; hosted proxy acceptance remains separate.
    self.service.session_cookie_paths_v2.return_value=([],None)
    final=await self.client.post('/private-media/v2/logout',headers={'Origin':ORIGIN},json={'transport':'browser','cursor':cursor})
    self.private(final,200);self.assertTrue(final.json()['cookie_cleanup_complete'])
    self.service.session_cookie_paths_v2.assert_called_with(route_fixture.VerifiedAuthContext(OWNER,SESSION,2000000000),cursor,all_sessions=True)

  async def test_v2_rejects_bad_cursors_native_and_unapproved_browser_without_revocation(self):
    for cursor in [f'video:{VIDEO}',f'video:{NIL}:{SESSION}',f'video:{VIDEO}:bad',f'Video:{VIDEO}:{SESSION}',f'video:{VIDEO}:{SESSION}:more']:
      self.private(await self.client.post('/private-media/v2/logout',headers={'Origin':ORIGIN},json={'transport':'browser','cursor':cursor}),422)
    self.private(await self.client.post('/private-media/v2/logout',json={'transport':'native'}),422)
    self.private(await self.client.post('/private-media/v2/logout',headers={'Origin':'https://evil.invalid'},json={'transport':'browser'}),403)
    self.private(await self.client.post('https://wrong.invalid/private-media/v2/logout',headers={'Origin':ORIGIN},json={'transport':'browser'}),503)
    self.service.revoke_global_session.assert_not_called();self.service.session_cookie_paths_v2.assert_not_called()

  async def test_legacy_nil_cursor_is_accepted_only_in_inventory_and_failures_stay_no_store(self):
    cursor=f'video:{VIDEO}:{NIL}'
    self.service.session_cookie_paths_v2.return_value=([],None)
    response=await self.client.post('/private-media/v2/session-replacement',headers={'Origin':ORIGIN},json={'transport':'browser','cursor':cursor})
    self.private(response,200)
    self.service.session_cookie_paths_v2.side_effect=RuntimeError('synthetic-private-inventory')
    failure=await self.client.post('/private-media/v2/session-replacement',headers={'Origin':ORIGIN},json={'transport':'browser'})
    self.private(failure,503);self.assertNotIn('synthetic-private-inventory',failure.text)


class BrowserMediaDownloadRoutesTest(unittest.IsolatedAsyncioTestCase):
  asyncSetUp = route_fixture.PrivateMediaRoutesTest.asyncSetUp
  asyncTearDown = route_fixture.PrivateMediaRoutesTest.asyncTearDown
  private = route_fixture.PrivateMediaRoutesTest.private

  def navigation(self):
    return {'Referer':ORIGIN+'/', 'Sec-Fetch-Mode':'navigate', 'Sec-Fetch-Dest':'document',
            'Sec-Fetch-Site':'same-site', 'Sec-Fetch-User':'?1', 'Cookie':routes.COOKIE+'='+TOKEN}

  async def test_video_and_archive_download_use_fresh_authorization_and_attachment(self):
    for kind,asset,content_type,name in [('video','export%3Apose','video/mp4','lift.mp4'),
                                         ('archive','archive','application/zip','lifts.zip')]:
      self.service.authorize_asset.return_value = route_fixture.PrivateMediaAsset(
        url='https://storage.invalid/private/x?token=synthetic-storage-secret', owner_id=OWNER,
        size_bytes=len(DATA), content_type=content_type, download_name=name)
      url=f'/private-media/session/{SESSION}/{kind}/{VIDEO}/download/{asset}'
      response=await self.client.get(url,headers=self.navigation())
      self.private(response,200)
      self.assertEqual(response.content,DATA)
      self.assertEqual(response.headers['content-type'],content_type)
      self.assertIn(name,response.headers['content-disposition'])
      self.service.authorize_asset.assert_called_with(TOKEN,kind,VIDEO,asset.replace('%3A',':'),
        expected_session_id=SESSION,is_cancelled=ANY)
    self.assertEqual(self.service.authorize_asset.call_count,2)
    for upstream in self.upstream:
      for name in ['authorization','cookie',routes.GRANT_HEADER,'referer']:
        self.assertNotIn(name,upstream.headers)

  async def test_wrong_navigation_headers_and_duplicate_referrer_do_not_authorize(self):
    url=PATH+'download/export%3Aclean'
    for name,value in [('Referer','https://other.usepeso.com/'),('Referer',ORIGIN+'/app'),
      ('Sec-Fetch-Site','none'),('Sec-Fetch-Mode','cors'),('Sec-Fetch-Dest','iframe'),('Sec-Fetch-User','?0'),
      ('Origin',ORIGIN)]:
      with self.subTest(name=name,value=value):
        self.private(await self.client.get(url,headers={**self.navigation(),name:value}),403)
    for name in ['Referer','Sec-Fetch-Site','Sec-Fetch-Mode','Sec-Fetch-Dest','Sec-Fetch-User']:
      headers=self.navigation();del headers[name]
      self.private(await self.client.get(url,headers=headers),403)
    self.private(await self.client.get(url,headers=[*self.navigation().items(),('Referer',ORIGIN+'/')]),403)
    self.service.authorize_asset.assert_not_called()
    self.assertEqual(self.upstream,[])

  async def test_download_guard_denies_non_export_paths_and_ambiguous_credentials(self):
    h=self.navigation();url=PATH+'download/export%3Aclean'
    for asset in ['playback','thumbnail','export%3Aunknown','archive']:
      self.private(await self.client.get(PATH+'download/'+asset,headers=h),404)
    self.private(await self.client.get(PATH.replace('/video/','/archive/')+'download/export%3Aclean',headers=h),404)
    self.private(await self.client.get(url+'?token=synthetic',headers=h),400)
    self.private(await self.client.head(url,headers=h),405)
    self.private(await self.client.get(url,headers={**h,'Authorization':'Bearer synthetic'}),401)
    self.private(await self.client.get(url,headers={**h,routes.GRANT_HEADER:TOKEN}),400)
    self.private(await self.client.get(url,headers={k:v for k,v in h.items() if k!='Cookie'}),401)
    self.private(await self.client.get('https://other.usepeso.com'+url,headers={**h,'X-Forwarded-Host':'api.usepeso.com'}),503)
    self.private(await self.client.get(url.replace(SESSION,NIL),headers=h),400)
    self.private(await self.client.get(PATH+'export%3Aclean',headers=h),403)
    self.service.authorize_asset.assert_not_called()
    self.assertEqual(self.upstream,[])

  async def test_revoked_or_wrong_session_cookie_cannot_stream_download(self):
    self.service.authorize_asset.side_effect=HTTPException(403,'Private media unavailable.')
    self.private(await self.client.get(PATH+'download/export%3Aclean',headers=self.navigation()),403)
    self.assertEqual(self.service.authorize_asset.call_args.kwargs['expected_session_id'],SESSION)
    self.assertEqual(self.upstream,[])
