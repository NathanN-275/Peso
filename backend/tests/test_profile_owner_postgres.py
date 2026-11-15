from pathlib import Path
from uuid import uuid4
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
import test_video_revocation_postgres as fixture
import test_private_media_grants_postgres as grant_fixture


@unittest.skipUnless(fixture.DATABASE_URL,'Dedicated local profile-owner database is not configured.')
class ProfileOwnerPostgresTest(unittest.TestCase):
  connect=classmethod(fixture.VideoRevocationPostgresTest.connect.__func__)
  @classmethod
  def setUpClass(cls):
    fixture.VideoRevocationPostgresTest.setUpClass.__func__(cls)
    root=Path(__file__).resolve().parents[2]
    with cls.psycopg.connect(fixture.DATABASE_URL,autocommit=True) as c:
      c.execute((root/'backend/tests/fixtures/profile_owner_database.sql').read_text())
      c.execute((root/'supabase/migrations/202607120001_profile_infrastructure_repair.sql').read_text())
      c.execute((root/'supabase/migrations/20260825033422_harden_video_upload_object_policy.sql').read_text())
      c.execute("create policy video_fixture_read on storage.objects for select to authenticated using(bucket_id='videos' and (storage.foldername(name))[1]=auth.uid()::text)")
      c.execute("create policy video_fixture_delete on storage.objects for delete to authenticated using(bucket_id='videos' and (storage.foldername(name))[1]=auth.uid()::text)")
      c.execute('grant select,insert,update,delete on public.profiles to service_role')
      legacy=uuid4();c.execute('insert into auth.users(id) values(%s)',(legacy,))
      deleted=uuid4();c.execute('insert into auth.users(id) values(%s)',(deleted,))
      at=c.execute('select deleting_at from public.begin_private_media_owner_deletion(%s)',(deleted,)).fetchone()[0]
      c.execute((root/'supabase/migrations/20261029210252_owner_profile_storage_admission.sql').read_text())
      if c.execute('select deleting_at from public.private_media_owners where user_id=%s',(legacy,)).fetchone()!=(None,):
        raise RuntimeError('Auth-only legacy owner was not backfilled.')
      if c.execute('select deleting_at from public.private_media_owners where user_id=%s',(deleted,)).fetchone()!=(at,):
        raise RuntimeError('Legacy deletion fence changed during backfill.')

  def setUp(self):
    self.c=self.psycopg.connect(fixture.DATABASE_URL,autocommit=True);self.addCleanup(self.c.close)
    self.c.execute('truncate public.private_media_generated_writes,public.private_media_write_attempts,public.private_media_owners,storage.objects,auth.users cascade')
    self.user,self.other=uuid4(),uuid4()
    self.c.execute('insert into auth.users(id) values(%s),(%s)',(self.user,self.other))

  def sql(self,sql,args=(),role='authenticated',user=None,connection=None):
    if connection is not None:
      cursor=connection.execute(sql,args)
      return cursor.fetchall() if cursor.description else []
    with self.psycopg.connect(fixture.DATABASE_URL) as c:
      c.execute('set local role '+role);c.execute("set local statement_timeout='4s'")
      c.execute("select set_config('request.jwt.claim.sub',%s,true)",(str(self.user if user is None else user),))
      return self.sql(sql,args,connection=c)

  def profile(self,user=None):
    owner=user or self.user
    return self.sql('insert into public.profiles(id,display_name) values(%s,%s) returning id',(owner,'Synthetic'),user=owner)

  def begin(self,connection=None):
    return self.sql('select * from public.begin_private_media_owner_deletion(%s)',(self.user,),role='service_role',connection=connection)

  def helper(self,owner=None,user=None):
    return self.sql('select peso_private.owned_media_write_is_live(%s)',(owner or self.user,),user=user)[0][0]

  def object(self,bucket='profile-avatars',user=None):
    owner=user or self.user;name=f'{owner}/{uuid4()}.png' if bucket=='profile-avatars' else f'{owner}/{uuid4()}.mp4'
    self.sql('insert into storage.objects(bucket_id,name) values(%s,%s)',(bucket,name),user=owner)
    return name

  def test_auth_role_signup_creates_owner_without_owner_table_privileges(self):
    user=uuid4();self.sql('insert into auth.users(id) values(%s)',(user,),role='supabase_auth_admin')
    self.assertEqual(self.c.execute('select deleting_at from public.private_media_owners where user_id=%s',(user,)).fetchone(),(None,))
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.sql('select * from public.private_media_owners')
    self.assertEqual(self.profile(user),[(user,)])

  def test_own_profile_insert_upsert_and_update_remain_compatible(self):
    self.profile()
    self.assertEqual(self.sql("insert into public.profiles(id,username) values(%s,'synthetic_user') on conflict(id) do update set username=excluded.username returning id",(self.user,)),[(self.user,)])
    self.assertEqual(self.sql("update public.profiles set display_name='Updated',avatar_path=%s where id=%s returning id",(f'{self.user}/avatar.png',self.user)),[(self.user,)])
    self.assertTrue(self.helper())

  def test_profile_foreign_null_and_anon_callers_cannot_write(self):
    for role,user in [('authenticated',self.other),('authenticated',''),('anon',self.user)]:
      with self.subTest(role=role,user=user),self.assertRaises(self.psycopg.Error):
        self.sql('insert into public.profiles(id) values(%s)',(self.user,),role=role,user=user)
    self.assertFalse(self.helper(owner=self.other));self.assertFalse(self.helper(user=''))

  def test_deletion_denies_profile_insert_and_update_without_mutation(self):
    self.profile();before=self.c.execute('select * from public.profiles').fetchall();self.begin()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.sql("update public.profiles set display_name='Late' where id=%s",(self.user,))
    self.assertEqual(self.c.execute('select * from public.profiles').fetchall(),before)
    self.sql('delete from public.profiles where id=%s',(self.user,))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.profile()

  def test_service_profile_writes_also_observe_deletion_and_identity_guard(self):
    self.profile();self.begin()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.sql("update public.profiles set display_name='Late' where id=%s",(self.user,),role='service_role')
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.sql('update public.profiles set id=%s where id=%s',(self.other,self.user),role='service_role')
    self.sql('delete from public.profiles where id=%s',(self.user,),role='service_role')
    self.assertEqual(self.c.execute('select id from public.profiles').fetchall(),[])

  def test_storage_insert_update_upsert_and_owner_isolation(self):
    for bucket in ('videos','profile-avatars'):
      name=self.object(bucket)
      self.assertTrue(self.sql("update storage.objects set metadata='{}' where bucket_id=%s and name=%s returning id",(bucket,name)))
      self.assertTrue(self.sql("insert into storage.objects(bucket_id,name,metadata) values(%s,%s,'{}') on conflict(bucket_id,name) do update set metadata=excluded.metadata returning id",(bucket,name)))
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.sql('insert into storage.objects(bucket_id,name) values(%s,%s)',(bucket,f'{self.other}/foreign.png'))
      self.assertEqual(self.sql('update storage.objects set metadata=null where name=%s returning id',(name,),user=self.other),[])

  def test_deletion_denies_direct_storage_writes_but_keeps_delete_cleanup(self):
    names=[(bucket,self.object(bucket)) for bucket in ('videos','profile-avatars')];self.begin()
    for bucket,name in names:
      with self.subTest(bucket=bucket):
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.object(bucket)
        self.assertEqual(self.sql("update storage.objects set metadata='{}' where name=%s returning id",(name,)),[])
        self.assertTrue(self.sql('delete from storage.objects where name=%s returning id',(name,)))

  def test_restrictive_owner_policies_cannot_be_bypassed_by_additional_permissive_policy(self):
    self.c.execute('create policy fixture_broad_insert on storage.objects for insert to authenticated with check(true)')
    try:
      self.begin()
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.object()
    finally:self.c.execute('drop policy fixture_broad_insert on storage.objects')

  def test_other_owner_work_survives_deletion(self):
    self.begin();self.assertEqual(self.profile(self.other),[(self.other,)]);self.assertTrue(self.object(user=self.other))

  def test_missing_owner_decision_is_false_and_cannot_create_an_owner(self):
    self.c.execute('truncate public.private_media_owners cascade')
    self.assertFalse(self.helper())
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.profile()
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.object()
    self.assertEqual(self.c.execute('select user_id from public.private_media_owners').fetchall(),[])

  def test_auth_recreation_preserves_deletion_tombstone(self):
    first=self.begin()[0][0];self.c.execute('delete from auth.users where id=%s',(self.user,))
    self.c.execute('insert into auth.users(id) values(%s)',(self.user,))
    self.assertEqual(self.c.execute('select deleting_at from public.private_media_owners where user_id=%s',(self.user,)).fetchone(),(first,))
    self.assertFalse(self.helper())
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.profile()

  def test_busy_owner_writes_fail_nowait_then_retry_after_rollback(self):
    self.profile()
    with self.psycopg.connect(fixture.DATABASE_URL) as holder:
      holder.execute('set local role service_role');self.begin(connection=holder)
      for call in (lambda:self.sql("update public.profiles set display_name='Retry' where id=%s",(self.user,)),lambda:self.object()):
        with self.assertRaises(self.psycopg.errors.LockNotAvailable):call()
      holder.rollback()
    self.assertTrue(self.sql("update public.profiles set display_name='Retry' where id=%s returning id",(self.user,)));self.assertTrue(self.object())

  def test_profile_writer_holds_owner_lock_until_transaction_commit(self):
    self.profile();ready=threading.Event();waiter={}
    def begin():
      with self.psycopg.connect(fixture.DATABASE_URL) as c:
        c.execute('set local role service_role');c.execute("set local statement_timeout='4s'")
        waiter['pid']=c.info.backend_pid;ready.set();return self.begin(connection=c)
    with self.psycopg.connect(fixture.DATABASE_URL) as writer,ThreadPoolExecutor(1) as pool:
      writer.execute('set local role authenticated');writer.execute("select set_config('request.jwt.claim.sub',%s,true)",(str(self.user),))
      writer.execute("update public.profiles set display_name='First' where id=%s",(self.user,))
      task=pool.submit(begin)
      try:
        self.assertTrue(ready.wait(2));grant_fixture.PrivateMediaGrantsPostgresTest.wait_for_lock(self,waiter['pid']);self.assertFalse(task.done())
      finally:writer.commit()
      self.assertFalse(task.result(timeout=4)[0][1])

  def test_private_helpers_have_exact_privileges_and_fixed_search_path(self):
    for role in ('anon','authenticated','service_role','supabase_auth_admin'):
      self.assertFalse(self.c.execute("select has_function_privilege(%s,'peso_private.initialize_private_media_owner()','execute')",(role,)).fetchone()[0])
    for role in ('anon','service_role','supabase_auth_admin'):
      self.assertFalse(self.c.execute("select has_function_privilege(%s,'peso_private.owned_media_write_is_live(uuid)','execute')",(role,)).fetchone()[0])
    self.assertTrue(self.c.execute("select has_function_privilege('authenticated','peso_private.owned_media_write_is_live(uuid)','execute')").fetchone()[0])
    rows=self.c.execute("select prosecdef,proconfig,pg_get_userbyid(proowner) from pg_proc where pronamespace='peso_private'::regnamespace").fetchall()
    self.assertEqual(len(rows),2);self.assertTrue(all(r[0] and 'search_path=""' in r[1] and r[2]=='postgres' for r in rows))
    self.assertFalse(self.c.execute("select has_schema_privilege('authenticated','peso_private','create')").fetchone()[0])
    policies=self.c.execute("select permissive from pg_policies where policyname in ('owner_media_insert_admission','owner_media_update_admission')").fetchall()
    self.assertEqual(policies,[('RESTRICTIVE',),('RESTRICTIVE',)])

  def test_service_storage_bypass_remains_an_explicit_backend_intent_requirement(self):
    self.begin()
    self.sql('insert into storage.objects(bucket_id,name) values(%s,%s)',('profile-avatars',f'{self.user}/service.png'),role='service_role')
    self.assertEqual(self.c.execute('select count(*) from storage.objects').fetchone()[0],1)



  def test_storage_writer_holds_owner_lock_until_commit(self):
    ready=threading.Event();waiter={}
    def begin():
      with self.psycopg.connect(fixture.DATABASE_URL) as c:
        c.execute('set local role service_role');c.execute("set local statement_timeout='4s'")
        waiter['pid']=c.info.backend_pid;ready.set();return self.begin(connection=c)
    with self.psycopg.connect(fixture.DATABASE_URL) as writer,ThreadPoolExecutor(1) as pool:
      writer.execute('set local role authenticated');writer.execute("select set_config('request.jwt.claim.sub',%s,true)",(str(self.user),))
      writer.execute('insert into storage.objects(bucket_id,name) values(%s,%s)',('profile-avatars',f'{self.user}/first.png'))
      task=pool.submit(begin)
      try:
        self.assertTrue(ready.wait(2));grant_fixture.PrivateMediaGrantsPostgresTest.wait_for_lock(self,waiter['pid']);self.assertFalse(task.done())
      finally:writer.commit()
      self.assertFalse(task.result(timeout=4)[0][1])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.object()

  def test_signup_owner_initialization_failure_rolls_back_auth_insert(self):
    self.c.execute("create function public.fixture_fail_owner() returns trigger language plpgsql as $$ begin raise exception 'synthetic owner failure'; end $$")
    self.c.execute('create trigger fixture_fail_owner before insert on public.private_media_owners for each row execute function public.fixture_fail_owner()')
    user=uuid4()
    try:
      with self.assertRaises(self.psycopg.errors.RaiseException):self.sql('insert into auth.users(id) values(%s)',(user,),role='supabase_auth_admin')
      self.assertEqual(self.c.execute('select id from auth.users where id=%s',(user,)).fetchall(),[])
    finally:
      self.c.execute('drop trigger fixture_fail_owner on public.private_media_owners');self.c.execute('drop function public.fixture_fail_owner()')

  def test_temporary_search_path_cannot_shadow_owner_decision(self):
    self.begin()
    with self.psycopg.connect(fixture.DATABASE_URL) as c:
      c.execute('create temporary table private_media_owners(user_id uuid,deleting_at timestamptz)')
      c.execute('insert into private_media_owners values(%s,null)',(self.user,))
      c.execute('set local role authenticated');c.execute("select set_config('request.jwt.claim.sub',%s,true)",(str(self.user),))
      self.assertFalse(c.execute('select peso_private.owned_media_write_is_live(%s)',(self.user,)).fetchone()[0])



  def test_signup_owner_supports_existing_media_sql_through_revocation(self):
    from datetime import datetime,timedelta,timezone
    from psycopg.types.json import Jsonb
    self.profile();rid=uuid4();lease=uuid4()
    self.sql('select id from public.reserve_video_upload(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
      (rid,self.user,f'{self.user}/source/{rid}.mp4','synthetic.mp4','video/mp4',100,
       datetime.now(timezone.utc)+timedelta(minutes=10),'camera_roll','squat','side',1000,None,3,10000,20,100000,100),role='service_role')
    self.sql('select id from public.mark_video_upload_received(%s,%s,%s)',(rid,self.user,lease),role='service_role')
    video=self.sql('select video_id from public.verify_video_upload(%s,%s,%s,%s,%s,%s)',
      (rid,self.user,100,Jsonb({'duration_ms':1000,'fps':30,'frame_count':30}),datetime.now(timezone.utc)+timedelta(hours=1),lease),role='service_role')[0][0]
    job=self.sql('select id from public.enqueue_video_analysis_job(%s,false,3,20)',(video,),role='service_role')[0][0]
    claimed=self.sql("select id,attempt_count from public.claim_video_analysis_job('synthetic-profile-worker',60)",role='service_role')[0]
    self.assertEqual(claimed,(job,1))
    self.assertIsNotNone(self.sql('select public.publish_video_analysis(%s,%s,%s,%s,%s,%s,%s)',
      (video,job,'synthetic-profile-worker',1,Jsonb({'status':'completed'}),'synthetic-model',Jsonb({'reps':1})),role='service_role')[0][0])
    self.assertTrue(self.sql('select public.complete_video_analysis_job(%s,%s,1)',(job,'synthetic-profile-worker'),role='service_role')[0][0])
    self.sql("update public.videos set is_saved=true,save_state='saved' where id=%s",(video,),role='service_role')
    archive=uuid4()
    self.sql("insert into public.saved_lift_export_jobs(id,user_id,video_ids,status,attempts,started_at) values(%s,%s,%s,'processing',1,clock_timestamp())",(archive,self.user,[video]),role='service_role')
    from test_archive_writes_postgres import ArchiveWritesPostgresTest
    plan=self.sql('select public.plan_private_media_archive(%s,%s)',(self.user,archive),role='service_role')[0][0]
    args=ArchiveWritesPostgresTest.arguments(self,plan)
    self.sql('select public.admit_private_media_archive_write('+','.join(['%s']*13)+')',args,role='service_role')
    self.assertTrue(self.sql('select public.observe_private_media_generated_write_success('+','.join(['%s']*12)+')',
      (args[0],self.user,None,'archive',args[7],args[8],None,'application/zip',args[9],None,None,None),role='service_role')[0][0])
    published=self.sql('select public.publish_private_media_archive(%s,%s,3600)',(args[0],self.user),role='service_role')[0][0]
    self.assertEqual(published['storage_path'],args[8])
    self.begin();self.assertEqual(len(self.sql('select * from public.revoke_video_media(%s,%s,true)',(self.user,[video]),role='service_role')),1)
    self.assertEqual(self.c.execute('select status,archive_path from public.saved_lift_export_jobs where id=%s',(archive,)).fetchone(),('expired',None))


if __name__=='__main__':unittest.main()
