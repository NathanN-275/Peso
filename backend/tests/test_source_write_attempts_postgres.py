from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import threading
import time
import unittest
from uuid import UUID, uuid4

import test_video_revocation_postgres as fixture


@unittest.skipUnless(fixture.DATABASE_URL, 'Dedicated local source-write database is not configured.')
class SourceWriteAttemptsPostgresTest(unittest.TestCase):
  connect = classmethod(fixture.VideoRevocationPostgresTest.connect.__func__)
  sql = fixture.VideoRevocationPostgresTest.sql
  setUp = fixture.VideoRevocationPostgresTest.setUp
  video = fixture.VideoRevocationPostgresTest.video
  rpc = fixture.VideoRevocationPostgresTest.rpc

  setUpClass = classmethod(fixture.VideoRevocationPostgresTest.setUpClass.__func__)

  def setUp(self):
    fixture.VideoRevocationPostgresTest.setUp(self)

  def run_sql(self, sql, args=(), connection=None, role='service_role'):
    if connection is not None:
      cursor = connection.execute(sql, args)
      return cursor.fetchall() if cursor.description else []
    with self.connect() as c:
      c.execute('set local role '+role)
      c.execute("set local statement_timeout='5s'")
      return self.run_sql(sql, args, c)

  def wait_for_lock(self, pid):
    deadline = time.monotonic()+2
    with self.connect(autocommit=True) as c:
      while time.monotonic()<deadline:
        row = c.execute('select wait_event_type from pg_catalog.pg_stat_activity where pid=%s',(pid,)).fetchone()
        if row and row['wait_event_type']=='Lock':return
        threading.Event().wait(.01)
    self.fail('Expected an actual PostgreSQL lock wait.')

  def reserve(self, owner=None, expiry=None):
    owner = owner or self.user
    reservation = uuid4()
    path = f'{owner}/source/{reservation}.mp4'
    self.run_sql("insert into public.upload_reservations(id,user_id,blob_path,file_name,content_type,requested_bytes,source_type,exercise_type,view_type,expires_at) values(%s,%s,%s,'synthetic.mp4','video/mp4',100,'camera_roll','squat','side',%s)",
      (reservation, owner, path, expiry or datetime.now(timezone.utc)+timedelta(minutes=5)))
    return reservation, path

  def args(self, reservation=None, owner=None):
    owner = owner or self.user
    reservation, path = reservation or self.reserve(owner)
    return (uuid4(), owner, reservation, 'videos', path, 'video/mp4', 80)

  def admit(self, args=None, connection=None, role='service_role'):
    args = args or self.args()
    rows = self.run_sql('select * from public.admit_private_media_source_write(%s,%s,%s,%s,%s,%s,%s)', args, connection, role)
    return args, rows

  def observe(self, args, connection=None, role='service_role'):
    return self.run_sql('select public.observe_private_media_source_write_success(%s,%s,%s,%s,%s,%s,%s) as observed', args, connection, role)[0]['observed']

  def begin(self, connection=None):
    return self.run_sql('select * from public.begin_private_media_owner_deletion(%s)', (self.user,), connection)

  def publish(self, args):
    lease = uuid4()
    self.run_sql('select * from public.mark_video_upload_received(%s,%s,%s)', (args[2],args[1],lease))
    video = self.run_sql('select * from public.verify_video_upload(%s,%s,%s,%s::jsonb,%s,%s)',
      (args[2],args[1],args[6],'{"duration_ms":1000,"frame_count":30,"fps":30}',datetime.now(timezone.utc)+timedelta(hours=1),lease))[0]['video_id']
    return video

  def finish(self, task):
    return self.run_sql('select public.complete_video_media_deletion(%s,%s,%s,%s,%s,%s) as completed',
      tuple(task[k] for k in ('video_id','user_id','storage_paths','archive_paths','export_prefixes','delete_metadata')))[0]['completed']

  def test_fresh_dispatch_receipt_binds_exact_body_and_stays_pending(self):
    args, rows = self.admit()
    self.assertEqual(rows,[dict(zip(('attempt_id','user_id','reservation_id','bucket','storage_path','content_type','size_bytes','state'),(*args,'dispatching')))])
    row = self.sql('select provider,state,observed_at,video_id from public.private_media_write_attempts')[0]
    self.assertEqual(row, {'provider':'supabase','state':'dispatching','observed_at':None,'video_id':None})

  def test_same_attempt_replay_never_authorizes_second_dispatch(self):
    args, _ = self.admit()
    for _ in range(2):
      with self.assertRaises(self.psycopg.errors.UniqueViolation):self.admit(args)
    self.assertEqual(len(self.sql('select attempt_id from public.private_media_write_attempts')),1)

  def test_pending_or_uncommitted_source_cleanup_denies_new_dispatch(self):
    args = self.args()
    video = self.video(storage_path=args[4], original_storage_path=args[4])
    self.rpc([video],delete=True)
    self.sql('delete from public.videos where id=%s',(video,))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState): self.admit(args)
    with self.connect() as cleanup:
      cleanup.execute('set local role service_role')
      cleanup.execute('delete from public.video_deletion_outbox where video_id=%s',(video,))
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState): self.admit(args)
      cleanup.rollback()
    self.assertEqual(self.sql('select attempt_id from public.private_media_write_attempts'),[])

  def test_same_reservation_cannot_dispatch_different_attempt_or_bucket(self):
    args, _ = self.admit()
    for bucket in ('videos','other-video-bucket'):
      changed = (uuid4(),*args[1:3],bucket,*args[4:])
      with self.assertRaises(self.psycopg.errors.UniqueViolation):self.admit(changed)
    self.assertEqual(len(self.sql('select attempt_id from public.private_media_write_attempts')),1)

  def test_attempt_id_cannot_be_rebound_to_another_reservation(self):
    args, _ = self.admit()
    second = list(self.args());second[0] = args[0]
    with self.assertRaises(self.psycopg.errors.UniqueViolation):self.admit(tuple(second))

  def test_wrong_owner_path_type_size_and_missing_reservation_are_denied(self):
    original = self.args()
    mutations = {0:UUID(int=0),1:self.other,2:uuid4(),3:'Bad/bucket',4:f'{self.other}/source/wrong.mp4',5:'video/webm',6:101}
    for index,value in mutations.items():
      args = list(original);args[index] = value
      with self.subTest(index=index),self.assertRaises(self.psycopg.Error):self.admit(tuple(args))
    for size in (None,0,-1):
      args = (*original[:6],size)
      with self.subTest(size=size),self.assertRaises(self.psycopg.Error):self.admit(args)
    self.assertEqual(self.sql('select attempt_id from public.private_media_write_attempts'),[])

  def test_custom_safe_bucket_is_preserved(self):
    args = list(self.args());args[3] = 'private-video.bucket_2'
    self.assertEqual(self.admit(tuple(args))[1][0]['bucket'],args[3])

  def test_deleting_owner_and_missing_owner_deny_admission(self):
    args = self.args();self.begin()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(args)
    missing = uuid4()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.run_sql('select public.lock_active_private_media_owner(%s,false)',(missing,))
    self.assertEqual(self.sql('select attempt_id from public.private_media_write_attempts'),[])

  def test_reservation_expiry_and_terminal_states_deny_dispatch(self):
    for state in ('expired','rejected','uploaded'):
      args = self.args()
      if state=='uploaded':
        self.run_sql('select public.mark_video_upload_received(%s,%s,%s)',(args[2],self.user,uuid4()))
      else:self.run_sql('update public.upload_reservations set state=%s where id=%s',(state,args[2]))
      with self.subTest(state=state),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(args)
    args = self.args()
    self.run_sql("update public.upload_reservations set expires_at=clock_timestamp()-interval '1 second' where id=%s",(args[2],))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(args)

  def test_legacy_unlinked_video_source_denies_dispatch(self):
    for field in ('storage_path','original_storage_path'):
      args = self.args()
      self.video(**{field:args[4]})
      with self.subTest(field=field),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(args)
    self.assertEqual(self.sql('select attempt_id from public.private_media_write_attempts'),[])

  def test_delete_observation_or_confirmed_cleanup_denies_dispatch(self):
    for column in ('blob_deleted_at','cleanup_confirmed_at'):
      args = self.args()
      self.run_sql('update public.upload_reservations set '+column+'=clock_timestamp() where id=%s',(args[2],))
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(args)

  def test_observed_success_is_exact_idempotent_and_never_settled(self):
    args, _ = self.admit();self.assertTrue(self.observe(args))
    first = self.sql('select * from public.private_media_write_attempts')[0]
    self.assertTrue(self.observe(args));self.assertEqual(self.sql('select * from public.private_media_write_attempts')[0],first)
    self.assertEqual(first['state'],'succeeded');self.assertIsNotNone(first['observed_at'])
    for index,value in ((0,uuid4()),(1,self.other),(2,uuid4()),(3,'different'),(4,args[4]+'x'),(5,'image/jpeg'),(6,79)):
      changed = list(args);changed[index] = value
      with self.subTest(index=index):self.assertFalse(self.observe(tuple(changed)))

  def test_late_success_survives_owner_deletion_and_auth_removal(self):
    args,_ = self.admit();at = self.begin()[0]['deleting_at']
    self.sql('delete from auth.users where id=%s',(self.user,))
    self.assertTrue(self.observe(args))
    row = self.sql('select user_id,state from public.private_media_write_attempts')[0]
    self.assertEqual(row,{'user_id':self.user,'state':'succeeded'})
    self.assertEqual(self.sql('select deleting_at from public.private_media_owners where user_id=%s',(self.user,))[0]['deleting_at'],at)
    self.assertIsNone(self.sql('select user_id from public.upload_reservations where id=%s',(args[2],))[0]['user_id'])

  def test_pending_attempt_blocks_quota_release_and_tombstone_purge_in_both_states(self):
    args,_ = self.admit()
    for success in (False,True):
      if success:self.observe(args)
      self.run_sql('update public.upload_reservations set blob_deleted_at=clock_timestamp() where id=%s',(args[2],))
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.run_sql('update public.upload_reservations set cleanup_confirmed_at=clock_timestamp() where id=%s',(args[2],))
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.run_sql('delete from public.upload_reservations where id=%s',(args[2],))
      self.assertIsNone(self.sql('select cleanup_confirmed_at from public.upload_reservations where id=%s',(args[2],))[0]['cleanup_confirmed_at'])

  def test_legacy_reservation_without_attempt_keeps_cleanup_behavior(self):
    reservation,_ = self.reserve()
    self.run_sql('update public.upload_reservations set cleanup_confirmed_at=clock_timestamp() where id=%s',(reservation,))
    self.run_sql('delete from public.upload_reservations where id=%s',(reservation,))
    self.assertEqual(self.sql('select id from public.upload_reservations'),[])

  def test_direct_insert_uses_same_owner_and_resource_boundary(self):
    args = self.args();self.begin()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.run_sql('insert into public.private_media_write_attempts(attempt_id,user_id,reservation_id,bucket,storage_path,content_type,size_bytes) values(%s,%s,%s,%s,%s,%s,%s)',args)

  def test_client_roles_have_no_table_or_rpc_access(self):
    args = self.args()
    for role in ('anon','authenticated','public_probe'):
      for query,values in [('select * from public.private_media_write_attempts',()),('select * from public.admit_private_media_source_write(%s,%s,%s,%s,%s,%s,%s)',args),('select public.observe_private_media_source_write_success(%s,%s,%s,%s,%s,%s,%s)',args),('select public.private_media_source_write_pending(%s,%s,%s)',(uuid4(),self.user,[]))]:
        with self.subTest(role=role,query=query),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.run_sql(query,values,role=role)

  def test_service_cannot_mutate_identity_delete_or_insert_success(self):
    args,_ = self.admit()
    for statement,values in [("update public.private_media_write_attempts set storage_path=storage_path||'x'",()),('delete from public.private_media_write_attempts',()),("insert into public.private_media_write_attempts(attempt_id,user_id,reservation_id,bucket,storage_path,content_type,size_bytes,state) values(%s,%s,%s,%s,%s,%s,%s,'succeeded')",self.args())]:
      with self.subTest(statement=statement),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.run_sql(statement,values)
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.sql('delete from public.private_media_write_attempts')
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.sql("update public.private_media_write_attempts set provider='other'")

  def test_success_cannot_be_cleared_or_combined_with_video_rebinding(self):
    args,_ = self.admit();self.observe(args)
    for changes in ("state='dispatching',observed_at=null",'observed_at=null',"observed_at='infinity'",'video_id=gen_random_uuid()'):
      with self.subTest(changes=changes),self.assertRaises(self.psycopg.Error):self.run_sql('update public.private_media_write_attempts set '+changes)

  def test_source_video_binding_is_durable_and_cannot_move(self):
    args,_ = self.admit();self.observe(args);video = self.publish(args)
    self.assertEqual(self.sql('select video_id from public.private_media_write_attempts')[0]['video_id'],video)
    for other in (None,uuid4()):
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.run_sql('update public.private_media_write_attempts set video_id=%s',(other,))
    self.sql('delete from public.videos where id=%s',(video,))
    self.assertEqual(self.sql('select video_id from public.private_media_write_attempts')[0]['video_id'],video)
    self.assertTrue(self.run_sql('select public.private_media_source_write_pending(%s,%s,%s) as pending',(video,self.user,[]))[0]['pending'])

  def test_finalizer_keeps_metadata_outbox_and_saved_receipt_pending(self):
    args,_ = self.admit();self.observe(args);video = self.publish(args)
    self.run_sql("update public.videos set save_state='saved',is_saved=true where id=%s",(video,))
    task = self.run_sql('select * from public.revoke_saved_lifts(%s,%s)',(self.user,[video]))[0]['task']
    for _ in range(2):self.assertFalse(self.finish(task))
    self.assertEqual(self.sql('select id from public.videos')[0]['id'],video)
    self.assertIsNone(self.sql('select completed_at from public.saved_lift_deletion_receipts')[0]['completed_at'])
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.run_sql('delete from public.video_deletion_outbox where video_id=%s',(video,))

  def test_saved_completion_cannot_bypass_missing_media_metadata(self):
    args,_ = self.admit();video = self.publish(args)
    self.run_sql("update public.videos set save_state='saved',is_saved=true where id=%s",(video,))
    self.run_sql('select * from public.revoke_saved_lifts(%s,%s)',(self.user,[video]))
    self.sql('delete from public.videos where id=%s',(video,))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.run_sql('update public.saved_lift_deletion_receipts set completed_at=clock_timestamp() where video_id=%s',(video,))
    self.assertIsNone(self.sql('select completed_at from public.saved_lift_deletion_receipts')[0]['completed_at'])

  def test_unrelated_owner_and_video_cleanup_remains_available(self):
    self.admit();video = self.video(owner=self.other)
    task = self.rpc([video],owner=self.other,delete=True)[0]
    self.assertTrue(self.finish(task))

  def test_owner_lock_wait_observes_committed_deletion(self):
    args = self.args()
    with self.connect() as holder,self.connect() as waiting,ThreadPoolExecutor(max_workers=1) as pool:
      holder.execute('set local role service_role');self.begin(holder)
      waiting.execute('set local role service_role')
      future = pool.submit(self.admit,args,waiting)
      self.wait_for_lock(waiting.info.backend_pid)
      holder.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):future.result(timeout=4)
    self.assertEqual(self.sql('select attempt_id from public.private_media_write_attempts'),[])

  def test_admission_holds_owner_until_commit_then_deletion_cannot_erase_intent(self):
    args = self.args()
    with self.connect() as holder,self.connect() as waiting,ThreadPoolExecutor(max_workers=1) as pool:
      holder.execute('set local role service_role');self.admit(args,holder)
      waiting.execute('set local role service_role')
      future = pool.submit(self.begin,waiting)
      self.wait_for_lock(waiting.info.backend_pid)
      holder.commit();self.assertIsNotNone(future.result(timeout=4)[0]['deleting_at']);waiting.commit()
    self.assertEqual(len(self.sql('select attempt_id from public.private_media_write_attempts')),1)
    self.assertTrue(self.observe(args))

  def test_cleanup_wait_cannot_release_quota_after_admission_commits(self):
    args = self.args()
    with self.connect() as holder,self.connect() as waiting,ThreadPoolExecutor(max_workers=1) as pool:
      holder.execute('set local role service_role');self.admit(args,holder)
      waiting.execute('set local role service_role')
      future = pool.submit(self.run_sql,'update public.upload_reservations set cleanup_confirmed_at=clock_timestamp() where id=%s',(args[2],),waiting)
      self.wait_for_lock(waiting.info.backend_pid);holder.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):future.result(timeout=4)
    self.assertIsNone(self.sql('select cleanup_confirmed_at from public.upload_reservations where id=%s',(args[2],))[0]['cleanup_confirmed_at'])

  def test_expiry_after_reservation_lock_wait_is_denied(self):
    args = self.args();expiry = datetime.now(timezone.utc)+timedelta(milliseconds=400)
    self.run_sql('update public.upload_reservations set expires_at=%s where id=%s',(expiry,args[2]))
    with self.connect() as holder,self.connect() as waiting,ThreadPoolExecutor(max_workers=1) as pool:
      holder.execute('select id from public.upload_reservations where id=%s for update',(args[2],))
      waiting.execute('set local role service_role')
      future = pool.submit(self.admit,args,waiting);self.wait_for_lock(waiting.info.backend_pid)
      delay = max(0,(expiry-datetime.now(timezone.utc)).total_seconds()+.05)
      threading.Event().wait(delay);holder.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):future.result(timeout=4)
    self.assertEqual(self.sql('select attempt_id from public.private_media_write_attempts'),[])

  def test_concurrent_dispatches_have_exactly_one_new_receipt(self):
    args = self.args();other = (uuid4(),*args[1:])
    def attempt(values):
      try:return bool(self.admit(values)[1])
      except self.psycopg.errors.UniqueViolation:return False
    with ThreadPoolExecutor(max_workers=2) as pool:results = list(pool.map(attempt,(args,other)))
    self.assertEqual(sorted(results),[False,True]);self.assertEqual(len(self.sql('select attempt_id from public.private_media_write_attempts')),1)

  def test_all_functions_are_service_only_invokers_with_fixed_path_and_rls(self):
    names = ['guard_private_media_write_attempt','admit_private_media_source_write','observe_private_media_source_write_success','bind_private_media_source_video','private_media_source_write_pending','fence_source_reservation_cleanup','fence_source_deletion_completion']
    rows = self.sql('select proname,prosecdef,proconfig from pg_catalog.pg_proc where proname=any(%s)',(names,))
    self.assertEqual(len(rows),len(names))
    for row in rows:
      self.assertFalse(row['prosecdef']);self.assertTrue(any(value in ('search_path=""','search_path=') for value in row['proconfig']))
    self.assertTrue(self.sql("select relrowsecurity from pg_catalog.pg_class where oid='public.private_media_write_attempts'::regclass")[0]['relrowsecurity'])
    self.assertEqual(self.sql("select conname from pg_catalog.pg_constraint where conrelid='public.private_media_write_attempts'::regclass and contype='f'"),[])
