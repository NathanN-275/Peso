from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import unittest
from uuid import UUID, uuid4

import test_video_revocation_postgres as fixture
import test_generated_media_writes_postgres as generated
import test_analyzed_export_writes_postgres as exports


@unittest.skipUnless(fixture.DATABASE_URL, 'Dedicated localhost archive-write database is not configured.')
class ArchiveWritesPostgresTest(unittest.TestCase):
  connect=classmethod(fixture.VideoRevocationPostgresTest.connect.__func__)
  setUpClass=classmethod(fixture.VideoRevocationPostgresTest.setUpClass.__func__)
  setUp=fixture.VideoRevocationPostgresTest.setUp
  sql=fixture.VideoRevocationPostgresTest.sql
  video=fixture.VideoRevocationPostgresTest.video
  revoke=fixture.VideoRevocationPostgresTest.rpc
  finish=fixture.VideoRevocationPostgresTest.finalize
  legacy_video_fields=fixture.VideoRevocationPostgresTest.legacy_video_fields
  run_sql=generated.GeneratedMediaWritesPostgresTest.run_sql
  wait_blocked=fixture.VideoRevocationPostgresTest.wait_blocked

  def plan(self, job, owner=None, connection=None):
    return self.run_sql('select public.plan_private_media_archive(%s,%s) as plan',
                        (owner or self.user,job),connection)[0]['plan']

  def arguments(self, plan):
    from psycopg.types.json import Jsonb
    attempt=uuid4()
    members=[{**member,'artifact_bucket':'videos','artifact_path':member['source_path'],
              'artifact_size_bytes':80,'artifact_sha256':'a'*64} for member in plan['member_snapshots']]
    return (attempt,plan['user_id'],plan['archive_job_id'],plan['archive_attempt_count'],plan['archive_started_at'],
            [UUID(v) for v in plan['video_ids']],Jsonb(members),'saved-lift-exports',f"{plan['user_id']}/{plan['archive_job_id']}-{attempt}.zip",
            200,'b'*64,1000000000,1000000000)

  def make(self, count=2, owner=None):
    owner=owner or self.user
    videos=[self.video(owner=owner) for _ in range(count)]
    self.sql("insert into public.analysis_results(video_id,result_json) select id,'{}'::jsonb from public.videos where id=any(%s)",(videos,))
    job=uuid4()
    self.run_sql("insert into public.saved_lift_export_jobs(id,user_id,video_ids,status,attempts,started_at) values(%s,%s,%s,'processing',1,clock_timestamp())",(job,owner,videos))
    return self.arguments(self.plan(job,owner))

  def admit(self,args,connection=None,role='service_role'):
    return self.run_sql('select public.admit_private_media_archive_write('+','.join(['%s']*13)+') as receipt',args,connection,role)[0]['receipt']

  def observe(self,args,connection=None):
    return self.run_sql('select public.observe_private_media_generated_write_success('+','.join(['%s']*12)+') as observed',
      (args[0],args[1],None,'archive',args[7],args[8],None,'application/zip',args[9],None,None,None),connection)[0]['observed']

  def publish(self,args,ttl=3600,connection=None,role='service_role'):
    return self.run_sql('select public.publish_private_media_archive(%s,%s,%s) as receipt',
                       (args[0],args[1],ttl),connection,role)[0]['receipt']

  def completed(self,args):
    self.admit(args);self.assertTrue(self.observe(args));return self.publish(args)

  def read(self,args):
    return self.run_sql('select public.read_private_media_archive(%s,%s) as receipt',(args[1],args[2]))[0]['receipt']

  def test_plan_is_compact_ordered_and_admission_observation_publication_are_separate(self):
    args=self.make();plan=self.plan(args[2]);self.assertEqual(plan['video_ids'],[str(v) for v in args[5]])
    self.assertTrue(all('result_json' not in member for member in plan['member_snapshots']))
    row=self.admit(args);self.assertEqual(row['state'],'dispatching');self.assertIsNone(row['published_at'])
    self.assertEqual(row['content_sha256'],'b'*64)
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)
    self.assertTrue(self.observe(args));published=self.publish(args)
    job=self.sql('select status,archive_path,completed_at,expires_at from public.saved_lift_export_jobs where id=%s',(args[2],))[0]
    self.assertEqual(job['status'],'completed');self.assertEqual(job['archive_path'],args[8])
    self.assertEqual(job['completed_at'],datetime.fromisoformat(published['published_at']))
    self.assertEqual(job['expires_at'],datetime.fromisoformat(published['cache_expires_at']))
    self.assertEqual(self.publish(args,ttl=7200),published)
    self.assertEqual(self.read(args),published)

  def test_all_fifty_members_are_bound_and_last_member_revocation_captures_the_archive(self):
    args=self.make(50);self.admit(args)
    self.assertEqual(len(args[6].obj),50)
    task=self.revoke([args[5][-1]])[0]
    self.assertIn(args[8],task['archive_paths']);self.assertNotIn(args[8],task['storage_paths'])
    self.assertFalse(self.finish(task));self.assertTrue(self.observe(args))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)

  def test_nonce_replay_and_second_nonce_for_same_job_generation_are_rejected(self):
    args=self.make();self.admit(args)
    with self.assertRaises(self.psycopg.errors.UniqueViolation):self.admit(args)
    changed=list(args);changed[0]=uuid4();changed[8]=f'{args[1]}/{args[2]}-{changed[0]}.zip'
    with self.assertRaises(self.psycopg.errors.UniqueViolation):self.admit(tuple(changed))

  def test_identity_generation_order_bucket_key_size_and_hash_cannot_be_rebound(self):
    args=self.make()
    changes={0:None,1:self.other,2:uuid4(),3:2,4:datetime.now(timezone.utc),5:list(reversed(args[5])),
             7:'videos',8:f'{args[1]}/{args[2]}.zip',9:0,10:'bad',11:0,12:None}
    for index,value in changes.items():
      changed=list(args);changed[index]=value
      with self.subTest(index=index),self.assertRaises(self.psycopg.Error):self.admit(tuple(changed))
    self.assertEqual(self.sql('select attempt_id from public.private_media_generated_writes'),[])

  def test_every_manifest_field_and_extra_untyped_fields_are_checked(self):
    from psycopg.types.json import Jsonb
    args=self.make();member=args[6].obj[0]
    for key,value in (('video_id',str(uuid4())),('source_path',member['source_path']+'old'),('analysis_id',str(uuid4())),
                      ('analysis_model_version','old'),('analysis_snapshot_hash','c'*64),('variant','pose'),
                      ('entry_name','../../outside.mp4'),('artifact_path',member['source_path']+'old'),
                      ('artifact_size_bytes',True),('artifact_size_bytes','80'),('artifact_size_bytes',0),
                      ('artifact_sha256','wrong'),('artifact_bucket','Bad/bucket'),('extra',1)):
      changed=list(args);changed[6]=Jsonb([{**member,key:value},args[6].obj[1]])
      with self.subTest(key=key,value=value),self.assertRaises(self.psycopg.Error):self.admit(tuple(changed))

  def test_clean_mov_filename_preserves_source_extension(self):
    args=self.make(1);vid=args[5][0]
    self.legacy_video_fields(vid,{'playback_path':None,'storage_path':f'{args[1]}/source/{vid}.MOV'})
    plan=self.plan(args[2]);self.assertTrue(plan['member_snapshots'][0]['entry_name'].endswith('.mov'))
    self.admit(self.arguments(plan))

  def test_missing_foreign_unsaved_expired_pruned_active_and_outboxed_member_deny_full_plan(self):
    for denial in ('missing','foreign','unsaved','expired','pruned','active','outbox'):
      args=self.make();vid=args[5][-1]
      if denial=='missing':self.sql('delete from public.videos where id=%s',(vid,))
      elif denial=='foreign':args=(args[0],self.other,*args[2:])
      elif denial=='unsaved':self.sql("update public.videos set is_saved=false,save_state='pending' where id=%s",(vid,))
      elif denial=='expired':self.sql("update public.videos set expires_at=clock_timestamp()-interval '1 second' where id=%s",(vid,))
      elif denial=='pruned':self.sql("update public.videos set storage_state='pruned' where id=%s",(vid,))
      elif denial=='active':self.run_sql("insert into public.analysis_jobs(video_id,status) values(%s,'queued')",(vid,))
      else:self.sql("insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values(%s,%s,'{}')",(vid,self.user))
      with self.subTest(denial=denial),self.assertRaises(self.psycopg.Error):self.admit(args)

  def test_same_analysis_id_contents_source_and_newer_analysis_changes_deny_publication(self):
    from psycopg.types.json import Jsonb
    for change in ('contents','source','newer'):
      args=self.make();self.admit(args);self.observe(args);vid=args[5][-1]
      if change=='contents':self.run_sql('update public.analysis_results set result_json=%s where video_id=%s',(Jsonb({'reps':9}),vid))
      elif change=='source':self.legacy_video_fields(vid,{'playback_path':f'{self.user}/new/{vid}.mp4'})
      else:self.run_sql("insert into public.analysis_results(video_id,model_version,result_json,created_at) values(%s,'newer','{}',clock_timestamp())",(vid,))
      with self.subTest(change=change),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)
      self.assertEqual(self.sql('select status from public.saved_lift_export_jobs where id=%s',(args[2],))[0]['status'],'processing')

  def test_overlay_member_requires_matching_published_export_bucket_snapshot_and_size(self):
    from psycopg.types.json import Jsonb
    args=self.make(1);vid=args[5][0]
    self.run_sql('update public.analysis_results set result_json=%s where video_id=%s',
                 (Jsonb({'poseFrames':[{'time':0,'keypoints':[]}]}),vid))
    plan=self.plan(args[2]);args=list(self.arguments(plan));member=args[6].obj[0]
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(tuple(args))
    aid=self.sql('select id from public.analysis_results where video_id=%s',(vid,))[0]['id']
    e=exports.AnalyzedExportWritesPostgresTest
    export=e.make(self,video=vid,analysis=aid)
    e.admit(self,export);e.observe(self,export);e.publish(self,export)
    member['artifact_path']=export[4]
    self.admit(tuple(args))
    self.observe(tuple(args));self.publish(tuple(args))

  def test_job_processing_generation_is_frozen_against_aba(self):
    args=self.make();self.admit(args)
    for fields in ('attempts=attempts+1','started_at=clock_timestamp()'):
      with self.subTest(fields=fields),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.run_sql('update public.saved_lift_export_jobs set '+fields+' where id=%s',(args[2],))

  def test_manifest_identity_and_evidence_cannot_be_modified_or_removed(self):
    args=self.make();self.admit(args)
    for fields in ("content_sha256=repeat('c',64)","member_snapshots='[]'","video_ids='{}'",'archive_job_id=gen_random_uuid()',
                   'archive_attempt_count=archive_attempt_count+1','archive_started_at=clock_timestamp()',"purpose='thumbnail_backfill'"):
      with self.subTest(fields=fields),self.assertRaises(self.psycopg.Error):self.run_sql('update public.private_media_generated_writes set '+fields)
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.run_sql('delete from public.private_media_generated_writes')

  def test_late_success_survives_job_video_and_auth_loss_without_publication_or_settlement(self):
    args=self.make();self.admit(args)
    self.run_sql('select * from public.begin_private_media_owner_deletion(%s)',(self.user,))
    self.sql('delete from auth.users where id=%s',(self.user,))
    self.assertTrue(self.observe(args))
    row=self.sql('select state,video_ids,published_at from public.private_media_generated_writes')[0]
    self.assertEqual(row['state'],'succeeded');self.assertIsNone(row['published_at']);self.assertEqual(row['video_ids'],args[5])
    with self.assertRaises(self.psycopg.Error):self.publish(args)
    self.assertTrue(self.run_sql('select public.private_media_source_write_pending(%s,%s,%s) as pending',
      (args[5][-1],self.user,[]))[0]['pending'])

  def test_every_member_retains_unpublished_archive_cleanup_after_job_loss(self):
    args=self.make();self.admit(args);self.sql('delete from public.saved_lift_export_jobs where id=%s',(args[2],))
    for vid in args[5]:
      task=self.revoke([vid])[0]
      self.assertIn(args[8],task['archive_paths']);self.assertNotIn(args[8],task['storage_paths']);self.assertFalse(self.finish(task))

  def test_retention_snapshots_archive_bucket_and_keeps_cleanup_pending(self):
    args=self.make();self.admit(args);vid=args[5][-1]
    self.sql("update public.videos set is_saved=false,save_state='pending',expires_at=clock_timestamp()-interval '1 second' where id=%s",(vid,))
    task=self.run_sql('select * from public.claim_expired_video_deletion(%s)',(vid,))[0]
    self.assertIn(args[8],task['archive_paths']);self.assertNotIn(args[8],task['storage_paths']);self.assertFalse(self.finish(task))

  def test_success_is_still_charged_and_source_admission_counts_archive_bytes(self):
    args=list(self.make());args[11:]=[200,200];self.completed(tuple(args))
    with self.assertRaises(self.psycopg.errors.RaiseException):
      generated.GeneratedMediaWritesPostgresTest.reserve_source(self,size=1,user_limit=200)
    self.assertEqual(self.sql('select sum(size_bytes) as charged from public.private_media_generated_writes')[0]['charged'],200)

  def test_capacity_rejects_additional_archive_and_generated_bytes(self):
    args=self.make();self.admit(args)
    other=list(self.make());other[11:]=[399,399]
    with self.assertRaises(self.psycopg.errors.RaiseException):self.admit(tuple(other))
    other=generated.GeneratedMediaWritesPostgresTest.make_args(self,'thumbnail_backfill')
    with self.assertRaises(self.psycopg.errors.RaiseException):generated.GeneratedMediaWritesPostgresTest.admit(self,other,limits=(200,200))

  def test_publication_expiry_is_anchored_to_admission_and_replay_never_extends_it(self):
    args=self.make();admitted=self.admit(args);self.observe(args);published=self.publish(args,ttl=30)
    self.assertEqual(datetime.fromisoformat(published['cache_expires_at'])-datetime.fromisoformat(admitted['created_at']),timedelta(seconds=30))
    self.assertEqual(self.publish(args,ttl=300),published)
    with self.assertRaises(self.psycopg.Error):self.run_sql("update public.private_media_generated_writes set cache_expires_at=cache_expires_at+interval '1 second'")

  def test_elapsed_attempt_cannot_publish_and_observation_remains_pending(self):
    args=self.make();self.admit(args);self.observe(args);threading.Event().wait(1.05)
    with self.assertRaises(self.psycopg.Error):self.publish(args,ttl=1)
    self.assertIsNone(self.sql('select published_at from public.private_media_generated_writes')[0]['published_at'])

  def test_new_completed_reference_without_observed_intent_is_denied(self):
    args=self.make()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.run_sql("update public.saved_lift_export_jobs set status='completed',archive_path=%s,completed_at=clock_timestamp(),expires_at=clock_timestamp()+interval '1 hour' where id=%s",(args[8],args[2]))

  def test_busy_member_and_job_and_owner_locks_fail_fast_without_dispatch(self):
    args=self.make()
    for table,key,value in (('videos','id',args[5][-1]),('saved_lift_export_jobs','id',args[2]),('private_media_owners','user_id',self.user)):
      with self.subTest(table=table),self.connect() as holder:
        holder.execute(f'select 1 from public.{table} where {key}=%s for update',(value,))
        start=time.monotonic()
        with self.assertRaises(self.psycopg.errors.LockNotAvailable):self.admit(args)
        self.assertLess(time.monotonic()-start,2)

  def test_privileges_are_service_only_fixed_invoker_and_no_cascade_foreign_keys(self):
    args=self.make()
    for role in ('anon','authenticated','public_probe'):
      with self.subTest(role=role),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.admit(args,role=role)
    procs=self.sql("select prosecdef,proconfig from pg_proc where proname in ('plan_private_media_archive','admit_private_media_archive_write','publish_private_media_archive','assert_private_media_archive_write')")
    self.assertEqual(len(procs),4)
    self.assertTrue(all(not p['prosecdef'] and 'search_path=""' in p['proconfig'] for p in procs))
    self.assertEqual(self.sql("select 1 from pg_constraint where conrelid='public.private_media_generated_writes'::regclass and contype='f'"),[])

  def test_frozen_published_zip_survives_later_analysis_update_but_not_member_revocation(self):
    args=self.make();published=self.completed(args)
    self.run_sql("update public.analysis_results set result_json='{}'::jsonb||jsonb_build_object('reps',9) where video_id=%s",(args[5][0],))
    self.assertEqual(self.publish(args),published)
    self.assertEqual(self.read(args),published)
    self.revoke([args[5][-1]])
    with self.assertRaises(self.psycopg.Error):self.publish(args)
    self.assertIsNone(self.read(args))

  def test_historical_untracked_archive_is_not_a_new_published_download(self):
    vid=self.video()
    job=fixture.VideoRevocationPostgresTest.archive(self,[vid])
    self.assertIsNone(self.run_sql('select public.read_private_media_archive(%s,%s) as receipt',(self.user,job))[0]['receipt'])

  def test_global_capacity_serializes_concurrent_distinct_archives(self):
    args=[]
    for owner in (self.user,self.other,self.user):
      row=list(self.make(owner=owner));row[11:]=[1000,400];args.append(tuple(row))
    def dispatch(row):
      try:self.admit(row);return True
      except (self.psycopg.errors.RaiseException,self.psycopg.errors.LockNotAvailable):return False
    with ThreadPoolExecutor(3) as pool:results=list(pool.map(dispatch,args))
    self.assertLessEqual(sum(results),2)
    for row,done in zip(args,results):
      if not done:dispatch(row)
    self.assertEqual(self.sql('select sum(size_bytes) as charged from public.private_media_generated_writes')[0]['charged'],400)

  def test_capacity_wait_rechecks_member_wall_clock_expiry_before_insert(self):
    args=self.make();vid=args[5][0]
    self.sql("update public.videos set expires_at=clock_timestamp()+interval '1 second' where id=%s",(vid,))
    ready=threading.Event();waiter={}
    def admission():
      with self.connect() as connection:
        connection.execute('set local role service_role');connection.execute("set local statement_timeout='5s'")
        waiter['pid']=connection.info.backend_pid;ready.set()
        return self.admit(args,connection)
    with ThreadPoolExecutor(1) as pool,self.connect() as holder:
      holder.execute("select pg_advisory_xact_lock(hashtextextended('peso:upload-capacity',0))")
      future=pool.submit(admission)
      try:
        self.assertTrue(ready.wait(2));self.wait_blocked(waiter['pid'],holder.info.backend_pid)
        time.sleep(1.05)
      finally:holder.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):future.result(timeout=5)
    self.assertEqual(self.sql('select attempt_id from public.private_media_generated_writes'),[])

  def test_busy_ledger_observation_cannot_deadlock_publication_or_partially_complete_job(self):
    args=self.make();self.admit(args);self.observe(args)
    with self.connect() as observer:
      observer.execute('select attempt_id from public.private_media_generated_writes where attempt_id=%s for update',(args[0],))
      started=time.monotonic()
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):self.publish(args)
      self.assertLess(time.monotonic()-started,2)
    self.assertEqual(self.sql('select status from public.saved_lift_export_jobs where id=%s',(args[2],))[0]['status'],'processing')
    self.assertIsNone(self.sql('select published_at from public.private_media_generated_writes')[0]['published_at'])
    self.publish(args)

  def test_overlay_member_cannot_use_another_bucket_or_mismatched_observed_size(self):
    from psycopg.types.json import Jsonb
    args=self.make(1);vid=args[5][0]
    self.run_sql('update public.analysis_results set result_json=%s where video_id=%s',
                 (Jsonb({'poseFrames':[{'time':0,'keypoints':[]}]}),vid))
    aid=self.sql('select id from public.analysis_results where video_id=%s',(vid,))[0]['id']
    e=exports.AnalyzedExportWritesPostgresTest;export=e.make(self,video=vid,analysis=aid)
    e.admit(self,export);e.observe(self,export);e.publish(self,export)
    args=list(self.arguments(self.plan(args[2])));member=args[6].obj[0];member['artifact_path']=export[4]
    for fields in ({'artifact_bucket':'other'},{'artifact_size_bytes':81}):
      changed=list(args);changed[6]=Jsonb([{**member,**fields}])
      with self.subTest(fields=fields),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(tuple(changed))

  def test_publication_after_owner_deletion_never_makes_a_download_available(self):
    args=self.make();self.admit(args);self.observe(args)
    self.run_sql('select * from public.begin_private_media_owner_deletion(%s)',(self.user,))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.read(args)

  def test_retention_rejects_unsafe_historical_archive_paths_without_losing_metadata(self):
    for suffix in ('../other.zip','bad.zip\u0085','a//bad.zip','file.zip/'):
      vid=self.video()
      fixture.VideoRevocationPostgresTest.archive(self,[vid],path=f'{self.user}/{suffix}',legacy=True)
      self.sql("update public.videos set is_saved=false,save_state='pending',expires_at=clock_timestamp()-interval '1 second' where id=%s",(vid,))
      with self.subTest(suffix=suffix),self.assertRaises(self.psycopg.Error):
        self.run_sql('select * from public.claim_expired_video_deletion(%s)',(vid,))
      self.assertEqual(len(self.sql('select id from public.videos where id=%s',(vid,))),1)
      self.assertEqual(self.sql('select video_id from public.video_deletion_outbox where video_id=%s',(vid,)),[])

  def test_plan_variants_match_pose_and_literal_barbell_availability(self):
    from psycopg.types.json import Jsonb
    args=self.make(1);vid=args[5][0]
    for result,variant in (
      ({},'clean'),({'poseFrames':[],'barbellPath':{'available':1,'points':[{},{}]}},'clean'),
      ({'poseFrames':[{}]},'pose'),({'barbellPath':{'available':True,'points':[{},{}]}},'barbell'),
      ({'poseFrames':[{}],'barbellPath':{'available':True,'points':[{},{}]}},'pose-barbell'),
      ({'poseFrames':{},'barbellPath':{'available':'true','points':[{},{}]}},'clean'),
      ({'barbellPath':{'available':True,'points':[{}]}},'clean'),
    ):
      self.run_sql('update public.analysis_results set result_json=%s where video_id=%s',(Jsonb(result),vid))
      with self.subTest(result=result):self.assertEqual(self.plan(args[2])['member_snapshots'][0]['variant'],variant)



if __name__=='__main__':unittest.main()
