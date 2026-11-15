from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.services.analyzed_export_writes import (
  read_current_export, require_cached_export_object, write_analyzed_export,
)


USER='33333333-3333-3333-3333-333333333333'
VIDEO='11111111-1111-1111-1111-111111111111'
ANALYSIS='22222222-2222-2222-2222-222222222222'
ATTEMPT='77777777-7777-7777-7777-777777777777'
SOURCE=f'{USER}/playback/{VIDEO}.mp4'


def published_row(variant='pose'):
  now=datetime.now(timezone.utc)
  return dict(attempt_id=ATTEMPT,user_id=USER,video_id=VIDEO,purpose='analyzed_export',bucket='videos',
    storage_path=f'{USER}/exports/{VIDEO}-{ANALYSIS}-{variant}-{ATTEMPT}-h264-v1.mp4',source_path=SOURCE,
    content_type='video/mp4',size_bytes=9,job_id=None,worker_id=None,attempt_count=None,
    analysis_id=ANALYSIS,analysis_model_version='fixture',analysis_snapshot_hash='a'*64,variant=variant,
    state='succeeded',published_at=(now-timedelta(seconds=1)).isoformat(),
    cache_expires_at=(now+timedelta(hours=1)).isoformat())


class AnalyzedExportWriteTest(unittest.TestCase):
  def setUp(self):
    directory=TemporaryDirectory();self.addCleanup(directory.cleanup)
    self.output=Path(directory.name)/'synthetic.mp4';self.output.write_bytes(b'synthetic')
    self.storage=MagicMock();self.storage.bucket='videos'
    self.video=dict(id=VIDEO,user_id=USER,storage_path=f'{USER}/source/{VIDEO}.mov',playback_path=SOURCE)
    self.analysis=dict(id=ANALYSIS,model_version='fixture',result_json={'reps':2,'poseFrames':[]})
    self.events=[];self.row=None;self.rpc_error=None;self.upload_error=None
    self.admission=lambda row:[dict(row)]
    self.persisted=lambda row:[dict(row)]
    self.publish_response=lambda row:[dict(row)]
    self.observed=True
    self.settings=SimpleNamespace(export_cache_ttl_hours=24,max_user_reserved_bytes=300,object_storage_limit_bytes=500)
    settings=patch('app.services.analyzed_export_writes.get_settings',return_value=self.settings)
    settings.start();self.addCleanup(settings.stop)
    nonce=patch('app.services.analyzed_export_writes.uuid4',return_value=ATTEMPT)
    nonce.start();self.addCleanup(nonce.stop)
    def rpc(name,args):
      def execute():
        self.events.append(name)
        if self.rpc_error==name:raise TimeoutError('synthetic unknown response')
        if name=='admit_private_media_export_write':
          self.assertEqual(args['p_analysis_result'],self.analysis['result_json'])
          self.assertEqual(args['p_max_user_bytes'],300);self.assertEqual(args['p_max_global_bytes'],500)
          self.row=published_row(args['p_variant'])
          self.row.update(state='dispatching',published_at=None,cache_expires_at=None)
          return SimpleNamespace(data=self.admission(self.row))
        if name=='observe_private_media_generated_write_success':
          self.assertEqual(args['p_attempt_id'],ATTEMPT);self.assertEqual(args['p_purpose'],'analyzed_export')
          return SimpleNamespace(data=self.observed)
        self.assertEqual(name,'publish_private_media_export')
        self.assertEqual(args,dict(p_attempt_id=ATTEMPT,p_user_id=USER,p_cache_ttl_seconds=86400))
        row=published_row(self.row['variant']);self.row=dict(row)
        return SimpleNamespace(data=self.publish_response(row))
      return SimpleNamespace(execute=execute)
    self.storage.client.rpc.side_effect=rpc
    def readback():
      self.events.append('readback');return SimpleNamespace(data=self.persisted(self.row))
    self.storage.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect=readback
    def upload(*_args,**_kw):
      self.events.append('upload')
      if self.upload_error:raise self.upload_error
    self.storage.create_file.side_effect=upload

  def write(self,**changes):
    fields=dict(video=self.video,analysis=self.analysis,user_id=USER,variant='pose',output_path=self.output,storage=self.storage)
    fields.update(changes);return write_analyzed_export(**fields)

  def test_exact_committed_analysis_attempt_precedes_upload_observation_and_publication(self):
    path=self.write()
    self.assertEqual(path,published_row()['storage_path'])
    self.assertEqual(self.events,['admit_private_media_export_write','readback','upload',
                                  'observe_private_media_generated_write_success','publish_private_media_export','readback'])
    self.storage.create_file.assert_called_once_with(path,self.output,'video/mp4',cache_control='31536000')
    self.storage.upload_file.assert_not_called();self.storage.delete_storage_path.assert_not_called()
    self.assertEqual(self.storage.client.table.call_count,2)
    self.storage.client.table.assert_called_with('private_media_generated_writes')

  def test_missing_or_malformed_admission_never_dispatches(self):
    for transform in (lambda row:[],lambda row:None,lambda row:[row,row],lambda row:[{**row,'analysis_id':VIDEO}],
                      lambda row:[{**row,'analysis_snapshot_hash':'wrong'}],lambda row:[{**row,'state':'succeeded'}],
                      lambda row:[{**row,'unknown':'field'}]):
      with self.subTest(transform=transform):
        self.admission=transform
        with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_not_called();self.storage.client.table.assert_not_called()

  def test_missing_wrong_snapshot_or_bool_integer_readback_never_dispatches(self):
    for transform in (lambda row:[],lambda row:None,lambda row:[{**row,'size_bytes':True}],
                      lambda row:[{**row,'analysis_snapshot_hash':'b'*64}],
                      lambda row:[{**row,'source_path':SOURCE+'other'}]):
      with self.subTest(transform=transform):
        self.persisted=transform
        with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_not_called()

  def test_unknown_admission_never_reads_back_or_replays(self):
    self.rpc_error='admit_private_media_export_write'
    with self.assertRaises(HTTPException):self.write()
    self.assertEqual(self.events,['admit_private_media_export_write'])

  def test_unknown_upload_stays_pending_without_observation_publication_or_delete(self):
    self.upload_error=TimeoutError('unknown upload')
    with self.assertRaises(HTTPException):self.write()
    self.assertEqual(self.events,['admit_private_media_export_write','readback','upload'])
    self.storage.delete_storage_path.assert_not_called()

  def test_unknown_observation_never_publishes_or_replays_upload(self):
    self.rpc_error='observe_private_media_generated_write_success'
    with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_called_once()
    self.assertNotIn('publish_private_media_export',self.events)
    self.storage.delete_storage_path.assert_not_called()

  def test_unknown_publication_preserves_uploaded_bytes_for_later_cache_resolution(self):
    self.rpc_error='publish_private_media_export'
    with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_called_once();self.storage.delete_storage_path.assert_not_called()

  def test_uncommitted_or_uncertain_publication_never_returns_an_artifact(self):
    def not_committed(row):
      if row['state']=='succeeded':return [{**row,'published_at':None,'cache_expires_at':None}]
      return [row]
    self.persisted=not_committed
    with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_called_once();self.storage.delete_storage_path.assert_not_called()

  def test_falsy_truthy_or_missing_observation_cannot_authorize_publication(self):
    for value in (None,False,1,'true',[True],{}):
      self.observed=value
      with self.subTest(value=value),self.assertRaises(HTTPException):self.write()
    self.assertNotIn('publish_private_media_export',self.events)

  def test_mismatched_or_expired_publication_never_returns_an_artifact(self):
    for change in ({'analysis_snapshot_hash':'b'*64},{'attempt_id':VIDEO},{'cache_expires_at':'2000-01-01T00:00:00+00:00'},
                   {'published_at':None},{'variant':'barbell'},{'size_bytes':True}):
      self.publish_response=lambda row,change=change:[{**row,**change}]
      with self.subTest(change=change),self.assertRaises(HTTPException):self.write()
    self.storage.delete_storage_path.assert_not_called()

  def test_invalid_context_or_empty_output_fails_before_any_admission(self):
    for fields in ({'user_id':VIDEO},{'analysis':{**self.analysis,'model_version':None}},
                   {'analysis':{**self.analysis,'result_json':None}},{'variant':'clean'}):
      with self.subTest(fields=fields),self.assertRaises((ValueError,HTTPException)):self.write(**fields)
    self.output.write_bytes(b'')
    with self.assertRaises(ValueError):self.write()
    self.storage.client.rpc.assert_not_called()


class AnalyzedExportCacheTest(unittest.TestCase):
  def setUp(self):
    self.client=MagicMock();self.client.rpc.return_value.execute.return_value.data=[published_row()]

  def read(self):
    return read_current_export(self.client,user_id=USER,video_id=VIDEO,variant='pose',bucket='videos')

  def test_only_valid_current_publication_is_resolved(self):
    row=self.read();self.assertEqual(row['storage_path'],published_row()['storage_path'])
    self.client.rpc.assert_called_once_with('read_private_media_export',dict(p_user_id=USER,p_video_id=VIDEO,
      p_variant='pose',p_bucket='videos',p_analysis_id=None))

  def test_absent_publication_is_the_only_cache_miss(self):
    self.client.rpc.return_value.execute.return_value.data=[];self.assertIsNone(self.read())
    for data in (None,{},[None],[published_row(),published_row()]):
      with self.subTest(data=data),self.assertRaises(HTTPException):
        self.client.rpc.return_value.execute.return_value.data=data;self.read()

  def test_malformed_binding_key_state_hash_and_deadlines_fail_closed(self):
    for change in ({'user_id':VIDEO},{'video_id':USER},{'bucket':'another'},{'storage_path':SOURCE},
                   {'source_path':f'{VIDEO}/foreign.mp4'},{'variant':'barbell'},{'state':'dispatching'},
                   {'purpose':'playback'},{'analysis_snapshot_hash':'wrong'},{'job_id':VIDEO},
                   {'size_bytes':True},{'size_bytes':0},{'published_at':None},
                   {'cache_expires_at':'2000-01-01T00:00:00+00:00'}):
      with self.subTest(change=change),self.assertRaises(HTTPException):
        self.client.rpc.return_value.execute.return_value.data=[{**published_row(),**change}];self.read()

  def test_cache_rpc_error_is_not_a_miss(self):
    self.client.rpc.return_value.execute.side_effect=TimeoutError('unknown cache read')
    with self.assertRaises(HTTPException):self.read()
    self.client.rpc.assert_called_once()

  def test_cache_storage_error_including_object_not_found_never_becomes_a_miss(self):
    storage=MagicMock()
    for error in (TimeoutError('unknown'),HTTPException(404,'NoSuchKey'),HTTPException(403,'AccessDenied')):
      storage.get_object_info.side_effect=error
      with self.subTest(error=error),self.assertRaises(HTTPException):require_cached_export_object(storage,published_row())
    storage.create_file.assert_not_called()

  def test_cache_object_size_must_match_admitted_generation(self):
    storage=MagicMock()
    for info in ({},{'size':True},{'size':8},None):
      storage.get_object_info.return_value=info
      with self.subTest(info=info),self.assertRaises(HTTPException):require_cached_export_object(storage,published_row())
    storage.get_object_info.return_value={'metadata':{'size':'9'}}
    require_cached_export_object(storage,published_row())
