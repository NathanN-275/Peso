from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import json
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.services.auth import VerifiedAuthContext
from app.services.avatar_writes import (LEDGER, MAX_AVATAR_BYTES, normalize_avatar, profile_fields,
  publish_avatar, read_profile, save_profile, write_avatar)

OWNER='33333333-3333-3333-3333-333333333333'
SESSION='44444444-4444-4444-4444-444444444444'
REVISION='55555555-5555-5555-5555-555555555555'
ATTEMPT='77777777-7777-7777-7777-777777777777'
NEXT='88888888-8888-8888-8888-888888888888'
CONTEXT=VerifiedAuthContext(OWNER,SESSION,2**31)


def timestamp(seconds):
  return (datetime.now(timezone.utc)-timedelta(seconds=seconds)).isoformat()


def profile(**values):
  return dict(id=OWNER,username='nathan',display_name='Nathan',avatar_path=None,
              created_at=timestamp(5),updated_at=timestamp(4),profile_revision=REVISION,**values)


class AvatarWriteTests(unittest.TestCase):
  def setUp(self):
    self.storage=MagicMock(); self.storage.bucket='profile-avatars'
    self.body=b'normalized jpeg fixture'
    self.storage.get_object_info.return_value={'metadata':{'size':len(self.body)}}
    self.settings=SimpleNamespace(max_user_reserved_bytes=300,object_storage_limit_bytes=500)
    self.events=[]; self.current=profile(); self.row=None; self.error=None
    self.admission=lambda row:deepcopy(row); self.persisted=lambda table,row:deepcopy(row)
    self.publication=lambda row:deepcopy(row); self.observed=True
    def rpc(name,args):
      def execute():
        self.events.append(name)
        self.assertEqual(args['p_user_id'],OWNER); self.assertEqual(args['p_session_id'],SESSION)
        if self.error==name:
          raise TimeoutError('sensitive backend context')
        if name=='read_private_media_profile':return SimpleNamespace(data=deepcopy(self.current))
        if name=='admit_private_media_avatar_write':
          self.assertEqual(set(args),{'p_attempt_id','p_user_id','p_session_id','p_profile_revision','p_size_bytes',
            'p_content_sha256','p_max_user_bytes','p_max_global_bytes'})
          self.row={key[2:]:value for key,value in args.items()}
          self.row.update(provider='supabase',bucket='profile-avatars',storage_path=f'{OWNER}/avatar-{args["p_attempt_id"]}.jpg',
            content_type='image/jpeg',previous_avatar_path=self.current['avatar_path'] if self.current else None,
            state='dispatching',created_at=timestamp(3),observed_at=None,published_at=None,
            published_username=None,published_display_name=None)
          return SimpleNamespace(data=self.admission(self.row))
        if name=='observe_private_media_avatar_write_success':
          for key,value in args.items():self.assertEqual(value,self.row[key[2:]])
          self.row.update(state='succeeded',observed_at=timestamp(2))
          return SimpleNamespace(data=self.observed)
        if name=='save_private_media_profile':
          self.current.update(username=args['p_username'],display_name=args['p_display_name'],profile_revision=NEXT,updated_at=timestamp(1))
          return SimpleNamespace(data=self.publication(self.current))
        self.assertEqual(name,'publish_private_media_avatar')
        if self.row['published_at'] is None:
          self.row.update(published_at=timestamp(1),published_username=args['p_username'],published_display_name=args['p_display_name'])
          self.current.update(avatar_path=self.row['storage_path'],username=args['p_username'],display_name=args['p_display_name'],
                              profile_revision=NEXT,updated_at=timestamp(1))
        return SimpleNamespace(data=self.publication(self.current))
      return SimpleNamespace(execute=execute)
    self.storage.client.rpc.side_effect=rpc
    def table(name):
      query=MagicMock()
      def execute():
        self.events.append('readback:'+name)
        row=self.row if name=='private_media_avatar_writes' else self.current
        return SimpleNamespace(data=[self.persisted(name,row)])
      query.select.return_value.eq.return_value.limit.return_value.execute.side_effect=execute
      return query
    self.storage.client.table.side_effect=table
    def create(path,local,*args,**kwargs):
      self.assertEqual(Path(local).read_bytes(),self.body);self.events.append('create')
    self.storage.create_file.side_effect=create
    self.uuid=patch('app.services.avatar_writes.uuid4',return_value=ATTEMPT);self.uuid.start();self.addCleanup(self.uuid.stop)

  def write(self,revision=REVISION):
    return write_avatar(self.body,revision=revision,context=CONTEXT,storage=self.storage,settings=self.settings)

  def publish(self,username=' Nathan ',display_name=' Nathan '):
    return publish_avatar(ATTEMPT,context=CONTEXT,username=username,display_name=display_name,storage=self.storage)

  def no_compensation(self):
    self.storage.upload_file.assert_not_called();self.storage.delete_storage_path.assert_not_called()

  def test_exact_typed_admission_and_independent_readback_before_one_create(self):
    self.assertEqual(self.write(),{'attempt_id':ATTEMPT,'avatar_path':f'{OWNER}/avatar-{ATTEMPT}.jpg'})
    self.assertEqual(self.events,['read_private_media_profile','admit_private_media_avatar_write',
      'readback:private_media_avatar_writes','create','observe_private_media_avatar_write_success'])
    self.assertEqual(self.row['content_sha256'],hashlib.sha256(self.body).hexdigest())
    self.storage.create_file.assert_called_once();self.no_compensation()

  def test_all_admission_identity_fields_and_scalar_types_are_exact(self):
    changes={'attempt_id':NEXT,'user_id':SESSION,'session_id':OWNER,'provider':'azure','bucket':'videos',
      'storage_path':f'{OWNER}/other.jpg','content_type':'image/png','size_bytes':True,'content_sha256':'b'*64,
      'profile_revision':NEXT,'previous_avatar_path':f'{OWNER}/unexpected.jpg','max_user_bytes':300.0,
      'max_global_bytes':True,'state':'succeeded','created_at':'tomorrow','observed_at':timestamp(2),
      'published_at':timestamp(1),'published_username':'nathan','published_display_name':'Nathan'}
    for key,value in changes.items():
      with self.subTest(key=key):
        self.admission=lambda row,key=key,value=value:{**row,key:value}
        with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_not_called();self.no_compensation()

  def test_incomplete_extra_and_nonobject_admission_never_dispatch(self):
    for transform in (lambda row:None,lambda row:[row],lambda row:{**row,'extra':True},
                      lambda row:{key:value for key,value in row.items() if key!='published_at'}):
      self.admission=transform
      with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_not_called()

  def test_readback_mismatch_and_failure_never_dispatch(self):
    for value in (True,300.0,0):
      self.persisted=lambda table,row,value=value:{**row,'max_user_bytes':value}
      with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_not_called();self.no_compensation()

  def test_stale_revision_and_absent_profile_binding_precede_admission(self):
    with self.assertRaises(HTTPException) as error:self.write(NEXT)
    self.assertEqual(error.exception.status_code,409)
    self.assertEqual(self.events,['read_private_media_profile'])
    self.current=None
    self.assertEqual(self.write(None)['attempt_id'],ATTEMPT)
    self.assertIsNone(self.row['profile_revision']);self.assertIsNone(self.row['previous_avatar_path'])

  def test_uncertain_admission_dispatch_and_observer_are_never_replayed_or_compensated(self):
    for name in ('admit_private_media_avatar_write','observe_private_media_avatar_write_success'):
      self.error=name
      with self.assertRaises(HTTPException) as error:self.write()
      self.assertNotIn('sensitive',error.exception.detail)
    self.error=None;self.storage.create_file.side_effect=TimeoutError('sensitive')
    with self.assertRaises(HTTPException):self.write()
    self.assertEqual(self.storage.create_file.call_count,2);self.no_compensation()

  def test_observation_requires_literal_true_and_exact_metadata_size(self):
    for value in (1,'true',False,None):
      self.observed=value
      with self.assertRaises(HTTPException):self.write()
    self.observed=True
    for size in (True,len(self.body)+1,None,1.0):
      self.storage.get_object_info.return_value={'metadata':{'size':size}}
      with self.assertRaises(HTTPException):self.write()
    self.no_compensation()

  def test_publication_full_profile_and_committed_profile_ledger_readback(self):
    self.write();self.events=[]
    result=self.publish()
    self.assertEqual(result['profile_revision'],NEXT);self.assertEqual(result['username'],'nathan')
    self.assertEqual(self.events,['readback:private_media_avatar_writes','publish_private_media_avatar',
      'readback:private_media_avatar_writes','readback:profiles'])
    self.assertEqual(self.publish(),result);self.storage.create_file.assert_called_once();self.no_compensation()

  def test_publication_context_and_malformed_ledger_never_mutate(self):
    for field,value in (('user_id',SESSION),('session_id',OWNER),('size_bytes',True),('state','dispatching'),
                        ('content_sha256','broken'),('profile_revision','bad')):
      self.write();self.row[field]=value;self.events=[]
      with self.assertRaises(HTTPException):self.publish()
      self.assertEqual(self.events,['readback:private_media_avatar_writes'])
    self.no_compensation()

  def test_publication_bad_response_or_persisted_profile_is_failure(self):
    self.write();self.publication=lambda row:{**row,'avatar_path':f'{OWNER}/wrong.jpg'}
    with self.assertRaises(HTTPException):self.publish()
    self.publication=lambda row:deepcopy(row)
    self.persisted=lambda table,row:{**row,'username':'wrong'} if table=='profiles' else deepcopy(row)
    with self.assertRaises(HTTPException):self.publish()
    self.no_compensation()

  def test_lost_publication_response_can_retry_same_attempt_and_body(self):
    self.write();real=self.publication
    def lost(row):raise TimeoutError('sensitive')
    self.publication=lost
    with self.assertRaises(HTTPException):self.publish()
    self.publication=real
    self.assertEqual(self.publish()['avatar_path'],self.row['storage_path'])
    with self.assertRaises(HTTPException) as error:self.publish('different','Nathan')
    self.assertEqual(error.exception.status_code,409);self.storage.create_file.assert_called_once()

  def test_profile_read_and_save_normalize_and_require_committed_full_receipt(self):
    self.assertEqual(read_profile(self.storage.client,CONTEXT),self.current)
    result=save_profile(self.storage.client,CONTEXT,REVISION,' Nathan ',' Nathan ')
    self.assertEqual((result['username'],result['display_name']),('nathan','Nathan'))
    self.assertEqual(profile_fields('  ',' '),(None,None))
    for values in (('ab','Nathan'),('nathan!','Nathan'),('nathan','x'*81),(True,'Nathan')):
      with self.assertRaises(HTTPException):profile_fields(*values)

  def test_read_rejects_wrong_owner_malformed_types_and_nonnull_empty_receipts(self):
    original=deepcopy(self.current)
    for field,value in (('id',SESSION),('profile_revision','bad'),('username',True),('display_name',True),
                        ('avatar_path',True),('created_at',True),('updated_at','tomorrow')):
      with self.subTest(field=field):
        self.current={**original,field:value}
        with self.assertRaises(HTTPException) as error:read_profile(self.storage.client,CONTEXT)
        self.assertEqual(error.exception.status_code,503)
    for value in ({},[],False):
      self.current=value
      with self.assertRaises(HTTPException):read_profile(self.storage.client,CONTEXT)
    self.current=None;self.assertIsNone(read_profile(self.storage.client,CONTEXT))


class AvatarNormalizerDiagnosticTests(unittest.TestCase):
  def test_failures_log_only_fixed_reason_and_numeric_process_facts(self):
    from app.services import avatar_writes
    from app.services.security_logging import SecurityJsonFormatter
    secret = 'synthetic-private-input-token-path-and-child-stderr'
    timeout = subprocess.TimeoutExpired(secret, 8, output=secret.encode(), stderr=secret.encode())
    cases = [
      ('spawn_error', OSError(11, secret), None, b'', 503),
      ('deadline', timeout, -9, b'', 400),
      ('communicate_error', RuntimeError(secret), -9, b'', 400),
      ('child_exit', None, 17, secret.encode(), 400),
      ('child_exit', None, secret, secret.encode(), 400),
      ('child_exit', None, 2**80, b'', 400),
      ('output_bounds', None, 0, b'', 400),
      ('output_bounds', None, 0, b'x' * (MAX_AVATAR_BYTES + 1), 400),
      ('output_bounds', None, 0, b'x' * (MAX_AVATAR_BYTES + 33), 400),
      ('jpeg_shape', None, 0, secret.encode(), 400),
    ]
    for reason, error, code, data, status in cases:
      with self.subTest(reason=reason, output_size=len(data)):
        child = MagicMock(returncode=code)
        child.communicate.side_effect = error if reason in {'deadline', 'communicate_error'} else None
        def spawn(*args, **kwargs):
          self.assertIs(kwargs['stderr'], subprocess.DEVNULL)
          if reason == 'spawn_error': raise error
          kwargs['stdout'].write(data)
          return child
        with patch.object(avatar_writes.subprocess, 'Popen', side_effect=spawn), \
             patch('time.monotonic', side_effect=[10, 10.125]), \
             self.assertLogs('app.services.avatar_writes', level='WARNING') as captured:
          with self.assertRaises(HTTPException) as failure:
            normalize_avatar(secret.encode(), 'image/jpeg')
        self.assertEqual(failure.exception.status_code, status)
        self.assertEqual(failure.exception.detail, 'Profile service is temporarily unavailable.' if status == 503
                         else 'Avatar image could not be processed.')
        self.assertEqual(len(captured.records), 1)
        record = captured.records[0]
        self.assertIsNone(record.exc_info)
        payload = json.loads(SecurityJsonFormatter().format(record))
        count = None if reason == 'spawn_error' else min(len(data), MAX_AVATAR_BYTES + 1)
        safe_code = code if type(code) is int and -(2**31) <= code < 2**31 else None
        self.assertEqual(payload['message'],
          f'Avatar normalization failed event=avatar_normalization_failure reason={reason} '
          f'child_returncode={safe_code} output_bytes={count} elapsed_ms=125')
        self.assertNotIn(secret, json.dumps(payload))
        if reason in {'deadline', 'communicate_error'}:
          child.kill.assert_called_once(); child.wait.assert_called_once()
        self.assertTrue(avatar_writes._normalization_slots.acquire(blocking=False))
        avatar_writes._normalization_slots.release()

  def test_success_emits_no_failure_event(self):
    from app.services import avatar_writes
    result = b'\xff\xd8\xff\x00\xff\xd9'
    def spawn(*args, **kwargs):
      kwargs['stdout'].write(result)
      return MagicMock(returncode=0)
    with patch.object(avatar_writes.subprocess, 'Popen', side_effect=spawn), \
         self.assertNoLogs('app.services.avatar_writes', level='WARNING'):
      self.assertEqual(normalize_avatar(b'synthetic input', 'image/jpeg'), result)


@unittest.skipUnless(sys.platform.startswith('linux'),'The normalizer intentionally requires Linux resource limits.')
@unittest.skipIf(os.environ.get('PESO_SKIP_AVATAR_NORMALIZER_TESTS') == 'true',
  'Avatar normalizer tests run against the pinned MVP runtime in container-security.')
class AvatarNormalizerTests(unittest.TestCase):
  def encoded(self,extension):
    import cv2
    import numpy as np
    success,data=cv2.imencode(extension,np.full((600,900,3),127,dtype=np.uint8))
    self.assertTrue(success)
    return data.tobytes()

  def test_actual_jpeg_png_webp_produce_one_bounded_jpeg(self):
    import cv2
    import numpy as np
    for extension,mime in (('.jpg','image/jpeg'),('.png','image/png'),('.webp','image/webp')):
      with self.subTest(extension=extension):
        result=normalize_avatar(self.encoded(extension),mime)
        decoded=cv2.imdecode(np.frombuffer(result,dtype=np.uint8),cv2.IMREAD_COLOR)
        self.assertLessEqual(max(decoded.shape[:2]),512)
        self.assertLessEqual(len(result),MAX_AVATAR_BYTES)

  def test_bad_oversize_wrong_codec_and_resource_failure_leave_slot_usable(self):
    cases=[(b'bad','image/jpeg'),(b'x'*(MAX_AVATAR_BYTES+1),'image/jpeg'),
           (self.encoded('.png'),'image/jpeg')]
    # This small PNG advertises dimensions requiring more than the child allocation limit.
    import struct,zlib
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    huge=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',100000,100000,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00'))+chunk(b'IEND',b'')
    cases.append((huge,'image/png'))
    for body,mime in cases:
      with self.subTest(mime=mime,size=len(body)):
        with self.assertRaises(HTTPException):normalize_avatar(body,mime)
        self.assertTrue(normalize_avatar(self.encoded('.jpg'),'image/jpeg').startswith(b'\xff\xd8'))

  def test_worker_has_fixed_hard_resource_limits_and_credentials_are_not_inherited(self):
    from app.services import avatar_writes
    real=subprocess.Popen
    seen=[]
    def spawn(*args,**kwargs):seen.append(kwargs);return real(*args,**kwargs)
    with patch.dict(os.environ, {'SUPABASE_SERVICE_ROLE_KEY': 'synthetic-must-not-be-inherited',
      'MALLOC_ARENA_MAX': '8', 'GLIBC_TUNABLES': 'glibc.malloc.arena_max=8'}), patch.object(
      avatar_writes.subprocess,'Popen',side_effect=spawn,
    ):
      normalize_avatar(self.encoded('.jpg'),'image/jpeg')
    self.assertEqual(seen[0]['env'], {'PATH': os.defpath, 'MALLOC_ARENA_MAX': '1'})
    worker=Path(avatar_writes.__file__).with_name('avatar_image_worker.py').read_text()
    self.assertIn('256 * 1024 * 1024',worker);self.assertIn('(2, 3)',worker)
    self.assertIn('RLIMIT_FSIZE',worker);self.assertIn("'-threads', '1'",worker)

  def test_timeout_holds_slot_until_child_is_reaped_and_next_image_succeeds(self):
    from app.services import avatar_writes
    child=MagicMock();child.communicate.side_effect=subprocess.TimeoutExpired('worker',8)
    def wait():
      self.assertFalse(avatar_writes._normalization_slots.acquire(blocking=False))
      return -9
    child.wait.side_effect=wait
    with patch.object(avatar_writes.subprocess,'Popen',return_value=child):
      with self.assertRaises(HTTPException):normalize_avatar(b'fixture','image/jpeg')
    child.kill.assert_called_once();child.wait.assert_called_once()
    self.assertTrue(normalize_avatar(self.encoded('.jpg'),'image/jpeg').endswith(b'\xff\xd9'))

  def test_one_process_slot_and_input_metadata_are_not_propagated(self):
    from app.services import avatar_writes
    self.assertTrue(avatar_writes._normalization_slots.acquire(blocking=False))
    try:
      with self.assertRaises(HTTPException) as error:normalize_avatar(b'fixture','image/jpeg')
      self.assertEqual(error.exception.status_code,429)
    finally:
      avatar_writes._normalization_slots.release()
    jpeg=self.encoded('.jpg');secret=b'Exif\x00\x00private-avatar-metadata'
    import struct
    tagged=jpeg[:2]+b'\xff\xe1'+struct.pack('>H',len(secret)+2)+secret+jpeg[2:]
    result=normalize_avatar(tagged,'image/jpeg')
    self.assertNotIn(secret,result);self.assertNotIn(b'Exif',result);self.assertNotIn(b'Lavc',result)
