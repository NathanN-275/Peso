from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.routes import profile
from app.services.auth import VerifiedAuthContext, get_current_auth_context
from app.services.avatar_writes import MAX_AVATAR_BYTES


OWNER='33333333-3333-3333-3333-333333333333'
SESSION='44444444-4444-4444-4444-444444444444'
REVISION='55555555-5555-5555-5555-555555555555'
ATTEMPT='77777777-7777-7777-7777-777777777777'


class ProfileRoutesTests(unittest.TestCase):
  def setUp(self):
    self.app=FastAPI();self.app.include_router(profile.router)
    self.context=VerifiedAuthContext(OWNER,SESSION,2**31)
    self.auth_calls=0
    def authenticate():self.auth_calls+=1;return self.context
    self.app.dependency_overrides[get_current_auth_context]=authenticate
    self.client=TestClient(self.app)
    self.settings=SimpleNamespace(private_media_enabled=True,upload_storage_provider='supabase',upload_reservations_enabled=True)
    for name,kwargs in (
      ('get_settings',{'return_value':self.settings}),('get_supabase_admin_client',{}),('StorageService',{}),
      ('normalize_avatar',{'return_value':b'normalized'}),('write_avatar',{'return_value':{'attempt_id':ATTEMPT,'avatar_path':f'{OWNER}/avatar-{ATTEMPT}.jpg'}}),
      ('read_profile',{'return_value':None}),('save_profile',{'return_value':{'profile_revision':REVISION}}),
      ('publish_avatar',{'return_value':{'profile_revision':REVISION}})):
      p=patch.object(profile,name,**kwargs);setattr(self,name,p.start());self.addCleanup(p.stop)

  def upload(self,body=b'raw',headers=None):
    return self.client.post('/profile/avatar',content=body,headers=headers or {'Content-Type':'image/jpeg','X-Peso-Profile-Revision':REVISION})

  def test_all_endpoints_use_verified_owner_and_session_dependency(self):
    self.assertEqual(self.client.get('/profile').json(),{'profile':None})
    self.assertEqual(self.client.put('/profile',json={'profile_revision':None,'username':None,'display_name':None}).status_code,200)
    self.assertEqual(self.upload().status_code,200)
    self.assertEqual(self.client.post(f'/profile/avatar/{ATTEMPT}/publish',json={'username':None,'display_name':None}).status_code,200)
    self.assertEqual(self.auth_calls,4)
    self.assertEqual(self.write_avatar.call_args.kwargs['context'],self.context)
    self.assertEqual(self.publish_avatar.call_args.kwargs['context'],self.context)

  def test_authentication_failure_blocks_all_endpoint_work(self):
    def unauthorized():raise HTTPException(401,'Invalid bearer token.')
    self.app.dependency_overrides[get_current_auth_context]=unauthorized
    for method,path,kwargs in [('get','/profile',{}),('put','/profile',{'json':{'profile_revision':None,'username':None,'display_name':None}}),
      ('post','/profile/avatar',{'content':b'x'}),('post',f'/profile/avatar/{ATTEMPT}/publish',{'json':{'username':None,'display_name':None}})]:
      self.assertEqual(getattr(self.client,method)(path,**kwargs).status_code,401)
    self.read_profile.assert_not_called();self.write_avatar.assert_not_called();self.save_profile.assert_not_called();self.publish_avatar.assert_not_called()

  def test_disabled_private_media_and_wrong_provider_fail_closed(self):
    for flag,provider in ((False,'supabase'),(True,'azure')):
      self.settings.private_media_enabled=flag;self.settings.upload_storage_provider=provider
      self.assertEqual(self.client.get('/profile').status_code,503)
      self.assertEqual(self.upload().status_code,503)
    self.write_avatar.assert_not_called();self.read_profile.assert_not_called()

  def test_strict_json_bodies_and_query_parameters(self):
    for body in ({'profile_revision':None,'username':12,'display_name':None},
      {'profile_revision':None,'username':None,'display_name':None,'avatar_path':'unsafe'},
      {'username':None,'display_name':None}):
      self.assertEqual(self.client.put('/profile',json=body).status_code,422)
    self.assertEqual(self.client.post(f'/profile/avatar/{ATTEMPT}/publish',json={'username':None,'display_name':None,'profile_revision':REVISION}).status_code,422)
    self.assertEqual(self.client.get('/profile?user_id=other').status_code,400)
    self.save_profile.assert_not_called();self.publish_avatar.assert_not_called()

  def test_upload_requires_revision_exact_mime_nonempty_body_and_bounded_stream(self):
    for headers in ({'Content-Type':'image/jpeg'}, {'Content-Type':'image/jpeg','X-Peso-Profile-Revision':'null'},
      {'Content-Type':'image/svg+xml','X-Peso-Profile-Revision':REVISION},
      {'Content-Type':'image/jpeg; charset=utf-8','X-Peso-Profile-Revision':REVISION}):
      self.assertEqual(self.upload(headers=headers).status_code,400)
    self.assertEqual(self.upload(b'').status_code,400)
    self.assertEqual(self.upload(b'x'*(MAX_AVATAR_BYTES+1)).status_code,413)
    self.assertEqual(self.upload(b'x'*(MAX_AVATAR_BYTES+1),{'Content-Type':'image/jpeg','X-Peso-Profile-Revision':REVISION,'Content-Length':'1'}).status_code,413)
    self.assertEqual(self.upload(iter([b'x'*MAX_AVATAR_BYTES,b'x'])).status_code,413)
    self.assertEqual(self.upload(b'raw',{'Content-Type':'image/jpeg','X-Peso-Profile-Revision':REVISION,'Content-Length':'9'*5000}).status_code,413)
    self.normalize_avatar.assert_not_called();self.write_avatar.assert_not_called()

  def test_absent_revision_upload_response_is_metadata_only_and_post_normalization(self):
    response=self.upload(headers={'Content-Type':'image/png','X-Peso-Profile-Revision':'absent'})
    self.assertEqual(response.status_code,200)
    self.assertEqual(set(response.json()),{'attempt_id','avatar_path'})
    self.normalize_avatar.assert_called_once_with(b'raw','image/png')
    self.assertIsNone(self.write_avatar.call_args.kwargs['revision'])
    self.assertEqual(self.write_avatar.call_args.args,(b'normalized',))
    self.StorageService.assert_called_once_with(bucket='profile-avatars')

  def test_normalizer_failure_and_upload_pause_leave_api_alive(self):
    self.normalize_avatar.side_effect=HTTPException(400,'Avatar image could not be processed.')
    self.assertEqual(self.upload().status_code,400)
    self.assertEqual(self.client.get('/profile').status_code,200)
    self.settings.upload_reservations_enabled=False
    self.assertEqual(self.upload().status_code,503)
    self.write_avatar.assert_not_called()

  def test_authenticated_avatar_upload_does_not_require_location_headers(self):
    response = self.upload()
    self.assertEqual(response.status_code, 200)
    self.write_avatar.assert_called_once()
