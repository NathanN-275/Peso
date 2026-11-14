from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import threading
import time
import unittest
from uuid import UUID, uuid4

import test_video_revocation_postgres as fixture


COLUMNS = ('attempt_id','user_id','video_id','purpose','bucket','storage_path',
           'source_path','content_type','size_bytes','job_id','worker_id','attempt_count')
PLACEHOLDERS = ','.join(['%s']*len(COLUMNS))


@unittest.skipUnless(fixture.DATABASE_URL, 'Dedicated local generated-media database is not configured.')
class GeneratedMediaWritesPostgresTest(unittest.TestCase):
  connect = classmethod(fixture.VideoRevocationPostgresTest.connect.__func__)
  setUpClass = classmethod(fixture.VideoRevocationPostgresTest.setUpClass.__func__)
  setUp = fixture.VideoRevocationPostgresTest.setUp
  sql = fixture.VideoRevocationPostgresTest.sql
  video = fixture.VideoRevocationPostgresTest.video
  revoke = fixture.VideoRevocationPostgresTest.rpc
  finish = fixture.VideoRevocationPostgresTest.finalize
  wait_blocked = fixture.VideoRevocationPostgresTest.wait_blocked

  def run_sql(self, query, values=(), connection=None, role='service_role'):
    if connection is not None:
      cursor = connection.execute(query,values)
      return cursor.fetchall() if cursor.description else []
    with self.connect() as connection:
      connection.execute('set local role '+role)
      connection.execute("set local statement_timeout='5s'")
      return self.run_sql(query,values,connection)

  def make_args(self, purpose='thumbnail', *, video=None, job=None, owner=None):
    owner = owner or self.user
    backfill = purpose=='thumbnail_backfill'
    video = video or self.video(owner=owner,status='completed' if backfill else 'processing',
                               thumbnail_path=None,playback_path=None)
    source = self.sql('select storage_path from public.videos where id=%s',(video,))[0]['storage_path']
    if not backfill and job is None:
      job = uuid4()
      self.run_sql("insert into public.analysis_jobs(id,video_id,status,attempt_count,lease_owner,lease_expires_at) values(%s,%s,'processing',1,'fixture-worker',%s)",
                   (job,video,datetime.now(timezone.utc)+timedelta(minutes=1)))
    attempt = uuid4()
    path = (f'{owner}/playback/{video}-{attempt}-h264-720p-v1.mp4' if purpose=='playback'
            else f'{owner}/thumbnails/{video}-{attempt}-thumb-v3.jpg')
    return (attempt,owner,video,purpose,'videos',path,source,
            'video/mp4' if purpose=='playback' else 'image/jpeg',80,
            None if backfill else job,None if backfill else 'fixture-worker',None if backfill else 1)

  def admit(self, args, connection=None, role='service_role', limits=(1000000000,1000000000)):
    return self.run_sql('select * from public.admit_private_media_generated_write('+PLACEHOLDERS+',%s,%s)',
                        (*args,*limits),connection,role)

  def observe(self, args, connection=None, role='service_role'):
    return self.run_sql('select public.observe_private_media_generated_write_success('+PLACEHOLDERS+') as observed',
                        args,connection,role)[0]['observed']

  def begin_owner(self, connection=None):
    return self.run_sql('select * from public.begin_private_media_owner_deletion(%s)',(self.user,),connection)

  def publish(self, args, *, column=None, value=None, connection=None, role='service_role'):
    column = column or ('playback_path' if args[3]=='playback' else 'thumbnail_path')
    self.assertIn(column,('playback_path','thumbnail_path'))
    return self.run_sql('update public.videos set '+column+'=%s where id=%s returning id',
                        (args[5] if value is None else value,args[2]),connection,role)

  def assert_no_attempts(self):
    self.assertEqual(self.sql('select attempt_id from public.private_media_generated_writes'),[])

  def reserve_source(self, owner=None, *, size=100, user_limit=1000000000, global_limit=1000000000):
    owner=owner or self.user;reservation=uuid4()
    return self.run_sql('select * from public.reserve_video_upload('+','.join(['%s']*17)+')',
      (reservation,owner,f'{owner}/source/{reservation}.mp4','synthetic.mp4','video/mp4',size,
       datetime.now(timezone.utc)+timedelta(minutes=5),'camera_roll','squat','side',1000,None,
       100,user_limit,100,global_limit,100))

  def test_generated_capacity_counts_pending_and_observed_attempts_at_user_and_global_bounds(self):
    first=self.make_args();self.admit(first,limits=(160,160))
    second=self.make_args('playback',video=first[2],job=first[9]);self.admit(second,limits=(160,160))
    for observed in (False,True):
      if observed:self.observe(first)
      for other,limits in ((self.user,(160,1000)),(self.other,(1000,160))):
        third=self.make_args(owner=other)
        with self.subTest(observed=observed,other=other),self.assertRaises(self.psycopg.errors.RaiseException):
          self.admit(third,limits=limits)
    self.assertEqual(len(self.sql('select attempt_id from public.private_media_generated_writes')),2)

  def test_source_reservations_and_generated_attempts_share_the_same_capacity_total(self):
    self.reserve_source(size=100)
    args=self.make_args()
    with self.assertRaises(self.psycopg.errors.RaiseException):self.admit(args,limits=(179,1000))
    self.admit(args,limits=(180,180))
    for observed in (False,True):
      if observed:self.observe(args)
      with self.assertRaises(self.psycopg.errors.RaiseException):self.reserve_source(size=1,user_limit=180)
      with self.assertRaises(self.psycopg.errors.RaiseException):self.reserve_source(self.other,size=1,global_limit=180)

  def test_invalid_or_missing_configured_capacity_denies_dispatch(self):
    args=self.make_args()
    for limits in ((0,1000),(1000,0),(-1,1000),(None,1000),(1000,None)):
      with self.subTest(limits=limits),self.assertRaises(self.psycopg.Error):self.admit(args,limits=limits)
    self.assert_no_attempts()

  def test_concurrent_generated_admissions_never_exceed_the_shared_global_limit(self):
    choices=[self.make_args(owner=owner) for owner in (self.user,self.other,self.user)]
    def attempt(args):
      try:self.admit(args,limits=(1000,160));return True
      except self.psycopg.errors.RaiseException:return False
    with ThreadPoolExecutor(3) as pool:results=list(pool.map(attempt,choices))
    self.assertEqual(sum(results),2)
    self.assertEqual(self.sql('select sum(size_bytes) as charged from public.private_media_generated_writes')[0]['charged'],160)

  def test_concurrent_source_and_generated_admission_use_one_capacity_decision(self):
    first,second=self.make_args(),self.make_args(owner=self.other)
    def attempt(kind):
      try:
        if kind=='source':self.reserve_source(size=100,user_limit=1000,global_limit=180)
        else:self.admit(first if kind=='first' else second,limits=(1000,180))
        return True
      except self.psycopg.errors.RaiseException:return False
    with ThreadPoolExecutor(3) as pool:results=list(pool.map(attempt,('source','first','second')))
    self.assertEqual(sum(results),2)
    charged=self.sql('select (select coalesce(sum(requested_bytes),0) from public.upload_reservations)+(select coalesce(sum(size_bytes),0) from public.private_media_generated_writes) as bytes')[0]['bytes']
    self.assertLessEqual(charged,180)

  def test_capacity_lock_wait_rechecks_expired_analysis_before_dispatch(self):
    args=self.make_args();expiry=datetime.now(timezone.utc)+timedelta(milliseconds=450)
    self.sql('update public.analysis_jobs set lease_expires_at=%s where id=%s',(expiry,args[9]))
    with self.connect() as capacity,self.connect() as waiting,ThreadPoolExecutor(1) as pool:
      capacity.execute("select pg_advisory_xact_lock(hashtextextended('peso:upload-capacity',0))")
      waiting.execute('set local role service_role');future=pool.submit(self.admit,args,waiting)
      self.wait_blocked(waiting.info.backend_pid,capacity.info.backend_pid)
      threading.Event().wait(max(0,(expiry-datetime.now(timezone.utc)).total_seconds()+.05));capacity.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):future.result(timeout=4)
    self.assert_no_attempts()

  def test_expiry_snapshot_includes_all_unpublished_generated_keys(self):
    args=self.make_args();self.admit(args)
    self.sql("update public.analysis_jobs set status='cancelled',lease_owner=null,lease_expires_at=null where id=%s",(args[9],))
    self.sql("update public.videos set save_state='pending',is_saved=false,expires_at=clock_timestamp()-interval '1 second' where id=%s",(args[2],))
    task=self.run_sql('select * from public.claim_expired_video_deletion(%s)',(args[2],))[0]
    self.assertIn(args[5],task['storage_paths'])
    self.assertEqual(self.sql('select id from public.videos where id=%s',(args[2],)),[])
    self.assertFalse(self.finish(task))

  def test_fresh_pipeline_receipts_bind_exact_key_body_and_generation(self):
    for purpose in ('thumbnail','playback'):
      args = self.make_args(purpose)
      self.assertEqual(self.admit(args),[{**dict(zip(COLUMNS,args)),'state':'dispatching'}])
      row = self.sql('select provider,state,observed_at from public.private_media_generated_writes where attempt_id=%s',(args[0],))[0]
      self.assertEqual(row,{'provider':'supabase','state':'dispatching','observed_at':None})

  def test_duplicate_or_rebound_attempt_does_not_authorize_dispatch(self):
    args = self.make_args();self.admit(args)
    for observed in (False,True):
      if observed:self.observe(args)
      with self.assertRaises(self.psycopg.errors.UniqueViolation):self.admit(args)
    different = list(self.make_args());different[0]=args[0]
    different[5]=f'{different[1]}/thumbnails/{different[2]}-{args[0]}-thumb-v3.jpg'
    with self.assertRaises(self.psycopg.errors.UniqueViolation):self.admit(tuple(different))
    self.assertEqual(len(self.sql('select attempt_id from public.private_media_generated_writes')),1)

  def test_key_type_source_size_and_identity_are_validated_before_intent(self):
    original = self.make_args()
    mutations = {0:UUID(int=0),1:self.other,2:uuid4(),3:'archive',4:'Bad/bucket',
                 5:original[5]+'different',6:original[6]+'different',7:'video/mp4',8:0}
    for index,value in mutations.items():
      args=list(original);args[index]=value
      with self.subTest(index=index),self.assertRaises(self.psycopg.Error):self.admit(tuple(args))
    for value in (None,-1):
      with self.subTest(size=value),self.assertRaises(self.psycopg.Error):self.admit((*original[:8],value,*original[9:]))
    self.assert_no_attempts()

  def test_missing_wrong_or_stale_worker_binding_is_denied(self):
    original = self.make_args()
    foreign = self.make_args(owner=self.other)
    for index,value in ((9,None),(9,uuid4()),(9,foreign[9]),(10,None),(10,''),(10,'another-worker'),(11,None),(11,0),(11,2)):
      args=list(original);args[index]=value
      with self.subTest(index=index,value=value),self.assertRaises(self.psycopg.Error):self.admit(tuple(args))
    self.assert_no_attempts()

  def test_deleting_owner_cannot_admit_any_generated_work(self):
    pipeline=self.make_args();backfill=self.make_args('thumbnail_backfill');self.begin_owner()
    for args in (pipeline,backfill):
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(args)
    self.assert_no_attempts()

  def test_missing_owner_is_not_created_from_generated_work(self):
    args=self.make_args()
    self.sql('truncate public.private_media_owners cascade')
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(args)
    self.assertEqual(self.sql('select user_id from public.private_media_owners'),[])
    self.assert_no_attempts()

  def test_revoked_pruned_expired_outboxed_or_missing_video_denies_admission(self):
    for denial in ('revoked','pruned','expired','infinite','outbox','missing'):
      args=self.make_args()
      if denial=='revoked':self.revoke([args[2]])
      elif denial=='pruned':self.sql("update public.videos set storage_state='pruned' where id=%s",(args[2],))
      elif denial=='expired':self.sql("update public.videos set expires_at=clock_timestamp()-interval '1 second' where id=%s",(args[2],))
      elif denial=='infinite':self.sql("update public.videos set expires_at='infinity' where id=%s",(args[2],))
      elif denial=='outbox':self.sql("insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values(%s,%s,'{}')",(args[2],self.user))
      else:self.sql('delete from public.videos where id=%s',(args[2],))
      with self.subTest(denial=denial),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(args)
    self.assert_no_attempts()

  def test_backfill_requires_current_completed_saved_lift_without_active_job(self):
    for denial in ('not-saved','processing','queued','active-job'):
      args=self.make_args('thumbnail_backfill')
      if denial=='not-saved':self.sql("update public.videos set is_saved=false,save_state='pending' where id=%s",(args[2],))
      elif denial=='active-job':self.run_sql("insert into public.analysis_jobs(video_id,status) values(%s,'queued')",(args[2],))
      else:self.sql('update public.videos set status=%s where id=%s',(denial,args[2]))
      with self.subTest(denial=denial),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(args)
    self.assert_no_attempts()

  def test_backfill_receipt_is_exact_and_rejects_any_worker_binding(self):
    args=self.make_args('thumbnail_backfill')
    for index,value in ((9,uuid4()),(10,'worker'),(11,1)):
      changed=list(args);changed[index]=value
      with self.subTest(index=index),self.assertRaises(self.psycopg.Error):self.admit(tuple(changed))
    self.assertEqual(self.admit(args),[{**dict(zip(COLUMNS,args)),'state':'dispatching'}])
    self.assertTrue(self.observe(args));self.assertEqual(self.publish(args),[{'id':args[2]}])

  def test_observation_is_exact_idempotent_and_does_not_settle_cleanup(self):
    args=self.make_args();self.admit(args);self.assertTrue(self.observe(args))
    before=self.sql('select * from public.private_media_generated_writes')[0]
    self.assertTrue(self.observe(args));self.assertEqual(self.sql('select * from public.private_media_generated_writes')[0],before)
    replacements=(uuid4(),self.other,uuid4(),'playback','other-bucket',args[5]+'x',args[6]+'x','video/mp4',79,uuid4(),'different',2)
    for index,value in enumerate(replacements):
      changed=list(args);changed[index]=value
      with self.subTest(index=index):self.assertFalse(self.observe(tuple(changed)))
    self.assertEqual(before['state'],'succeeded');self.assertIsNotNone(before['observed_at'])
    self.assertTrue(self.run_sql('select public.private_media_source_write_pending(%s,%s,%s) as pending',(args[2],self.user,[]))[0]['pending'])

  def test_late_success_survives_owner_deletion_and_auth_video_removal(self):
    args=self.make_args();self.admit(args);self.begin_owner()
    self.sql('delete from auth.users where id=%s',(self.user,))
    self.assertEqual(self.sql('select id from public.videos where id=%s',(args[2],)),[])
    self.assertTrue(self.observe(args))
    self.assertEqual(self.sql('select user_id,video_id,state from public.private_media_generated_writes'),
                     [{'user_id':self.user,'video_id':args[2],'state':'succeeded'}])

  def test_service_and_root_cannot_rebind_delete_or_insert_success(self):
    args=self.make_args();self.admit(args)
    for query in ('delete from public.private_media_generated_writes',
                  "update public.private_media_generated_writes set storage_path=storage_path||'x'"):
      with self.subTest(query=query),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.run_sql(query)
      with self.subTest(root=query),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.sql(query)
    for assignment in ('user_id=gen_random_uuid()','video_id=gen_random_uuid()',"provider='other'",'attempt_count=attempt_count+1',"source_path=source_path||'x'",'size_bytes=size_bytes+1',"created_at=created_at-interval '1 second'"):
      with self.subTest(assignment=assignment),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.sql('update public.private_media_generated_writes set '+assignment)
    new=self.make_args()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.sql('insert into public.private_media_generated_writes('+','.join(COLUMNS)+",state,observed_at) values("+PLACEHOLDERS+",'succeeded',clock_timestamp())",new)

  def test_observed_outcome_cannot_be_cleared_reopened_or_moved_into_future(self):
    args=self.make_args();self.admit(args);self.observe(args)
    for assignment in ("state='dispatching',observed_at=null",'observed_at=null',"observed_at='infinity'", "observed_at=clock_timestamp()+interval '1 hour'"):
      with self.subTest(assignment=assignment),self.assertRaises(self.psycopg.Error):
        self.run_sql('update public.private_media_generated_writes set '+assignment)

  def test_direct_insert_has_the_same_owner_and_current_generation_boundary(self):
    args=self.make_args();self.begin_owner()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.run_sql('insert into public.private_media_generated_writes('+','.join(COLUMNS)+') values('+PLACEHOLDERS+')',args)
    self.assert_no_attempts()

  def test_unobserved_intent_cannot_publish_even_with_privileged_table_write(self):
    args=self.make_args();self.admit(args)
    for role in ('service_role','postgres'):
      with self.subTest(role=role),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args,role=role)
    self.assertIsNone(self.sql('select thumbnail_path from public.videos where id=%s',(args[2],))[0]['thumbnail_path'])

  def test_observed_pipeline_keys_publish_exact_matching_assets(self):
    thumb=self.make_args();playback=self.make_args('playback',video=thumb[2],job=thumb[9])
    for args in (thumb,playback):
      self.admit(args);self.observe(args);self.assertEqual(self.publish(args),[{'id':args[2]}])
    self.assertEqual(self.sql('select thumbnail_path,playback_path from public.videos where id=%s',(thumb[2],)),
                     [{'thumbnail_path':thumb[5],'playback_path':playback[5]}])

  def test_wrong_asset_kind_video_or_path_cannot_reuse_an_observation(self):
    args=self.make_args();self.admit(args);self.observe(args)
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args,column='playback_path')
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args,value=args[5]+'x')
    other=self.video(thumbnail_path=None,playback_path=None)
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.run_sql('update public.videos set thumbnail_path=%s where id=%s',(args[5],other))

  def test_old_generation_cannot_publish_after_worker_attempt_changes(self):
    args=self.make_args();self.admit(args);self.observe(args)
    self.sql('update public.analysis_jobs set attempt_count=2 where id=%s',(args[9],))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)
    self.assertIsNone(self.sql('select thumbnail_path from public.videos where id=%s',(args[2],))[0]['thumbnail_path'])

  def test_cancelled_or_expired_worker_cannot_publish_observed_bytes(self):
    for denial in ('cancelled','expired'):
      args=self.make_args();self.admit(args);self.observe(args)
      if denial=='cancelled':self.sql("update public.analysis_jobs set status='cancelled',lease_owner=null,lease_expires_at=null where id=%s",(args[9],))
      else:self.sql("update public.analysis_jobs set lease_expires_at=clock_timestamp()-interval '1 second' where id=%s",(args[9],))
      with self.subTest(denial=denial),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)

  def test_source_change_cannot_publish_bytes_from_the_prior_source(self):
    args=self.make_args();self.admit(args);self.observe(args)
    self.sql('update public.videos set storage_path=%s where id=%s',(f'{self.user}/source/new-source.mp4',args[2]))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)

  def test_backfill_rechecks_saved_status_and_new_analysis_at_publication(self):
    for denial in ('not-saved','active-job','status'):
      args=self.make_args('thumbnail_backfill');self.admit(args);self.observe(args)
      if denial=='not-saved':self.sql("update public.videos set save_state='pending',is_saved=false where id=%s",(args[2],))
      elif denial=='active-job':self.run_sql("insert into public.analysis_jobs(video_id,status) values(%s,'queued')",(args[2],))
      else:self.sql("update public.videos set status='processing' where id=%s",(args[2],))
      with self.subTest(denial=denial),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)

  def test_legacy_untracked_new_paths_are_denied_on_insert_and_update(self):
    video=self.video();legacy=f'{self.user}/thumbnails/new-legacy.jpg'
    for role in ('service_role','postgres'):
      with self.subTest(role=role):
        with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
          self.run_sql('update public.videos set thumbnail_path=%s where id=%s',(legacy,video),role=role)
        with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
          self.run_sql("insert into public.videos(id,user_id,storage_path,playback_path) values(%s,%s,%s,%s)",
                       (uuid4(),self.user,f'{self.user}/source/new.mp4',f'{self.user}/playback/new.mp4'),role=role)

  def test_existing_paths_are_unchanged_or_cleared_without_a_new_intent(self):
    video=self.video()
    self.run_sql('update public.videos set thumbnail_path=thumbnail_path,playback_path=playback_path where id=%s',(video,))
    self.run_sql('update public.videos set thumbnail_path=null,playback_path=null where id=%s',(video,))
    self.assertEqual(self.sql('select thumbnail_path,playback_path from public.videos where id=%s',(video,)),
                     [{'thumbnail_path':None,'playback_path':None}])

  def test_revocation_captures_every_unpublished_admitted_key(self):
    thumb=self.make_args();playback=self.make_args('playback',video=thumb[2],job=thumb[9])
    self.admit(thumb);self.admit(playback);self.observe(playback)
    task=self.revoke([thumb[2]],delete=True)[0]
    self.assertEqual(set(task['storage_paths']),{thumb[6],thumb[5],playback[5]})
    self.assertEqual(self.revoke([thumb[2]],delete=True)[0]['storage_paths'],task['storage_paths'])
    self.assertFalse(self.finish(task))
    self.assertIsNotNone(self.sql('select id from public.videos where id=%s',(thumb[2],))[0]['id'])

  def test_saved_deletion_and_outbox_completion_stay_pending_in_both_states(self):
    args=self.make_args('thumbnail_backfill');self.admit(args)
    task=self.run_sql('select * from public.revoke_saved_lifts(%s,%s)',(self.user,[args[2]]))[0]['task']
    for observed in (False,True):
      if observed:self.observe(args)
      self.assertFalse(self.finish(task))
      self.assertIsNone(self.sql('select completed_at from public.saved_lift_deletion_receipts')[0]['completed_at'])
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.run_sql('delete from public.video_deletion_outbox where video_id=%s',(args[2],))

  def test_metadata_loss_does_not_remove_pending_generation_or_complete_receipt(self):
    args=self.make_args('thumbnail_backfill');self.admit(args);self.observe(args)
    self.run_sql('select * from public.revoke_saved_lifts(%s,%s)',(self.user,[args[2]]))
    self.sql('delete from public.videos where id=%s',(args[2],))
    self.assertTrue(self.run_sql('select public.private_media_source_write_pending(%s,%s,%s) as pending',(args[2],self.user,[]))[0]['pending'])
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.run_sql('update public.saved_lift_deletion_receipts set completed_at=clock_timestamp() where video_id=%s',(args[2],))
    retry=self.revoke([args[2]],delete=True)[0]
    self.assertIn(args[5],retry['storage_paths']);self.assertFalse(self.finish(retry))

  def test_other_owner_cleanup_remains_available(self):
    args=self.make_args();self.admit(args)
    video=self.video(owner=self.other)
    self.assertTrue(self.finish(self.revoke([video],owner=self.other,delete=True)[0]))

  def test_client_roles_cannot_access_ledger_or_dispatch_and_observation_rpcs(self):
    args=self.make_args()
    queries=[('select * from public.private_media_generated_writes',()),
             ('select * from public.admit_private_media_generated_write('+PLACEHOLDERS+',%s,%s)',(*args,1000000000,1000000000)),
             ('select public.observe_private_media_generated_write_success('+PLACEHOLDERS+')',args)]
    for role in ('anon','authenticated','public_probe'):
      for query,values in queries:
        with self.subTest(role=role,query=query),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
          self.run_sql(query,values,role=role)

  def test_functions_are_invokers_with_fixed_path_and_ledger_has_no_cascading_fks(self):
    names=['assert_private_media_generated_write','assert_private_media_generated_capacity','guard_private_media_generated_write',
           'admit_private_media_generated_write','observe_private_media_generated_write_success','fence_generated_media_publication']
    rows=self.sql('select proname,prosecdef,proconfig from pg_catalog.pg_proc where proname=any(%s)',(names,))
    self.assertEqual(len(rows),len(names))
    for row in rows:
      self.assertFalse(row['prosecdef']);self.assertIn('search_path=""',row['proconfig'])
    self.assertTrue(self.sql("select relrowsecurity from pg_catalog.pg_class where oid='public.private_media_generated_writes'::regclass")[0]['relrowsecurity'])
    self.assertEqual(self.sql("select conname from pg_catalog.pg_constraint where conrelid='public.private_media_generated_writes'::regclass and contype='f'"),[])

  def test_admission_waits_for_owner_and_observes_committed_deletion(self):
    args=self.make_args()
    with self.connect() as holder,self.connect() as waiting,ThreadPoolExecutor(1) as pool:
      holder.execute('set local role service_role');self.begin_owner(holder)
      waiting.execute('set local role service_role')
      future=pool.submit(self.admit,args,waiting)
      self.wait_blocked(waiting.info.backend_pid,holder.info.backend_pid);holder.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):future.result(timeout=4)
    self.assert_no_attempts()

  def test_admission_holds_owner_until_commit_then_deletion_keeps_pending_attempt(self):
    args=self.make_args()
    with self.connect() as holder,self.connect() as waiting,ThreadPoolExecutor(1) as pool:
      holder.execute('set local role service_role');self.admit(args,holder)
      waiting.execute('set local role service_role')
      future=pool.submit(self.begin_owner,waiting)
      self.wait_blocked(waiting.info.backend_pid,holder.info.backend_pid);holder.commit()
      self.assertIsNotNone(future.result(timeout=4)[0]['deleting_at']);waiting.commit()
    self.assertTrue(self.observe(args));self.assertEqual(len(self.sql('select attempt_id from public.private_media_generated_writes')),1)

  def test_admission_waits_for_revocation_then_denies_dispatch(self):
    args=self.make_args()
    with self.connect() as holder,self.connect() as waiting,ThreadPoolExecutor(1) as pool:
      holder.execute('set local role service_role')
      holder.execute('select * from public.revoke_video_media(%s,%s,false)',(self.user,[args[2]])).fetchall()
      waiting.execute('set local role service_role');future=pool.submit(self.admit,args,waiting)
      self.wait_blocked(waiting.info.backend_pid,holder.info.backend_pid);holder.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):future.result(timeout=4)
    self.assert_no_attempts()

  def test_admission_before_revocation_is_captured_after_actual_lock_wait(self):
    args=self.make_args()
    with self.connect() as holder,self.connect() as waiting,ThreadPoolExecutor(1) as pool:
      holder.execute('set local role service_role');self.admit(args,holder)
      waiting.execute('set local role service_role')
      future=pool.submit(self.run_sql,'select * from public.revoke_video_media(%s,%s,false)',(self.user,[args[2]]),waiting)
      self.wait_blocked(waiting.info.backend_pid,holder.info.backend_pid);holder.commit()
      task=future.result(timeout=4)[0];waiting.commit()
    self.assertIn(args[5],task['storage_paths']);self.assertFalse(self.finish(task))

  def test_lease_expiry_after_video_lock_wait_denies_new_dispatch(self):
    args=self.make_args();expiry=datetime.now(timezone.utc)+timedelta(milliseconds=450)
    self.sql('update public.analysis_jobs set lease_expires_at=%s where id=%s',(expiry,args[9]))
    with self.connect() as holder,self.connect() as waiting,ThreadPoolExecutor(1) as pool:
      holder.execute('select id from public.videos where id=%s for update',(args[2],))
      waiting.execute('set local role service_role');future=pool.submit(self.admit,args,waiting)
      self.wait_blocked(waiting.info.backend_pid,holder.info.backend_pid)
      threading.Event().wait(max(0,(expiry-datetime.now(timezone.utc)).total_seconds()+.05));holder.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):future.result(timeout=4)
    self.assert_no_attempts()

  def test_busy_current_job_fails_nowait_without_partial_admission(self):
    args=self.make_args()
    with self.connect() as holder:
      holder.execute('select id from public.analysis_jobs where id=%s for update',(args[9],))
      start=time.monotonic()
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):self.admit(args)
      self.assertLess(time.monotonic()-start,1.5)
    self.assert_no_attempts()
