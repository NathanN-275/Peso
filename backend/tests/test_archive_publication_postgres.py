from __future__ import annotations

import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import test_video_revocation_postgres as fixture
import test_generated_media_writes_postgres as generated


@unittest.skipUnless(fixture.DATABASE_URL, "Dedicated video-revocation Postgres database is not configured.")
class ArchivePublicationPostgresTest(unittest.TestCase):
  connect = classmethod(fixture.VideoRevocationPostgresTest.connect.__func__)
  setUp = fixture.VideoRevocationPostgresTest.setUp
  sql = fixture.VideoRevocationPostgresTest.sql
  video = fixture.VideoRevocationPostgresTest.video
  archive = fixture.VideoRevocationPostgresTest.archive
  rpc = fixture.VideoRevocationPostgresTest.rpc
  wait_blocked = fixture.VideoRevocationPostgresTest.wait_blocked
  run_sql = generated.GeneratedMediaWritesPostgresTest.run_sql

  @classmethod
  def setUpClass(cls):
    fixture.VideoRevocationPostgresTest.setUpClass.__func__(cls)
    paths=list((Path(__file__).resolve().parents[2]/'supabase/migrations').glob('*_owner_archive_publication_fence.sql'))
    if len(paths)!=1:raise RuntimeError('Exactly one CLI-generated owner archive migration is required.')
    with cls.connect(autocommit=True) as connection:
      if connection.execute("select to_regprocedure('public.fence_owner_saved_lift_export()') as function").fetchone()['function'] is None:
        connection.execute(paths[0].read_text())

  def lift(self, **fields):
    owner=fields.pop('owner',None)
    video = self.video(owner=owner)
    self.sql("insert into public.analysis_results(video_id,result_json) values (%s,'{}')", (video,))
    if fields:
      self.sql('update public.videos set '+','.join(key+'=%s' for key in fields)+' where id=%s',(*fields.values(),video))
    return video

  def insert(self, ids, *, owner=None, job=None, status="queued", path=None, expires=None, completed=None):
    job = job or uuid4()
    with self.connect() as connection:
      connection.execute("set local role service_role")
      return connection.execute("insert into public.saved_lift_export_jobs(id,user_id,video_ids,status,archive_path,completed_at,expires_at,attempts,started_at) values (%s,%s,%s,%s,%s,%s,%s,%s,%s) returning id",
                                (job,owner or self.user,ids,status,path,completed,expires,1 if status=="processing" else 0,datetime.now(timezone.utc) if status=="processing" else None)).fetchone()["id"]

  def complete(self, job, *, expires=None):
    import test_archive_writes_postgres as archive_writes
    helper=archive_writes.ArchiveWritesPostgresTest
    owner=self.sql('select user_id from public.saved_lift_export_jobs where id=%s',(job,))[0]['user_id']
    plan=helper.plan(self,job,owner)
    args=helper.arguments(self,plan)
    helper.admit(self,args);helper.observe(self,args)
    helper.publish(self,args)
    return [{'id':job}]

  def test_service_only_trigger_is_invoker_empty_search_path(self):
    proc = self.sql("select prosecdef,proconfig from pg_proc where oid='public.fence_saved_lift_export_publication()'::regprocedure")[0]
    self.assertFalse(proc["prosecdef"]); self.assertEqual(proc["proconfig"], ['search_path=""'])
    for role in ("anon", "authenticated", "public_probe"):
      self.assertFalse(self.sql("select has_function_privilege(%s,'public.fence_saved_lift_export_publication()','execute') as allowed",(role,))[0]["allowed"])
    self.assertTrue(self.sql("select has_function_privilege('service_role','public.fence_saved_lift_export_publication()','execute') as allowed")[0]["allowed"])

  def test_selection_rejects_null_duplicate_multidimensional_and_over_limit(self):
    video = self.lift()
    for ids in (None,[],[None],[video,video],[[video]],[uuid4() for _ in range(51)]):
      with self.subTest(ids=ids), self.assertRaises(self.psycopg.errors.InvalidParameterValue):
        self.insert(ids)
    self.assertEqual(self.sql("select id from public.saved_lift_export_jobs"), [])

  def test_whole_selection_checks_owner_existence_saved_analysis_and_outbox(self):
    live = self.lift()
    foreign = self.lift(owner=self.other)
    pending = self.lift(save_state="pending",is_saved=False)
    no_analysis = self.video()
    outboxed = self.lift()
    self.sql("insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values (%s,%s,'{}')", (outboxed,self.user))
    for bad in (uuid4(), foreign, pending, no_analysis, outboxed):
      with self.subTest(bad=bad), self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.insert([live,bad])
    self.assertEqual(self.sql("select id from public.saved_lift_export_jobs"), [])

  def test_nil_job_or_owner_identity_rejected(self):
    video = self.lift()
    with self.assertRaises(self.psycopg.errors.InvalidParameterValue): self.insert([video],job=UUID(int=0))
    with self.assertRaises(self.psycopg.errors.InvalidParameterValue): self.insert([video],owner=UUID(int=0))

  def test_legacy_saved_flags_and_null_deadline_are_preserved(self):
    first=self.lift(save_state="saved",is_saved=False,expires_at=None)
    second=self.lift(save_state="pending",is_saved=True,expires_at=None)
    self.assertTrue(self.insert([second,first]))

  def test_all_fifty_members_accepted_once_in_reverse_order(self):
    videos=[self.lift() for _ in range(50)]
    self.assertTrue(self.insert(list(reversed(videos))))

  def test_discarded_pruned_elapsed_and_nonfinite_member_denied(self):
    fields=[{"discarded_at": datetime.now(timezone.utc)}, {"storage_state":"pruned"},
            {"expires_at":datetime.now(timezone.utc)-timedelta(seconds=1)},
            {"expires_at":"infinity"},{"expires_at":"-infinity"},
            {"save_state":None,"is_saved":False}]
    for values in fields:
      video=self.lift(**values)
      with self.subTest(values=values), self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState): self.insert([video])

  def test_completed_direct_insert_needs_observed_attempt_even_with_valid_legacy_path(self):
    video=self.lift(); now=datetime.now(timezone.utc)
    for path,done,expiry in [("wrong",now,now+timedelta(hours=1)),("valid",None,now+timedelta(hours=1)),
                             ("valid","infinity",now+timedelta(hours=1)),("valid",now,"infinity"),
                             ("valid",now,None),("valid",now,now-timedelta(seconds=1))]:
      job=uuid4(); actual=f"{self.user}/{job}.zip" if path=="valid" else f"{self.user}/wrong.zip"
      with self.subTest(path=path,done=done,expiry=expiry), self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.insert([video],job=job,status="completed",path=actual,completed=done,expires=expiry)
    job=uuid4()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.insert([video],job=job,status="completed",path=f"{self.user}/{job}.zip",completed=now,expires=now+timedelta(hours=1))

  def test_queued_and_processing_cannot_publish_archive_path(self):
    for state in ("queued","processing"):
      video=self.lift();job=uuid4()
      with self.subTest(state=state),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.insert([video],job=job,status=state,path=f"{self.user}/{job}.zip")

  def test_immutable_identity_and_membership(self):
    video=self.lift(); other=self.lift();job=self.insert([video])
    for clause,values in [("id=%s",(uuid4(),)),("user_id=%s",(self.other,)),("video_ids=%s",([other],))]:
      with self.subTest(clause=clause),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.sql("update public.saved_lift_export_jobs set "+clause+" where id=%s",values+(job,))
    self.assertEqual(self.sql("select video_ids from public.saved_lift_export_jobs where id=%s",(job,))[0]["video_ids"],[video])

  def test_expired_and_failed_rows_never_reopen(self):
    for terminal in ("expired","failed"):
      video=self.lift();job=self.insert([video]);self.sql("update public.saved_lift_export_jobs set status=%s where id=%s",(terminal,job))
      for state in ("queued","processing","completed"):
        with self.subTest(terminal=terminal,state=state),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
          self.sql("update public.saved_lift_export_jobs set status=%s where id=%s",(state,job))
      if terminal=="expired":
        with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
          self.sql("update public.saved_lift_export_jobs set status='failed' where id=%s",(job,))

  def test_revoke_processing_archive_prevents_completion_or_failure_resurrection(self):
    video=self.lift();job=self.insert([video],status="processing")
    task=self.rpc([video])[0]
    self.assertIn(f"{self.user}/{job}.zip",task["archive_paths"])
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState): self.complete(job)
    self.assertEqual(self.sql("select status,archive_path from public.saved_lift_export_jobs where id=%s",(job,))[0],{"status":"expired","archive_path":None})

  def test_completion_rechecks_all_members_and_does_not_extend_completed_archive(self):
    first=self.lift();second=self.lift();job=self.insert([second,first],status="processing")
    self.sql("update public.videos set expires_at=clock_timestamp()-interval '1 second' where id=%s",(second,))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState): self.complete(job)
    self.sql("update public.videos set expires_at=null where id=%s",(second,));self.assertEqual(len(self.complete(job)),1)
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState): self.complete(job)

  def test_stale_worker_failure_cannot_overwrite_completed_archive(self):
    video=self.lift();job=self.insert([video],status="processing");self.complete(job)
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.sql("update public.saved_lift_export_jobs set status='failed',archive_path=null,failure_code='generation_failed' where id=%s",(job,))
    self.assertEqual(self.sql("select status from public.saved_lift_export_jobs where id=%s",(job,))[0]["status"],"completed")
    self.sql("update public.saved_lift_export_jobs set status='failed',archive_path=null,failure_code='archive_missing' where id=%s",(job,))
    self.assertEqual(self.sql("select status from public.saved_lift_export_jobs where id=%s",(job,))[0]["status"],"failed")

  def test_busy_member_lock_fails_fast_without_archive_transition(self):
    video=self.lift();job=self.insert([video],status="processing")
    with self.connect() as revoker:
      revoker.execute("select id from public.videos where id=%s for update",(video,))
      started=time.monotonic()
      with self.assertRaises(self.psycopg.errors.LockNotAvailable): self.complete(job)
      self.assertLess(time.monotonic()-started,2)
    self.assertEqual(self.sql("select status from public.saved_lift_export_jobs where id=%s",(job,))[0]["status"],"processing")
    self.assertEqual(len(self.complete(job)),1)

  def test_completion_after_archive_row_wait_rechecks_wall_clock_deadline(self):
    video=self.lift(expires_at=datetime.now(timezone.utc)+timedelta(seconds=1))
    job=self.insert([video],status="processing");ready=threading.Event();waiter={}
    def publish():
      with self.connect() as connection:
        connection.execute("set local statement_timeout='5s'");connection.execute("set local role service_role")
        waiter["pid"]=connection.info.backend_pid;ready.set()
        return connection.execute("update public.saved_lift_export_jobs set status='completed',archive_path=user_id::text||'/'||id::text||'.zip',completed_at=clock_timestamp(),expires_at=clock_timestamp()+interval '1 hour' where id=%s returning id",(job,)).fetchall()
    with ThreadPoolExecutor(max_workers=1) as pool,self.connect() as holder:
      holder.execute("select id from public.saved_lift_export_jobs where id=%s for update",(job,))
      future=pool.submit(publish)
      try:
        self.assertTrue(ready.wait(3));self.wait_blocked(waiter["pid"],holder.info.backend_pid)
        time.sleep(1.1)
      finally: holder.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):future.result(timeout=5)
    self.assertEqual(self.sql("select status from public.saved_lift_export_jobs where id=%s",(job,))[0]["status"],"processing")


  def begin_owner_deletion(self, owner=None, connection=None):
    if connection is not None:
      return connection.execute('select * from public.begin_private_media_owner_deletion(%s)',(owner or self.user,)).fetchone()
    with self.connect() as connection:
      connection.execute("set local statement_timeout='4s'");connection.execute('set local role service_role')
      return self.begin_owner_deletion(owner,connection)

  def terminal_update(self, job, *, state='expired', failure=None, complete=False):
    with self.connect() as connection:
      connection.execute("set local statement_timeout='4s'");connection.execute('set local role service_role')
      if complete:
        return connection.execute("update public.saved_lift_export_jobs set status=%s,archive_path=null,failure_code=%s,completed_at=clock_timestamp(),expires_at=null where id=%s returning id",(state,failure,job)).fetchall()
      return connection.execute('update public.saved_lift_export_jobs set status=%s,archive_path=null where id=%s returning id',(state,job)).fetchall()

  def test_deleting_owner_cannot_admit_any_archive_state(self):
    video=self.lift();self.begin_owner_deletion();now=datetime.now(timezone.utc)
    for state in ('queued','processing','completed','failed','expired'):
      job=uuid4()
      with self.subTest(state=state),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.insert([video],job=job,status=state,path=f'{self.user}/{job}.zip' if state=='completed' else None,
                    completed=now if state=='completed' else None,expires=now+timedelta(hours=1) if state=='completed' else None)
    self.assertEqual(self.sql('select id from public.saved_lift_export_jobs'),[])

  def test_deleting_owner_cannot_start_or_publish_existing_archive(self):
    video=self.lift();queued=self.insert([video]);processing=self.insert([video],status='processing')
    completed=self.insert([video],status='processing');self.complete(completed)
    before=self.sql('select * from public.saved_lift_export_jobs order by id');self.begin_owner_deletion()
    mutations=[("update public.saved_lift_export_jobs set status='processing',attempts=1,started_at=clock_timestamp() where id=%s",(queued,)),
               ("update public.saved_lift_export_jobs set status='completed',archive_path=user_id::text||'/'||id::text||'.zip',completed_at=clock_timestamp(),expires_at=clock_timestamp()+interval '1 hour' where id=%s",(processing,)),
               ("update public.saved_lift_export_jobs set status='completed' where id=%s",(completed,))]
    for sql,args in mutations:
      with self.subTest(sql=sql),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.sql(sql,args)
    self.assertEqual(self.sql('select * from public.saved_lift_export_jobs order by id'),before)

  def test_missing_owner_denies_insert_and_publication_but_allows_expiry(self):
    video=self.lift();job=self.insert([video],status='processing')
    # Synthetic missing-owner fault only: owner rows have no Auth/video FK.
    self.sql('truncate public.private_media_owners cascade')
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.insert([video])
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.complete(job)
    self.assertTrue(self.terminal_update(job));self.assertTrue(self.terminal_update(job))
    self.assertEqual(self.sql('select count(*) as n from public.private_media_owners')[0]['n'],0)

  def test_expire_cleanup_and_replay_remain_possible_for_every_old_state(self):
    video=self.lift();jobs=[]
    for state in ('queued','processing','completed','failed'):
      job=self.insert([video],status='processing' if state=='completed' else state)
      if state=='completed':self.complete(job)
      jobs.append(job)
    self.begin_owner_deletion()
    for job in jobs:
      with self.subTest(job=job):
        self.assertTrue(self.terminal_update(job));self.assertTrue(self.terminal_update(job))
        self.assertEqual(self.sql('select status,archive_path from public.saved_lift_export_jobs where id=%s',(job,))[0],{'status':'expired','archive_path':None})

  def test_failure_cleanup_and_replay_survive_owner_deletion(self):
    video=self.lift();jobs=[]
    for state in ('queued','processing','completed'):
      job=self.insert([video],status='processing' if state=='completed' else state)
      if state=='completed':self.complete(job)
      jobs.append((job,state))
    self.begin_owner_deletion()
    for job,old in jobs:
      with self.subTest(old=old):
        self.assertTrue(self.terminal_update(job,state='failed',failure='archive_missing' if old=='completed' else 'generation_failed',complete=True))
        self.assertTrue(self.terminal_update(job,state='failed'))
        self.assertEqual(self.sql('select status,archive_path,expires_at from public.saved_lift_export_jobs where id=%s',(job,))[0],{'status':'failed','archive_path':None,'expires_at':None})

  def test_terminal_cleanup_cannot_hide_identity_attempt_or_artifact_changes(self):
    video=self.lift();other=self.lift();job=self.insert([video],status='processing')
    before=self.sql('select * from public.saved_lift_export_jobs where id=%s',(job,))[0];self.begin_owner_deletion()
    mutations=[('id=%s',(uuid4(),)),('user_id=%s',(self.other,)),('video_ids=%s',([other],)),
               ('attempts=attempts+1',()),('started_at=clock_timestamp()',()),
               ('archive_path=%s',(f'{self.user}/{job}.zip',)),
               ("expires_at=clock_timestamp()+interval '1 hour'",()),("completed_at='infinity'",())]
    for clause,args in mutations:
      with self.subTest(clause=clause),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.sql("update public.saved_lift_export_jobs set status='expired',"+("" if clause.startswith("archive_path=") else "archive_path=null,")+clause+' where id=%s',args+(job,))
      self.assertEqual(self.sql('select * from public.saved_lift_export_jobs where id=%s',(job,))[0],before)

  def test_terminal_cleanup_rejects_hidden_attempt_even_for_active_owner(self):
    video=self.lift();job=self.insert([video],status='processing')
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.sql("update public.saved_lift_export_jobs set status='failed',archive_path=null,attempts=attempts+1 where id=%s",(job,))
    self.assertEqual(self.sql('select status,attempts from public.saved_lift_export_jobs where id=%s',(job,))[0],{'status':'processing','attempts':1})

  def test_busy_owner_fails_nowait_for_admission_and_completion_then_retry_succeeds(self):
    video=self.lift();job=self.insert([video],status='processing')
    with self.connect() as holder:
      holder.execute('select user_id from public.private_media_owners where user_id=%s for update',(self.user,))
      for operation in (lambda:self.insert([video]),lambda:self.complete(job)):
        started=time.monotonic()
        with self.assertRaises(self.psycopg.errors.LockNotAvailable):operation()
        self.assertLess(time.monotonic()-started,2)
    self.assertTrue(self.insert([video]));self.assertEqual(len(self.complete(job)),1)

  def test_expire_cleanup_does_not_wait_for_busy_owner(self):
    video=self.lift();job=self.insert([video],status='processing')
    with self.connect() as holder:
      holder.execute('select user_id from public.private_media_owners where user_id=%s for update',(self.user,))
      started=time.monotonic();self.assertTrue(self.terminal_update(job));self.assertLess(time.monotonic()-started,2)
    self.assertEqual(self.sql('select status from public.saved_lift_export_jobs where id=%s',(job,))[0]['status'],'expired')

  def test_uncommitted_owner_deletion_fails_fast_and_rollback_preserves_publication(self):
    video=self.lift();job=self.insert([video],status='processing')
    with self.connect() as holder:
      holder.execute('set local role service_role');self.begin_owner_deletion(connection=holder)
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):self.complete(job)
      holder.rollback()
    self.assertEqual(len(self.complete(job)),1)
    self.begin_owner_deletion()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.complete(job)

  def test_completion_transaction_holds_owner_boundary_until_deletion_can_commit(self):
    video=self.lift();job=self.insert([video],status='processing');ready=threading.Event();waiter={}
    import test_archive_writes_postgres as archive_writes
    helper=archive_writes.ArchiveWritesPostgresTest
    args=helper.arguments(self,helper.plan(self,job));helper.admit(self,args);helper.observe(self,args)
    def delete():
      with self.connect() as connection:
        connection.execute("set local statement_timeout='4s'");connection.execute('set local role service_role')
        waiter['pid']=connection.info.backend_pid;ready.set()
        return self.begin_owner_deletion(connection=connection)
    with ThreadPoolExecutor(max_workers=1) as pool,self.connect() as writer:
      writer.execute('set local role service_role')
      writer.execute('select public.publish_private_media_archive(%s,%s,3600)',(args[0],self.user))
      task=pool.submit(delete)
      try:
        self.assertTrue(ready.wait(2));self.wait_blocked(waiter['pid'],writer.info.backend_pid)
      finally:writer.commit()
      self.assertFalse(task.result(timeout=5)['replayed'])
    self.assertEqual(self.sql('select status from public.saved_lift_export_jobs where id=%s',(job,))[0]['status'],'completed')
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.complete(job)

  def test_other_owner_archive_work_is_unchanged_by_deletion(self):
    video=self.lift(owner=self.other);job=self.insert([video],owner=self.other,status='processing')
    self.begin_owner_deletion()
    self.assertEqual(len(self.complete(job)),1)
    self.assertEqual(self.sql('select status from public.saved_lift_export_jobs where id=%s',(job,))[0]['status'],'completed')

  def test_owner_archive_guard_is_service_only_invoker_with_empty_search_path(self):
    proc=self.sql("select prosecdef,proconfig from pg_proc where oid='public.fence_owner_saved_lift_export()'::regprocedure")[0]
    self.assertFalse(proc['prosecdef']);self.assertEqual(proc['proconfig'],['search_path=""'])
    self.assertTrue(self.sql("select has_function_privilege('service_role','public.fence_owner_saved_lift_export()','execute') as allowed")[0]['allowed'])
    for role in ('anon','authenticated','public_probe'):
      self.assertFalse(self.sql("select has_function_privilege(%s,'public.fence_owner_saved_lift_export()','execute') as allowed",(role,))[0]['allowed'])



  def test_video_revocation_cleanup_still_expires_archives_after_owner_deletion(self):
    video=self.lift();jobs=[]
    for state in ('queued','processing','completed','failed'):
      job=self.insert([video],status='processing' if state=='completed' else state)
      if state=='completed':self.complete(job)
      jobs.append(job)
    self.begin_owner_deletion();task=self.rpc([video])[0]
    for job in jobs:
      self.assertIn(f'{self.user}/{job}.zip',task['archive_paths'])
      row=self.sql('select status,archive_path,expires_at<=clock_timestamp() as elapsed from public.saved_lift_export_jobs where id=%s',(job,))[0]
      self.assertEqual(row,{'status':'expired','archive_path':None,'elapsed':True})
    self.assertEqual(len(self.rpc([video])),1)


if __name__ == "__main__": unittest.main()
