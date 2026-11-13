import unittest
import threading
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4, UUID
import test_video_revocation_postgres as fixture


@unittest.skipUnless(fixture.DATABASE_URL, 'Dedicated deletion test database is not configured.')
class SavedDeletionPostgresTest(unittest.TestCase):
  setUpClass=classmethod(fixture.VideoRevocationPostgresTest.setUpClass.__func__)
  connect=classmethod(fixture.VideoRevocationPostgresTest.connect.__func__)
  setUp=fixture.VideoRevocationPostgresTest.setUp
  sql=fixture.VideoRevocationPostgresTest.sql
  video=fixture.VideoRevocationPostgresTest.video
  job=fixture.VideoRevocationPostgresTest.job
  archive=fixture.VideoRevocationPostgresTest.archive
  rpc=fixture.VideoRevocationPostgresTest.rpc

  def batch(self,ids,owner=None,role='service_role',connection=None):
    if connection:
      return connection.execute('select * from public.revoke_saved_lifts(%s,%s)',(owner or self.user,ids)).fetchall()
    with self.connect() as c:
      c.execute('set local statement_timeout=\'5s\'');c.execute('set local role '+role)
      return self.batch(ids,owner,role,c)

  def finish(self, task, connection=None):
    if connection:
      return connection.execute('select public.complete_video_media_deletion(%s,%s,%s,%s,%s,%s) as done',
        tuple(task[k] for k in ['video_id','user_id','storage_paths','archive_paths','export_prefixes','delete_metadata'])).fetchone()['done']
    with self.connect() as c:
      c.execute('set local role service_role');return self.finish(task,c)

  def readback(self,ids,owner=None):
    with self.connect() as c:
      c.execute('set local role service_role')
      return c.execute('select * from public.read_saved_lift_deletion_receipts(%s,%s)',(owner or self.user,ids)).fetchall()

  def test_first_batch_revokes_every_member_and_completes_atomically_per_task(self):
    videos=[self.video(),self.video()];job=self.job(videos[0]);archive=self.archive(videos)
    rows=self.batch(videos);self.assertEqual(len(rows),2)
    self.assertTrue(all(not r['completed'] and r['task']['delete_metadata'] for r in rows))
    self.assertEqual(self.sql('select status from public.analysis_jobs where id=%s',(job,))[0]['status'],'cancelled')
    self.assertEqual(self.sql('select status from public.saved_lift_export_jobs where id=%s',(archive,))[0]['status'],'expired')
    for r in rows:self.assertTrue(self.finish(r['task']))
    self.assertTrue(all(r['completed'] for r in self.readback(videos)))
    self.assertEqual(self.sql('select id from public.videos'),[])
    self.assertEqual(self.sql('select video_id from public.video_deletion_outbox'),[])

  def test_partial_original_batch_retry_preserves_completed_member(self):
    videos=[self.video(),self.video()];first=self.batch(videos)
    self.assertTrue(self.finish(first[0]['task']))
    again=self.batch(list(reversed(videos)));done=[r for r in again if r['completed']];pending=[r for r in again if not r['completed']]
    self.assertEqual(len(done),1);self.assertIsNone(done[0]['task']);self.assertEqual(len(pending),1)
    self.assertTrue(self.finish(pending[0]['task']))
    self.assertTrue(all(r['completed'] and r['task'] is None for r in self.batch(videos)))

  def test_full_selection_failure_rolls_back_new_intents_and_revocation(self):
    live=self.video();foreign=self.video(owner=self.other);pending=self.video(save_state='pending',is_saved=False)
    for bad in (foreign,uuid4(),pending):
      with self.subTest(bad=bad),self.assertRaises(self.psycopg.Error):self.batch([live,bad])
      self.assertEqual(self.sql('select video_id from public.saved_lift_deletion_receipts'),[])
      self.assertIsNone(self.sql('select discarded_at from public.videos where id=%s',(live,))[0]['discarded_at'])
      self.assertEqual(self.sql('select video_id from public.video_deletion_outbox'),[])

  def test_completed_plus_fresh_invalid_does_not_revoke_other_valid_lift(self):
    done=self.video();self.finish(self.batch([done])[0]['task']);valid=self.video();bad=self.video(save_state='pending',is_saved=False)
    with self.assertRaises(self.psycopg.Error):self.batch([done,valid,bad])
    self.assertIsNone(self.sql('select discarded_at from public.videos where id=%s',(valid,))[0]['discarded_at'])
    self.assertEqual(len(self.sql('select video_id from public.saved_lift_deletion_receipts')),1)

  def test_generic_discard_and_retention_outbox_cannot_authorize_saved_deletion(self):
    for method in ('discard','outbox'):
      video=self.video()
      if method=='discard':self.rpc([video])
      else:self.sql('insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values (%s,%s,\'{}\')',(video,self.user))
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.batch([video])
    self.assertEqual(self.sql('select video_id from public.saved_lift_deletion_receipts'),[])

  def test_legacy_saved_flags_and_fifty_boundary(self):
    videos=[self.video(save_state='saved',is_saved=False),self.video(save_state='pending',is_saved=True)]+[self.video() for _ in range(48)]
    self.assertEqual(len(self.batch(list(reversed(videos)))),50)

  def test_invalid_bounded_selections_do_not_write(self):
    v=self.video()
    for ids in (None,[],[None],[v,v],[[v]],[UUID(int=0)],[uuid4() for _ in range(51)]):
      with self.subTest(ids=ids),self.assertRaises(self.psycopg.errors.InvalidParameterValue):self.batch(ids)
    self.assertEqual(self.sql('select video_id from public.saved_lift_deletion_receipts'),[])

  def test_receipt_owner_is_never_rebound_and_foreign_readback_empty(self):
    v=self.video();self.batch([v])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.batch([v],self.other)
    self.assertEqual(self.readback([v],self.other),[])

  def test_stale_snapshot_does_not_complete_receipt(self):
    v=self.video();task=self.batch([v])[0]['task'];stale=deepcopy(task);stale['storage_paths'].append(f'{self.user}/unconfirmed.mp4')
    self.assertFalse(self.finish(stale));self.assertFalse(self.readback([v])[0]['completed'])
    self.assertTrue(self.finish(task));self.assertTrue(self.readback([v])[0]['completed'])

  def test_finalizer_failure_rolls_back_receipt_and_metadata(self):
    v=self.video();task=self.batch([v])[0]['task']
    self.sql("create function public.test_stop_saved_finalizer() returns trigger language plpgsql as $$ begin raise exception 'fixture stop'; end $$")
    self.sql('create trigger test_stop_saved_finalizer before delete on public.videos for each row execute function public.test_stop_saved_finalizer()')
    try:
      with self.assertRaises(self.psycopg.Error):self.finish(task)
      self.assertFalse(self.readback([v])[0]['completed']);self.assertEqual(len(self.sql('select id from public.videos where id=%s',(v,))),1)
      self.assertEqual(len(self.sql('select video_id from public.video_deletion_outbox where video_id=%s',(v,))),1)
    finally:self.sql('drop trigger test_stop_saved_finalizer on public.videos');self.sql('drop function public.test_stop_saved_finalizer()')

  def test_completed_identity_cannot_be_reused_even_by_original_owner(self):
    v=self.video();self.finish(self.batch([v])[0]['task'])
    for owner in (self.user,self.other):
      with self.subTest(owner=owner),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.sql('insert into public.videos(id,user_id) values (%s,%s)',(v,owner))
    live=self.video()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.sql('update public.videos set id=%s where id=%s',(v,live))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.sql('update public.videos set user_id=%s where id=%s',(self.other,live))

  def test_receipt_cannot_be_premarked_changed_or_deleted(self):
    v=self.video();self.batch([v])
    for statement,values in [('update public.saved_lift_deletion_receipts set completed_at=clock_timestamp() where video_id=%s',(v,)),
                             ('update public.saved_lift_deletion_receipts set user_id=%s where video_id=%s',(self.other,v)),
                             ('delete from public.saved_lift_deletion_receipts where video_id=%s',(v,))]:
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.sql(statement,values)
    unknown=uuid4()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.sql('insert into public.saved_lift_deletion_receipts(video_id,user_id) values (%s,%s)',(unknown,self.user))

  def test_concurrent_reverse_batches_and_duplicate_completion_serialize(self):
    ids=[self.video(),self.video()]
    with ThreadPoolExecutor(2) as pool:
      first=pool.submit(self.batch,ids);second=pool.submit(self.batch,list(reversed(ids)))
      rows=first.result(timeout=8);self.assertEqual(len(second.result(timeout=8)),2)
    with ThreadPoolExecutor(2) as pool:
      results=list(pool.map(self.finish,[rows[0]['task'],rows[0]['task']]))
    self.assertEqual(sorted(results),[False,True]);self.assertTrue(self.readback([rows[0]['video_id']])[0]['completed'])

  def test_insert_waiting_behind_completion_cannot_reuse_deleted_id(self):
    v=self.video();task=self.batch([v])[0]['task'];ready=threading.Event();waiter={}
    def insert():
      with self.connect() as c:
        c.execute("set local statement_timeout='5s'");waiter['pid']=c.info.backend_pid;ready.set()
        return c.execute('insert into public.videos(id,user_id) values (%s,%s)',(v,self.user))
    with self.connect() as finisher,ThreadPoolExecutor(1) as pool:
      finisher.execute('set local role service_role');self.assertTrue(self.finish(task,finisher))
      future=pool.submit(insert)
      try:
        self.assertTrue(ready.wait(3))
        fixture.VideoRevocationPostgresTest.wait_blocked(self,waiter['pid'],finisher.info.backend_pid)
      finally:finisher.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):future.result(timeout=5)

  def test_auth_removal_does_not_erase_completed_retry_proof(self):
    v=self.video();self.finish(self.batch([v])[0]['task']);self.sql('delete from auth.users where id=%s',(self.user,))
    self.assertTrue(self.readback([v])[0]['completed'])

  def test_pending_outbox_retry_survives_missing_video_metadata(self):
    v=self.video();task=self.batch([v])[0]['task'];self.sql('delete from public.videos where id=%s',(v,))
    again=self.batch([v])[0];self.assertFalse(again['completed']);self.assertEqual(again['task']['storage_paths'],task['storage_paths'])
    self.assertTrue(self.finish(again['task']));self.assertTrue(self.readback([v])[0]['completed'])

  def test_completed_receipt_with_new_outbox_is_not_completion_proof(self):
    v=self.video();self.finish(self.batch([v])[0]['task'])
    self.sql('insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values (%s,%s,\'{}\')',(v,self.user))
    self.assertFalse(self.readback([v])[0]['completed'])
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.batch([v])

  def test_service_only_tables_functions_and_fixed_invoker_scope(self):
    signatures=['revoke_saved_lifts(uuid,uuid[])','read_saved_lift_deletion_receipts(uuid,uuid[])','guard_deleted_video_identity()','guard_saved_lift_deletion_receipt()']
    for sig in signatures:
      p=self.sql('select prosecdef,proconfig from pg_proc where oid=%s::regprocedure',('public.'+sig,))[0]
      self.assertFalse(p['prosecdef']);self.assertIn('search_path=""',p['proconfig'])
      for role in ('anon','authenticated','public_probe'):
        self.assertFalse(self.sql('select has_function_privilege(%s,%s,\'execute\') as allowed',(role,'public.'+sig))[0]['allowed'])
    for role in ('anon','authenticated','public_probe'):
      for privilege in ('SELECT','INSERT','UPDATE','DELETE'):
        self.assertFalse(self.sql('select has_table_privilege(%s,\'public.saved_lift_deletion_receipts\',%s) as allowed',(role,privilege))[0]['allowed'])
