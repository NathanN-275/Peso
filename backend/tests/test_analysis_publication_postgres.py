from __future__ import annotations

import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import test_video_revocation_postgres as fixture_module

DATABASE_URL=os.getenv('VIDEO_REVOCATION_TEST_DATABASE_URL','')


@unittest.skipUnless(DATABASE_URL,'Dedicated video-revocation Postgres database is not configured.')
class AnalysisPublicationPostgresTest(unittest.TestCase):
  connect=classmethod(fixture_module.VideoRevocationPostgresTest.connect.__func__)
  setUp=fixture_module.VideoRevocationPostgresTest.setUp
  sql=fixture_module.VideoRevocationPostgresTest.sql
  video=fixture_module.VideoRevocationPostgresTest.video
  rpc=fixture_module.VideoRevocationPostgresTest.rpc
  wait_blocked=fixture_module.VideoRevocationPostgresTest.wait_blocked
  queueable_video=fixture_module.VideoRevocationPostgresTest.queueable_video
  enqueue=fixture_module.VideoRevocationPostgresTest.enqueue

  @classmethod
  def setUpClass(cls):
    fixture_module.VideoRevocationPostgresTest.setUpClass.__func__(cls)
    from psycopg.types.json import Jsonb
    cls.Jsonb=Jsonb
    with cls.connect(autocommit=True) as connection:
      paths=list((Path(__file__).resolve().parents[2]/'supabase/migrations').glob('*_analysis_publication_fence.sql'))
      if len(paths)!=1:raise RuntimeError('Exactly one CLI-generated analysis publication migration is required.')
      if connection.execute("select to_regprocedure('public.publish_video_analysis(uuid,uuid,text,integer,jsonb,text,jsonb)')").fetchone()['to_regprocedure'] is None:
        raise RuntimeError('The shared fixture must load the current publication migration.')

  def job(self,video,status='processing',attempt=1,worker='worker',expiry=None):
    job=uuid4()
    expiry=(expiry if expiry is not None else datetime.now(timezone.utc)+timedelta(minutes=1)) if status=='processing' else None
    worker=worker if status=='processing' else None
    self.sql("insert into public.analysis_jobs(id,video_id,status,attempt_count,lease_owner,lease_expires_at) values(%s,%s,%s,%s,%s,%s)",
             (job,video,status,attempt,worker,expiry))
    return job

  def publish(self,video,job,*,attempt=1,worker='worker',fields=None,result=None,role='service_role',connection=None):
    if connection is None:
      with self.connect() as conn:
        conn.execute("set local statement_timeout='4s'");conn.execute('set local role '+role)
        return self.publish(video,job,attempt=attempt,worker=worker,fields=fields,result=result,connection=conn)
    return connection.execute('select public.publish_video_analysis(%s,%s,%s,%s,%s,%s,%s) as publication',
       (video,job,worker,attempt,self.Jsonb(fields if fields is not None else {}),
        'model-v1' if result is not None else None,self.Jsonb(result) if result is not None else None)).fetchone()['publication']

  def control(self,name,job,*,attempt=1,worker='worker',connection=None):
    calls={
      'renew':('public.renew_video_analysis_job_lease(%s,%s,%s,60)',()),
      'progress':('public.report_video_analysis_job_progress(%s,%s,%s,%s)',('pose',)),
      'complete':('public.complete_video_analysis_job(%s,%s,%s)',()),
      'fail':('public.record_video_analysis_job_failure(%s,%s,%s,%s,%s,%s)',('failure','analysis_runtime',True)),
    }
    expression,extra=calls[name]
    if connection is None:
      with self.connect() as conn:
        conn.execute("set local statement_timeout='4s'");conn.execute('set local role service_role')
        return self.control(name,job,attempt=attempt,worker=worker,connection=conn)
    return connection.execute('select '+expression+' as result',(job,worker,attempt,*extra)).fetchone()['result']

  def claim(self,worker='worker'):
    with self.connect() as conn:
      conn.execute('set local role service_role')
      return conn.execute('select * from public.claim_video_analysis_job(%s,60)',(worker,)).fetchall()

  def recover(self):
    with self.connect() as conn:
      conn.execute('set local role service_role')
      return conn.execute('select * from public.recover_expired_video_analysis_jobs()').fetchone()

  def test_live_publication_upserts_idempotently_and_updates_only_the_allowed_fields(self):
    video=self.video();job=self.job(video)
    first=self.publish(video,job,fields={'status':'processing','fps':29.97,'duration_ms':1200},result={'reps':1})
    attempt=uuid4();path=f'{self.user}/thumbnails/{video}-{attempt}-thumb-v3.jpg'
    source=self.sql('select storage_path from public.videos where id=%s',(video,))[0]['storage_path']
    args=(attempt,self.user,video,'thumbnail','videos',path,source,'image/jpeg',80,job,'worker',1)
    with self.connect() as connection:
      connection.execute('set local role service_role')
      connection.execute('select * from public.admit_private_media_generated_write(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(*args,1000000000,1000000000))
    with self.connect() as connection:
      connection.execute('set local role service_role')
      self.assertTrue(connection.execute('select public.observe_private_media_generated_write_success(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) as observed',args).fetchone()['observed'])
    second=self.publish(video,job,fields={'status':'completed','thumbnail_path':path},result={'reps':2})
    self.assertEqual(first['analysis']['id'],second['analysis']['id'])
    self.assertEqual(second['analysis']['result_json'],{'reps':2})
    self.assertEqual(second['video']['status'],'completed')
    self.assertEqual(second['video']['fps'],29.97)
    self.assertEqual(self.sql('select count(*) as n from public.analysis_results')[0]['n'],1)
    self.assertTrue(self.control('complete',job))

  def test_wrong_identity_generation_or_expired_lease_cannot_publish_or_control(self):
    for change in ('worker','attempt','video','cancelled','expired','infinite'):
      with self.subTest(change=change):
        video=self.video();job=self.job(video,attempt=2)
        worker='other' if change=='worker' else 'worker';attempt=1 if change=='attempt' else 2
        selected=self.video() if change=='video' else video
        if change=='cancelled':self.sql("update public.analysis_jobs set status='cancelled',lease_owner=null,lease_expires_at=null where id=%s",(job,))
        if change=='expired':self.sql("update public.analysis_jobs set lease_expires_at=clock_timestamp()-interval '1 second' where id=%s",(job,))
        if change=='infinite':self.sql("update public.analysis_jobs set lease_expires_at='infinity' where id=%s",(job,))
        self.assertIsNone(self.publish(selected,job,attempt=attempt,worker=worker,fields={'status':'failed'},result={'stale':True}))
        if change!='video':
          for name in ('renew','progress','complete','fail'):
            self.assertIn(self.control(name,job,attempt=attempt,worker=worker),(False,None))
        self.assertEqual(self.sql('select id from public.analysis_results where video_id=%s',(selected,)),[])

  def test_same_worker_old_attempt_cannot_complete_fail_renew_or_publish_new_attempt(self):
    video=self.video();job=self.job(video,attempt=2)
    before=self.sql('select * from public.analysis_jobs where id=%s',(job,))[0]
    for name in ('renew','progress','complete','fail'):self.assertIn(self.control(name,job,attempt=1),(False,None))
    self.assertIsNone(self.publish(video,job,attempt=1,result={'stale':True}))
    self.assertEqual(self.sql('select * from public.analysis_jobs where id=%s',(job,))[0],before)
    self.assertIsNotNone(self.publish(video,job,attempt=2,result={'current':True}))

  def test_all_resource_denials_block_metadata_results_and_control(self):
    for change in ('discarded','outbox','pruned','expired','infinite'):
      with self.subTest(change=change):
        video=self.video();job=self.job(video)
        if change=='discarded':self.sql('update public.videos set discarded_at=clock_timestamp() where id=%s',(video,))
        if change=='outbox':self.sql('insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values(%s,%s,ARRAY[]::text[])',(video,self.user))
        if change=='pruned':self.sql("update public.videos set storage_state='pruned' where id=%s",(video,))
        if change=='expired':self.sql("update public.videos set expires_at=clock_timestamp()-interval '1 second' where id=%s",(video,))
        if change=='infinite':self.sql("update public.videos set expires_at='infinity' where id=%s",(video,))
        before=self.sql('select to_jsonb(v) as snapshot from public.videos v where id=%s',(video,))[0]
        self.assertIsNone(self.publish(video,job,fields={'status':'processing','playback_path':f'{self.user}/new.mp4'},result={'late':True}))
        for name in ('renew','progress','complete','fail'):self.assertIn(self.control(name,job),(False,None))
        self.assertEqual(self.sql('select to_jsonb(v) as snapshot from public.videos v where id=%s',(video,))[0],before)

  def test_bad_fields_and_foreign_or_unsafe_paths_roll_back_entire_publication(self):
    video=self.video();job=self.job(video)
    variants=[{'status':'uploaded'},{'status':None},{'save_state':'saved'},{'discarded_at':None},
              {'user_id':str(self.other)},{'fps':0},{'fps':'NaN'},{'duration_ms':0},{'duration_ms':1.5},
              {'playback_path':f'{self.other}/foreign.mp4'},{'thumbnail_path':f'{self.user}/../bad.jpg'},
              {'original_storage_path':f'{self.user}/a//b'},{'thumbnail_path':f'{self.user}/bad.jpg\n'},
              {'thumbnail_path':f'\u00a0{self.user}/bad.jpg'},{'storage_optimized_at':'infinity'}]
    before=self.sql('select to_jsonb(v) as snapshot from public.videos v where id=%s',(video,))[0]
    for fields in variants:
      with self.subTest(fields=fields):
        with self.assertRaises(self.psycopg.Error):self.publish(video,job,fields={**fields,'storage_optimization_error':None},result={'invalid':True})
        self.assertEqual(self.sql('select to_jsonb(v) as snapshot from public.videos v where id=%s',(video,))[0],before)
        self.assertEqual(self.sql('select id from public.analysis_results where video_id=%s',(video,)),[])

  def test_busy_job_is_nowait_and_does_not_partially_publish(self):
    video=self.video();job=self.job(video)
    with self.connect() as holder:
      holder.execute('select id from public.analysis_jobs where id=%s for update',(job,))
      started=time.monotonic()
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):self.publish(video,job,result={'late':True})
      self.assertLess(time.monotonic()-started,2)
    self.assertEqual(self.sql('select id from public.analysis_results'),[])

  def test_lease_expiring_while_waiting_for_video_lock_is_checked_after_wait(self):
    video=self.video();deadline=datetime.now(timezone.utc)+timedelta(seconds=.5);job=self.job(video,expiry=deadline)
    waiter={};ready=threading.Event()
    def progress():
      with self.connect() as conn:
        conn.execute("set local statement_timeout='4s'");conn.execute('set local role service_role')
        waiter['pid']=conn.info.backend_pid;ready.set()
        return self.control('progress',job,connection=conn)
    with ThreadPoolExecutor(max_workers=1) as pool,self.connect() as holder:
      holder.execute('select id from public.videos where id=%s for update',(video,))
      future=pool.submit(progress)
      try:
        self.assertTrue(ready.wait(2));self.wait_blocked(waiter['pid'],holder.info.backend_pid)
        while datetime.now(timezone.utc)<=deadline:time.sleep(.01)
      finally:holder.commit()
      self.assertFalse(future.result(timeout=5))
    self.assertNotEqual(self.sql('select stage from public.analysis_jobs where id=%s',(job,))[0]['stage'],'pose')

  def test_publish_first_then_revoke_commits_revocation_last(self):
    video=self.video();job=self.job(video);ready=threading.Event();waiter={}
    def revoke():
      with self.connect() as conn:
        conn.execute("set local statement_timeout='4s'");conn.execute('set local role service_role')
        waiter['pid']=conn.info.backend_pid;ready.set()
        return conn.execute('select * from public.revoke_video_media(%s,%s,false)',(self.user,[video])).fetchall()
    with ThreadPoolExecutor(max_workers=1) as pool,self.connect() as writer:
      writer.execute('set local role service_role')
      self.assertIsNotNone(self.publish(video,job,fields={'status':'completed'},result={'reps':1},connection=writer))
      future=pool.submit(revoke)
      try:self.assertTrue(ready.wait(2));self.wait_blocked(waiter['pid'],writer.info.backend_pid)
      finally:writer.commit()
      self.assertEqual(len(future.result(timeout=5)),1)
    self.assertIsNotNone(self.sql('select discarded_at from public.videos where id=%s',(video,))[0]['discarded_at'])
    self.assertEqual(self.sql('select status from public.analysis_jobs where id=%s',(job,))[0]['status'],'cancelled')

  def test_revoke_first_denies_waiting_publisher(self):
    video=self.video();job=self.job(video);ready=threading.Event();waiter={}
    def publish():
      with self.connect() as conn:
        conn.execute("set local statement_timeout='4s'");conn.execute('set local role service_role')
        waiter['pid']=conn.info.backend_pid;ready.set()
        return self.publish(video,job,fields={'status':'completed'},result={'late':True},connection=conn)
    with ThreadPoolExecutor(max_workers=1) as pool,self.connect() as revoker:
      revoker.execute('set local role service_role')
      revoker.execute('select * from public.revoke_video_media(%s,%s,false)',(self.user,[video])).fetchall()
      future=pool.submit(publish)
      try:self.assertTrue(ready.wait(2));self.wait_blocked(waiter['pid'],revoker.info.backend_pid)
      finally:revoker.commit()
      self.assertIsNone(future.result(timeout=5))
    self.assertEqual(self.sql('select id from public.analysis_results'),[])

  def test_claim_only_admits_live_resource_and_returns_incremented_generation(self):
    for change in ('discarded','outbox','pruned','expired','infinite'):
      with self.subTest(change=change):
        video=self.video(status='queued');self.job(video,status='queued',attempt=0)
        if change=='discarded':self.sql('update public.videos set discarded_at=clock_timestamp() where id=%s',(video,))
        if change=='outbox':self.sql('insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values(%s,%s,ARRAY[]::text[])',(video,self.user))
        if change=='pruned':self.sql("update public.videos set storage_state='pruned' where id=%s",(video,))
        if change=='expired':self.sql("update public.videos set expires_at=clock_timestamp()-interval '1 second' where id=%s",(video,))
        if change=='infinite':self.sql("update public.videos set expires_at='infinity' where id=%s",(video,))
        self.assertEqual(self.claim(),[])
        self.assertEqual(self.sql('select status from public.videos where id=%s',(video,))[0]['status'],'queued')
    video=self.video(status='queued');job=self.job(video,status='queued',attempt=0)
    claimed=self.claim()
    self.assertEqual(len(claimed),1);self.assertEqual(claimed[0]['id'],job);self.assertEqual(claimed[0]['attempt_count'],1)
    self.assertIsNotNone(self.publish(video,job,result={'claimed':True}))

  def test_expired_queued_and_future_retry_jobs_release_quota_and_allow_retention(self):
    for state in ('queued','retry_wait'):
      with self.subTest(state=state):
        video=self.video(status='queued',save_state='pending',is_saved=False)
        job=self.job(video,status=state,attempt=0 if state=='queued' else 1)
        self.sql("update public.analysis_jobs set available_at=clock_timestamp()+interval '1 hour' where id=%s",(job,))
        self.sql("update public.videos set expires_at=clock_timestamp()-interval '1 second' where id=%s",(video,))
        self.assertEqual(self.claim(),[])
        self.assertEqual(self.sql('select status from public.analysis_jobs where id=%s',(job,))[0]['status'],'cancelled')
        self.assertEqual(self.sql("select count(*) as n from public.analysis_jobs where video_id=%s and status in ('queued','processing','retry_wait')",(video,))[0]['n'],0)
        with self.connect() as conn:
          conn.execute('set local role service_role')
          task=conn.execute('select * from public.claim_expired_video_deletion(%s)',(video,)).fetchone()
        self.assertEqual(task['video_id'],video)
        self.assertEqual(self.sql('select id from public.videos where id=%s',(video,)),[])

  def test_recovery_cancels_revoked_without_reviving_video_and_preserves_live_retry(self):
    for change in ('discarded','outbox','pruned','expired'):
      video=self.video(status='completed');job=self.job(video,expiry=datetime.now(timezone.utc)-timedelta(seconds=1))
      if change=='discarded':self.sql('update public.videos set discarded_at=clock_timestamp() where id=%s',(video,))
      if change=='outbox':self.sql('insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values(%s,%s,ARRAY[]::text[])',(video,self.user))
      if change=='pruned':self.sql("update public.videos set storage_state='pruned' where id=%s",(video,))
      if change=='expired':self.sql("update public.videos set expires_at=clock_timestamp()-interval '1 second' where id=%s",(video,))
      self.recover()
      self.assertEqual(self.sql('select status from public.videos where id=%s',(video,))[0]['status'],'completed')
      self.assertEqual(self.sql('select status from public.analysis_jobs where id=%s',(job,))[0]['status'],'cancelled')
    video=self.video();job=self.job(video,expiry=datetime.now(timezone.utc)-timedelta(seconds=1))
    self.assertEqual(self.recover()['retried_count'],1)
    self.assertEqual(self.sql('select status from public.videos where id=%s',(video,))[0]['status'],'queued')

  def test_old_unbound_rpc_overloads_are_inaccessible_to_service_and_clients(self):
    signatures=['renew_video_analysis_job_lease(uuid,text,integer)','complete_video_analysis_job(uuid,text)',
                'report_video_analysis_job_progress(uuid,text,text)','record_video_analysis_job_failure(uuid,text,text,text,boolean)',
                'fail_video_analysis_job(uuid,text,text)']
    for role in ('service_role','anon','authenticated','public_probe'):
      for signature in signatures:
        self.assertFalse(self.sql('select has_function_privilege(%s,%s,\'EXECUTE\') as allowed',(role,'public.'+signature))[0]['allowed'])

  def test_new_rpc_privileges_invoker_and_empty_search_path(self):
    signatures=['lock_video_analysis_attempt(uuid,uuid,text,integer)','publish_video_analysis(uuid,uuid,text,integer,jsonb,text,jsonb)',
                'renew_video_analysis_job_lease(uuid,text,integer,integer)','complete_video_analysis_job(uuid,text,integer)',
                'report_video_analysis_job_progress(uuid,text,integer,text)','record_video_analysis_job_failure(uuid,text,integer,text,text,boolean)',
                'claim_video_analysis_job(text,integer)','recover_expired_video_analysis_jobs()']
    for signature in signatures:
      row=self.sql('select prosecdef,proconfig from pg_proc where oid=%s::regprocedure',('public.'+signature,))[0]
      self.assertFalse(row['prosecdef']);self.assertIn('search_path=""',row['proconfig'])
      self.assertTrue(self.sql('select has_function_privilege(\'service_role\',%s,\'EXECUTE\') as allowed',('public.'+signature,))[0]['allowed'])
      for role in ('anon','authenticated','public_probe'):
        self.assertFalse(self.sql('select has_function_privilege(%s,%s,\'EXECUTE\') as allowed',(role,'public.'+signature))[0]['allowed'])



  def begin_owner(self,user=None,connection=None):
    if connection is not None:
      return connection.execute('select * from public.begin_private_media_owner_deletion(%s)',(user or self.user,)).fetchall()
    with self.connect() as conn:
      conn.execute('set local role service_role');return self.begin_owner(user,conn)

  def owner_snapshot(self,job):
    return self.sql('select to_jsonb(j) as data from public.analysis_jobs j where id=%s',(job,))[0]['data']

  def prepare_two_owners(self,state='queued',expired=False):
    first=self.video(status=state);second=self.video(owner=self.other,status=state)
    expiry=datetime.now(timezone.utc)-timedelta(seconds=1) if expired else None
    a=self.job(first,status=state,attempt=1 if state=='processing' else 0,expiry=expiry)
    z=self.job(second,status=state,attempt=1 if state=='processing' else 0,expiry=expiry)
    self.sql("update public.analysis_jobs set available_at=clock_timestamp()-interval '2 minutes' where id=%s",(a,))
    self.sql("update public.analysis_jobs set available_at=clock_timestamp()-interval '1 minute' where id=%s",(z,))
    return first,a,second,z

  def test_owner_deletion_denies_enqueue_reuse_for_every_active_job_state(self):
    rows=[]
    for state in ('queued','processing','retry_wait'):
      video=self.video(status='queued');job=self.job(video,status=state)
      self.assertEqual(self.enqueue(video)[0]['id'],job)
      rows.append((video,job,self.owner_snapshot(job)))
    self.begin_owner()
    for video,job,before in rows:
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.enqueue(video)
      self.assertEqual(self.owner_snapshot(job),before)

  def test_owner_deletion_denies_new_enqueue_and_preserves_verified_reservation(self):
    video=self.queueable_video();before=self.sql('select to_jsonb(v) as data from public.videos v where id=%s',(video,))[0]
    self.begin_owner()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.enqueue(video)
    self.assertEqual(self.sql('select to_jsonb(v) as data from public.videos v where id=%s',(video,))[0],before)
    self.assertEqual(self.sql('select state from public.upload_reservations')[0]['state'],'verified')

  def test_claim_cancels_deleting_first_owner_and_claims_other_owner(self):
    video,a,other,z=self.prepare_two_owners();before=self.sql('select to_jsonb(v) as data from public.videos v where id=%s',(video,))[0]
    self.begin_owner();claimed=self.claim()
    self.assertEqual([r['id'] for r in claimed],[z]);self.assertEqual(claimed[0]['attempt_count'],1)
    old=self.owner_snapshot(a);self.assertEqual(old['status'],'cancelled');self.assertEqual(old['attempt_count'],0)
    self.assertEqual(old['failure_class'],'owner_unavailable');self.assertIsNone(old['lease_owner'])
    self.assertEqual(self.sql('select to_jsonb(v) as data from public.videos v where id=%s',(video,))[0],before)

  def test_claim_cancels_missing_owner_without_creating_it(self):
    _,a,_,z=self.prepare_two_owners()
    # Disposable fault fixture: emulate legacy owner metadata missing at cutover.
    self.sql('truncate public.private_media_owners cascade')
    self.sql('insert into public.private_media_owners(user_id) values(%s)',(self.other,))
    self.assertEqual([r['id'] for r in self.claim()],[z]);self.assertEqual(self.owner_snapshot(a)['status'],'cancelled')
    self.assertEqual(self.sql('select user_id from public.private_media_owners where user_id=%s',(self.user,)),[])

  def test_claim_cancels_deleting_future_retry_instead_of_pinning_quota(self):
    _,a,_,z=self.prepare_two_owners(state='retry_wait')
    self.sql("update public.analysis_jobs set available_at=clock_timestamp()+interval '1 hour' where id=%s",(a,))
    self.begin_owner();self.assertEqual([r['id'] for r in self.claim()],[z])
    self.assertEqual(self.claim(),[])
    self.assertEqual(self.owner_snapshot(a)['status'],'cancelled')

  def test_claim_skips_busy_live_owner_and_can_claim_it_after_release(self):
    _,a,_,z=self.prepare_two_owners();before=self.owner_snapshot(a)
    with self.connect() as holder:
      holder.execute('select user_id from public.private_media_owners where user_id=%s for update',(self.user,))
      self.assertEqual([r['id'] for r in self.claim()],[z]);self.assertEqual(self.owner_snapshot(a),before)
      holder.rollback()
    self.assertEqual([r['id'] for r in self.claim()],[a])

  def test_uncommitted_deletion_does_not_cancel_and_rollback_restores_admission(self):
    _,a,_,z=self.prepare_two_owners();before=self.owner_snapshot(a)
    with self.connect() as holder:
      holder.execute('set local role service_role');self.begin_owner(connection=holder)
      self.assertEqual([r['id'] for r in self.claim()],[z]);self.assertEqual(self.owner_snapshot(a),before)
      holder.rollback()
    self.assertEqual([r['id'] for r in self.claim()],[a])

  def test_busy_deletion_commit_is_observed_on_later_claim(self):
    _,a,_,z=self.prepare_two_owners()
    with self.connect() as holder:
      holder.execute('set local role service_role');self.begin_owner(connection=holder)
      self.assertEqual([r['id'] for r in self.claim()],[z]);self.assertEqual(self.owner_snapshot(a)['status'],'queued')
      holder.commit()
    self.assertEqual(self.claim(),[]);self.assertEqual(self.owner_snapshot(a)['status'],'cancelled')

  def test_recovery_cancels_deleting_owner_and_preserves_other_retry_failure_counts(self):
    video,a,_,z=self.prepare_two_owners(state='processing',expired=True)
    third=self.video(owner=self.other);terminal=self.job(third,attempt=3,expiry=datetime.now(timezone.utc)-timedelta(seconds=1))
    before=self.sql('select to_jsonb(v) as data from public.videos v where id=%s',(video,))[0]
    self.begin_owner();self.assertEqual(self.recover(),{'retried_count':1,'failed_count':1})
    self.assertEqual(self.owner_snapshot(a)['status'],'cancelled');self.assertEqual(self.owner_snapshot(a)['failure_class'],'owner_unavailable')
    self.assertEqual(self.owner_snapshot(z)['status'],'retry_wait');self.assertEqual(self.owner_snapshot(terminal)['status'],'failed')
    self.assertEqual(self.sql('select to_jsonb(v) as data from public.videos v where id=%s',(video,))[0],before)

  def test_recovery_skips_busy_owner_without_starving_other_expired_job(self):
    _,a,_,z=self.prepare_two_owners(state='processing',expired=True);before=self.owner_snapshot(a)
    with self.connect() as holder:
      holder.execute('select user_id from public.private_media_owners where user_id=%s for update',(self.user,))
      self.assertEqual(self.recover(),{'retried_count':1,'failed_count':0});self.assertEqual(self.owner_snapshot(a),before)
      holder.rollback()
    self.assertEqual(self.recover(),{'retried_count':1,'failed_count':0});self.assertEqual(self.owner_snapshot(a)['status'],'retry_wait')

  def test_deleted_owner_cannot_control_or_publish_current_worker_attempt(self):
    video=self.video();job=self.job(video);before=self.owner_snapshot(job)
    prior=self.sql('select to_jsonb(v) as data from public.videos v where id=%s',(video,))[0]
    self.begin_owner()
    for name in ('renew','progress','complete','fail'):
      with self.subTest(name=name):self.assertIn(self.control(name,job),(False,None))
    self.assertIsNone(self.publish(video,job,fields={'status':'completed'},result={'late':True}))
    self.assertEqual(self.owner_snapshot(job),before);self.assertEqual(self.sql('select to_jsonb(v) as data from public.videos v where id=%s',(video,))[0],prior)
    self.assertEqual(self.sql('select id from public.analysis_results'),[])

  def test_direct_job_and_result_writes_deny_deleted_owner_but_cleanup_remains(self):
    video=self.video();job=self.job(video)
    result=self.sql("insert into public.analysis_results(video_id,result_json) values(%s,'{}') returning id",(video,))[0]['id']
    self.begin_owner()
    for command,args in [("insert into public.analysis_jobs(video_id,status) values(%s,'queued')",(video,)),
        ('update public.analysis_jobs set attempt_count=attempt_count+1 where id=%s',(job,)),
        ("insert into public.analysis_results(video_id,model_version,result_json) values(%s,'late','{}')",(video,)),
        ("update public.analysis_results set result_json=jsonb_build_object('late',true) where id=%s",(result,))]:
      with self.subTest(command=command),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.sql(command,args)
    self.assertEqual(self.sql('select public.cancel_video_analysis_jobs(%s) as n',(video,))[0]['n'],1)
    self.assertEqual(self.sql('select public.cancel_video_analysis_jobs(%s) as n',(video,))[0]['n'],0)
    self.sql('delete from public.analysis_results where id=%s',(result,));self.assertEqual(self.sql('select id from public.analysis_results'),[])

  def test_cancel_only_exception_cannot_hide_new_attempt_schedule_or_identity(self):
    video=self.video();job=self.job(video);other=self.video(owner=self.other)
    self.begin_owner()
    for fields in ('attempt_count=attempt_count+1',"available_at=clock_timestamp()+interval '1 hour'",f"video_id='{other}'"):
      with self.subTest(fields=fields),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.sql("update public.analysis_jobs set status='cancelled',stage='failed',lease_owner=null,lease_expires_at=null,completed_at=clock_timestamp(),"+fields+' where id=%s',(job,))
    self.assertEqual(self.owner_snapshot(job)['status'],'processing')

  def test_result_identity_is_immutable_and_missing_video_cannot_bypass_guard(self):
    video=self.video();other=self.video(owner=self.other)
    result=self.sql("insert into public.analysis_results(video_id,result_json) values(%s,'{}') returning id",(video,))[0]['id']
    for fields in ('id=gen_random_uuid()',"model_version='changed'",f"video_id='{other}'"):
      with self.subTest(fields=fields),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.sql('update public.analysis_results set '+fields+' where id=%s',(result,))
    for command in ("insert into public.analysis_jobs(video_id) values(%s)","insert into public.analysis_results(video_id,result_json) values(%s,'{}')"):
      with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):self.sql(command,(uuid4(),))

  def test_direct_job_and_result_publication_reject_current_resource_denials(self):
    for fields in ("discarded_at=clock_timestamp()","storage_state='pruned'","expires_at=clock_timestamp()-interval '1 second'","expires_at='infinity'",'outbox'):
      video=self.video()
      if fields=='outbox':self.sql("insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values(%s,%s,'{}')",(video,self.user))
      else:self.sql('update public.videos set '+fields+' where id=%s',(video,))
      with self.subTest(fields=fields):
        with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.job(video,status='queued')
        with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.sql("insert into public.analysis_results(video_id,result_json) values(%s,'{}')",(video,))

  def test_owner_cancellation_and_next_claim_roll_back_atomically(self):
    _,a,_,z=self.prepare_two_owners();self.begin_owner();before_a=self.owner_snapshot(a);before_z=self.owner_snapshot(z)
    with self.connect() as connection:
      connection.execute('set local role service_role')
      self.assertEqual(connection.execute("select id from public.claim_video_analysis_job('rollback',60)").fetchone()['id'],z)
      connection.rollback()
    self.assertEqual(self.owner_snapshot(a),before_a);self.assertEqual(self.owner_snapshot(z),before_z)
    self.assertEqual([r['id'] for r in self.claim()],[z])

  def test_owner_work_probe_is_service_only_invoker_and_distinguishes_busy(self):
    names=['private_media_owner_work_state(uuid)','assert_private_media_video_work(uuid)','fence_owner_analysis_job()','fence_owner_analysis_result()']
    for name in names:
      row=self.sql('select prosecdef,proconfig from pg_proc where oid=%s::regprocedure',('public.'+name,))[0]
      self.assertFalse(row['prosecdef']);self.assertIn('search_path=""',row['proconfig'])
      for role in ('anon','authenticated','public_probe'):
        self.assertFalse(self.sql("select has_function_privilege(%s,%s,'execute') as allowed",(role,'public.'+name))[0]['allowed'])
    self.assertEqual(self.sql('select public.private_media_owner_work_state(%s) as state',(self.user,))[0]['state'],'active')
    self.assertEqual(self.sql('select public.private_media_owner_work_state(%s) as state',(uuid4(),))[0]['state'],'unavailable')
    with self.connect() as holder:
      holder.execute('select user_id from public.private_media_owners where user_id=%s for update',(self.user,))
      self.assertEqual(self.sql('select public.private_media_owner_work_state(%s) as state',(self.user,))[0]['state'],'busy')



  def test_worker_preflight_waits_for_live_owner_and_keeps_valid_attempt(self):
    video=self.video();job=self.job(video);ready=threading.Event();waiter={}
    def progress():
      with self.connect() as connection:
        connection.execute("set local statement_timeout='4s'");connection.execute('set local role service_role')
        waiter['pid']=connection.info.backend_pid;ready.set()
        return self.control('progress',job,connection=connection)
    with ThreadPoolExecutor(1) as pool,self.connect() as holder:
      holder.execute('select user_id from public.private_media_owners where user_id=%s for update',(self.user,))
      task=pool.submit(progress)
      try:self.assertTrue(ready.wait(2));self.wait_blocked(waiter['pid'],holder.info.backend_pid);self.assertFalse(task.done())
      finally:holder.rollback()
      self.assertTrue(task.result(timeout=4))
    self.assertEqual(self.owner_snapshot(job)['stage'],'pose')

  def test_owner_deletion_committing_during_preflight_wait_denies_publication(self):
    video=self.video();job=self.job(video);ready=threading.Event();waiter={}
    def publish():
      with self.connect() as connection:
        connection.execute("set local statement_timeout='4s'");connection.execute('set local role service_role')
        waiter['pid']=connection.info.backend_pid;ready.set()
        return self.publish(video,job,result={'late':True},connection=connection)
    with ThreadPoolExecutor(1) as pool,self.connect() as holder:
      holder.execute('set local role service_role');self.begin_owner(connection=holder)
      task=pool.submit(publish)
      try:self.assertTrue(ready.wait(2));self.wait_blocked(waiter['pid'],holder.info.backend_pid)
      finally:holder.commit()
      self.assertIsNone(task.result(timeout=4))
    self.assertEqual(self.sql('select id from public.analysis_results'),[])


if __name__=='__main__':unittest.main()
