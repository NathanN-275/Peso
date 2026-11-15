from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.services.archive_writes import file_sha256, plan_archive, read_published_archive, write_archive

OWNER='33333333-3333-3333-3333-333333333333'
VIDEO='11111111-1111-1111-1111-111111111111'
JOB='55555555-5555-5555-5555-555555555555'
ATTEMPT='77777777-7777-7777-7777-777777777777'
ANALYSIS='22222222-2222-2222-2222-222222222222'


def archive_plan(owner=OWNER, job=JOB, video=VIDEO, analysis=ANALYSIS):
  return dict(user_id=owner,archive_job_id=job,archive_attempt_count=1,
    archive_started_at=(datetime.now(timezone.utc)-timedelta(seconds=3)).isoformat(),video_ids=[video],
    member_snapshots=[dict(video_id=video,source_path=f'{owner}/playback/{video}.mp4',analysis_id=analysis,
      analysis_model_version='fixture',analysis_snapshot_hash='a'*64,variant='clean',entry_name=f'01-squat-{video}.mp4')])


def published_archive(owner=OWNER,job=JOB,video=VIDEO,attempt=ATTEMPT):
  plan=archive_plan(owner,job,video)
  members=[{**m,'artifact_bucket':'videos','artifact_path':m['source_path'],
            'artifact_size_bytes':1,'artifact_sha256':'a'*64} for m in plan['member_snapshots']]
  return dict(**{**plan,'member_snapshots':members},attempt_id=attempt,purpose='archive',bucket='saved-lift-exports',
    storage_path=f'{owner}/{job}-{attempt}.zip',content_type='application/zip',size_bytes=10,content_sha256='b'*64,
    state='succeeded',created_at=(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat(),
    published_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),
    cache_expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())


class ArchiveWriteTest(unittest.TestCase):
  def setUp(self):
    temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup)
    self.output=Path(temporary.name)/'synthetic.zip';self.output.write_bytes(b'synthetic')
    self.storage=MagicMock();self.storage.bucket='saved-lift-exports'
    self.storage.get_object_info.return_value={'metadata':{'size':9}}
    self.plan=archive_plan();self.members=[{**m,'artifact_bucket':'videos','artifact_path':m['source_path'],
      'artifact_size_bytes':1,'artifact_sha256':'a'*64} for m in self.plan['member_snapshots']]
    self.settings=SimpleNamespace(export_cache_ttl_hours=1,max_user_reserved_bytes=300,object_storage_limit_bytes=500,
                                  max_saved_lift_export_bytes=1000)
    self.events=[];self.row=None;self.rpc_error=None;self.observed=True
    self.admission=lambda row:deepcopy(row);self.persisted=lambda row:[deepcopy(row)];self.publication=lambda row:deepcopy(row)
    def rpc(name,args):
      def execute():
        self.events.append(name)
        if self.rpc_error==name:raise TimeoutError('synthetic private context')
        if name=='plan_private_media_archive':return SimpleNamespace(data=self.plan)
        if name=='admit_private_media_archive_write':
          self.assertEqual(args['p_max_user_bytes'],300);self.assertEqual(args['p_max_global_bytes'],500)
          self.row={key[2:]:deepcopy(value) for key,value in args.items() if key not in {'p_max_user_bytes','p_max_global_bytes'}}
          self.row.update(purpose='archive',content_type='application/zip',state='dispatching',
            created_at=(datetime.now(timezone.utc)-timedelta(seconds=2)).isoformat(),published_at=None,cache_expires_at=None)
          return SimpleNamespace(data=self.admission(self.row))
        if name=='observe_private_media_generated_write_success':
          self.assertEqual(args['p_video_id'],None);self.assertEqual(args['p_source_path'],None)
          self.assertEqual(args['p_purpose'],'archive');return SimpleNamespace(data=self.observed)
        if name=='read_private_media_archive':return SimpleNamespace(data=self.row)
        self.assertEqual(name,'publish_private_media_archive')
        self.row.update(state='succeeded',published_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),
                        cache_expires_at=(datetime.fromisoformat(self.row['created_at'])+timedelta(seconds=args['p_cache_ttl_seconds'])).isoformat())
        return SimpleNamespace(data=self.publication(self.row))
      return SimpleNamespace(execute=execute)
    self.storage.client.rpc.side_effect=rpc
    def readback():
      self.events.append('readback');return SimpleNamespace(data=self.persisted(self.row))
    self.storage.client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.side_effect=readback
    self.storage.create_file.side_effect=lambda *_args,**_kwargs:self.events.append('create')

  def write(self):
    return write_archive(plan=self.plan,members=self.members,attempt_id=ATTEMPT,output_path=self.output,
                         storage=self.storage,settings=self.settings)

  def assert_no_compensation(self):
    self.storage.upload_file.assert_not_called();self.storage.delete_storage_path.assert_not_called()

  def test_exact_admission_and_readback_precede_single_create_then_observation_publication_readback(self):
    path=self.write();self.assertEqual(path,f'{OWNER}/{JOB}-{ATTEMPT}.zip')
    self.assertEqual(self.events,['admit_private_media_archive_write','readback','create',
      'observe_private_media_generated_write_success','publish_private_media_archive','readback'])
    self.storage.create_file.assert_called_once_with(path,self.output,'application/zip',cache_control='31536000')
    self.assertEqual(self.row['content_sha256'],file_sha256(self.output));self.assert_no_compensation()

  def test_missing_malformed_or_mismatched_admission_never_dispatches(self):
    for transform in (lambda row:None,lambda row:[],lambda row:[row],lambda row:{**row,'extra':1},
                      lambda row:{**row,'archive_job_id':VIDEO},lambda row:{**row,'size_bytes':True},
                      lambda row:{**row,'content_sha256':'wrong'},lambda row:{**row,'state':'succeeded'}):
      with self.subTest(transform=transform):
        self.admission=transform
        with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_not_called();self.assert_no_compensation()

  def test_nested_bool_float_and_missing_manifest_receipts_never_dispatch(self):
    for value in (True,1.0,0,None):
      def transform(row):
        result=deepcopy(row);result['member_snapshots'][0]['artifact_size_bytes']=value;return result
      with self.subTest(value=value):
        self.persisted=lambda row:[transform(row)]
        with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_not_called();self.assert_no_compensation()

  def test_lost_admission_or_committed_readback_response_never_dispatches(self):
    self.rpc_error='admit_private_media_archive_write'
    with self.assertRaises(HTTPException):self.write()
    self.rpc_error=None;self.persisted=lambda row:[]
    with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_not_called();self.assert_no_compensation()

  def test_uncertain_upload_is_not_replayed_or_compensated(self):
    self.storage.create_file.side_effect=TimeoutError('synthetic unknown upload')
    with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_called_once()
    self.assertNotIn('observe_private_media_generated_write_success',self.events);self.assert_no_compensation()

  def test_only_literal_true_observation_can_reach_metadata_and_publication(self):
    for observed in (None,False,1,'true',[],{}):
      with self.subTest(observed=observed):
        self.observed=observed
        with self.assertRaises(HTTPException):self.write()
    self.storage.get_object_info.assert_not_called();self.assertNotIn('publish_private_media_archive',self.events)
    self.assert_no_compensation()

  def test_metadata_not_found_and_permission_and_wrong_size_fail_after_observation_without_publication(self):
    for error in ('NoSuchKey','Forbidden',None):
      self.storage.get_object_info.side_effect=RuntimeError(error) if error else None
      self.storage.get_object_info.return_value={'size':8}
      with self.subTest(error=error),self.assertRaises(HTTPException):self.write()
    self.assertIn('observe_private_media_generated_write_success',self.events)
    self.assertNotIn('publish_private_media_archive',self.events);self.assert_no_compensation()

  def test_lost_publication_response_preserves_uploaded_bytes_without_returning_path(self):
    self.rpc_error='publish_private_media_archive'
    with self.assertRaises(HTTPException):self.write()
    self.storage.create_file.assert_called_once();self.assert_no_compensation()

  def test_mismatched_publication_or_final_readback_cannot_return_path(self):
    self.publication=lambda row:{**row,'storage_path':f'{OWNER}/wrong.zip'}
    with self.assertRaises(HTTPException):self.write()
    self.publication=lambda row:row
    self.persisted=lambda row:[] if row['state']=='succeeded' else [deepcopy(row)]
    with self.assertRaises(HTTPException):self.write()
    self.assert_no_compensation()

  def test_publication_cannot_extend_the_configured_lifetime(self):
    self.publication=lambda row:{**row,'cache_expires_at':(datetime.now(timezone.utc)+timedelta(days=2)).isoformat()}
    with self.assertRaises(HTTPException):self.write()
    self.assert_no_compensation()

  def test_bound_plan_checks_generation_selection_members_and_filename_before_storage(self):
    job=dict(id=JOB,user_id=OWNER,status='processing',attempts=1,started_at=self.plan['archive_started_at'],video_ids=[VIDEO])
    self.assertEqual(plan_archive(self.storage,job),self.plan)
    for update in ({'attempts':True},{'started_at':'bad'},{'video_ids':[]},{'status':'expired'}):
      with self.subTest(update=update),self.assertRaises(HTTPException):plan_archive(self.storage,{**job,**update})
    self.plan['member_snapshots'][0]['entry_name']='../../outside.mp4'
    with self.assertRaises(HTTPException):plan_archive(self.storage,job)
    self.storage.create_file.assert_not_called()

  def test_manifest_plan_cannot_change_before_write(self):
    self.members[0]['analysis_snapshot_hash']='c'*64
    with self.assertRaises(HTTPException):self.write()
    self.storage.client.rpc.assert_not_called();self.storage.create_file.assert_not_called()

  def test_published_read_requires_exact_owner_job_path_manifest_and_live_deadline(self):
    self.row=published_archive()
    self.assertEqual(read_published_archive(self.storage.client,user_id=OWNER,job_id=JOB,storage_path=self.row['storage_path']),self.row)
    for update in ({'user_id':VIDEO},{'archive_job_id':VIDEO},{'state':'dispatching'},{'cache_expires_at':'2000-01-01T00:00:00+00:00'},
                   {'video_ids':[VIDEO,VIDEO]},{'content_sha256':'wrong'}):
      self.row={**published_archive(),**update}
      with self.subTest(update=update),self.assertRaises(HTTPException):
        read_published_archive(self.storage.client,user_id=OWNER,job_id=JOB,storage_path=f'{OWNER}/{JOB}-{ATTEMPT}.zip')
    self.assert_no_compensation()


if __name__=='__main__':unittest.main()
