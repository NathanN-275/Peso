from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import threading
import unittest
from uuid import UUID, uuid4

import test_video_revocation_postgres as fixture
import test_generated_media_writes_postgres as generated
import test_private_media_grants_postgres as grants


PROFILE_FIELDS = {'id', 'username', 'display_name', 'avatar_path', 'created_at', 'updated_at', 'profile_revision'}
WRITE_FIELDS = {'attempt_id', 'user_id', 'session_id', 'provider', 'bucket', 'storage_path', 'content_type',
                'size_bytes', 'content_sha256', 'profile_revision', 'previous_avatar_path', 'max_user_bytes',
                'max_global_bytes', 'state', 'created_at', 'observed_at', 'published_at', 'published_username',
                'published_display_name'}


@unittest.skipUnless(fixture.DATABASE_URL, 'Dedicated localhost avatar-write database is not configured.')
class AvatarWritesPostgresTest(unittest.TestCase):
  connect = classmethod(fixture.VideoRevocationPostgresTest.connect.__func__)
  video = fixture.VideoRevocationPostgresTest.video
  legacy_video_fields = fixture.VideoRevocationPostgresTest.legacy_video_fields
  wait_blocked = fixture.VideoRevocationPostgresTest.wait_blocked
  make_generated = generated.GeneratedMediaWritesPostgresTest.make_args
  reserve_source = generated.GeneratedMediaWritesPostgresTest.reserve_source
  session = grants.PrivateMediaGrantsPostgresTest.session

  @classmethod
  def setUpClass(cls):
    fixture.VideoRevocationPostgresTest.setUpClass.__func__(cls)
    root = Path(__file__).resolve().parents[2]
    with cls.psycopg.connect(fixture.DATABASE_URL, autocommit=True) as c:
      c.execute((root/'backend/tests/fixtures/profile_owner_database.sql').read_text())
      # Load the full production profile schema, constraints, RLS and triggers.
      c.execute((root/'supabase/migrations/202607120001_profile_infrastructure_repair.sql').read_text())
      c.execute((root/'supabase/migrations/20260825033422_harden_video_upload_object_policy.sql').read_text())
      c.execute("create policy fixture_video_read on storage.objects for select to authenticated using(bucket_id='videos' and (storage.foldername(name))[1]=auth.uid()::text)")
      c.execute("create policy fixture_video_delete on storage.objects for delete to authenticated using(bucket_id='videos' and (storage.foldername(name))[1]=auth.uid()::text)")
      c.execute((root/'supabase/migrations/20261029210252_owner_profile_storage_admission.sql').read_text())
      c.execute((root/'supabase/migrations/20261030000756_avatar_write_attempts.sql').read_text())

  def setUp(self):
    self.c = self.psycopg.connect(fixture.DATABASE_URL, autocommit=True)
    self.addCleanup(self.c.close)
    self.c.execute('truncate public.private_media_avatar_writes,public.private_media_generated_writes,public.private_media_write_attempts,public.private_media_owners,storage.objects,auth.users cascade')
    self.c.execute("""update public.private_media_provider_policy set enabled=true,auth_version='v2.197.0',
      auth_source_commit=%s,timebox_seconds=0,inactivity_timeout_seconds=0,
      single_per_user=false,allow_low_aal_seconds=0,refresh_rotation_enabled=true,refresh_reuse_interval_seconds=10,
      refresh_allow_reuse=false,refresh_token_algorithm_version=2,refresh_token_upgrade_percentage=100,
      verified_at=clock_timestamp()-interval '1 minute',verified_until=clock_timestamp()+interval '1 hour'""",
      ('4eee58f296d9698a1c2c0ae14d7a0b379c7622d3',))
    self.c.execute('update public.upload_admission_control set enabled=true where id=1')
    self.user, self.other, self.sid, self.sid2, self.other_sid = (uuid4() for _ in range(5))
    self.c.execute('insert into auth.users(id) values(%s),(%s)', (self.user,self.other))
    self.session(self.sid); self.session(self.sid2); self.session(self.other_sid,self.other)

  def sql(self, query, args=()):
    return fixture.VideoRevocationPostgresTest.sql(self,query,args)

  def run_sql(self, query, args=(), connection=None, role='service_role'):
    if connection is not None:
      cursor = connection.execute(query,args)
      return cursor.fetchall() if cursor.description else []
    with self.psycopg.connect(fixture.DATABASE_URL) as c:
      c.execute(self.psycopg.sql.SQL('set local role {}').format(self.psycopg.sql.Identifier(role)))
      c.execute("set local statement_timeout='4s'")
      c.execute("select set_config('request.jwt.claim.sub',%s,true)",(str(self.user),))
      return self.run_sql(query,args,c)

  def scalar(self, query, args=(), **kwargs):
    return self.run_sql(query,args,**kwargs)[0][0]

  def read(self, owner=None, session=None, **kwargs):
    return self.scalar('select public.read_private_media_profile(%s,%s)',(owner or self.user,session or self.sid),**kwargs)

  def save(self, revision=None, username='synthetic_user', name='Synthetic', **kwargs):
    return self.scalar('select public.save_private_media_profile(%s,%s,%s,%s,%s)',
      (self.user,self.sid,revision,username,name),**kwargs)

  def args(self, *, owner=None, session=None, revision=None, size=80, limits=(1000000,1000000)):
    return (uuid4(),owner or self.user,session or self.sid,revision,size,'a'*64,*limits)

  def admit(self, args, **kwargs):
    return self.scalar('select public.admit_private_media_avatar_write('+','.join(['%s']*8)+')',args,**kwargs)

  def observe_args(self, args):
    return (args[0],args[1],args[2],'profile-avatars',f'{args[1]}/avatar-{args[0]}.jpg','image/jpeg',args[4],args[5])

  def observe(self, args, **kwargs):
    return self.scalar('select public.observe_private_media_avatar_write_success('+','.join(['%s']*8)+')',self.observe_args(args),**kwargs)

  def publish(self, args, username='synthetic_user', name='Synthetic', **kwargs):
    return self.scalar('select public.publish_private_media_avatar(%s,%s,%s,%s,%s)',(*args[:3],username,name),**kwargs)

  def write(self, args):
    return self.scalar('select to_jsonb(a) from public.private_media_avatar_writes a where attempt_id=%s',(args[0],))

  def ready(self, **kwargs):
    args=self.args(**kwargs);self.admit(args);self.assertIs(self.observe(args),True);return args

  def begin(self, **kwargs):
    return self.run_sql('select * from public.begin_private_media_owner_deletion(%s)',(self.user,),**kwargs)

  def logout(self, **kwargs):
    return self.scalar("select public.revoke_private_media_session(%s,%s,'local')",(self.user,self.sid),**kwargs)

  def test_absent_profile_admission_observation_publication_and_exact_replay(self):
    self.assertIsNone(self.read());args=self.args();row=self.admit(args)
    self.assertEqual(set(row),WRITE_FIELDS);self.assertEqual(row['state'],'dispatching')
    self.assertIsNone(row['profile_revision']);self.assertIsNone(row['previous_avatar_path'])
    self.assertEqual(row,self.write(args));self.assertIs(self.observe(args),True)
    profile=self.publish(args);self.assertEqual(set(profile),PROFILE_FIELDS)
    self.assertEqual(profile['avatar_path'],self.observe_args(args)[4]);self.assertIsNotNone(profile['profile_revision'])
    self.assertEqual(self.publish(args),profile);self.assertEqual(self.read(),profile)
    published=self.write(args);self.assertIsNotNone(published['published_at'])
    self.assertEqual(published['published_username'],'synthetic_user');self.assertEqual(published['published_display_name'],'Synthetic')
    self.assertIs(self.observe(args),True);self.assertEqual(self.write(args),published)

  def test_current_revision_required_for_admission_and_save(self):
    profile=self.save();revision=profile['profile_revision']
    for stale in (None,uuid4()):
      with self.subTest(stale=stale),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(self.args(revision=stale))
      with self.subTest(save_stale=stale),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.save(stale)
    self.admit(self.args(revision=revision));updated=self.save(revision,name='Updated')
    self.assertNotEqual(updated['profile_revision'],revision);self.assertEqual(updated['display_name'],'Updated')
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.save(revision)

  def test_missing_profile_rejects_nonnull_revision_and_delete_recreate_cas(self):
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.save(uuid4())
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.admit(self.args(revision=uuid4()))
    first=self.save();args=self.ready(revision=first['profile_revision'])
    self.run_sql('delete from public.profiles where id=%s',(self.user,),role='authenticated')
    self.save()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)
    self.assertIsNone(self.write(args)['published_at'])

  def test_every_profile_update_rotates_revision_even_same_values_and_caller_supplied_revision(self):
    first=self.save();revision=first['profile_revision']
    for role in ('authenticated','service_role'):
      row=self.scalar('update public.profiles p set display_name=display_name,profile_revision=%s where id=%s returning to_jsonb(p)',
        (revision,self.user),role=role)
      self.assertNotEqual(row['profile_revision'],revision);revision=row['profile_revision']
    second=self.save(revision);self.assertNotEqual(second['profile_revision'],revision)

  def test_profile_change_during_upload_blocks_publication_without_losing_observation(self):
    before=self.save();args=self.ready(revision=before['profile_revision']);after=self.save(before['profile_revision'],name='Later')
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)
    self.assertEqual(self.read(),after);self.assertEqual(self.write(args)['state'],'succeeded');self.assertIsNone(self.write(args)['published_at'])

  def test_replay_keeps_later_profile_text_and_cannot_rebind_or_reattach(self):
    args=self.ready();first=self.publish(args);later=self.save(first['profile_revision'],name='Later')
    self.assertEqual(self.publish(args),later)
    for username,name in [('different_user','Synthetic'),('synthetic_user','Different')]:
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args,username,name)
    replacement=self.ready(revision=later['profile_revision']);current=self.publish(replacement,name='Replacement')
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(args)
    self.assertEqual(self.read(),current)
    self.run_sql('update public.profiles set avatar_path=null where id=%s',(self.user,))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(replacement,name='Replacement')
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.run_sql('update public.profiles set avatar_path=%s where id=%s',(current['avatar_path'],self.user))

  def test_exact_observer_identity_returns_literal_false_for_every_mismatch(self):
    args=self.args();self.admit(args);original=self.write(args);identity=self.observe_args(args)
    for index,value in enumerate((uuid4(),self.other,self.sid2,'videos',f'{self.other}/avatar.jpg','image/png',81,'b'*64)):
      changed=list(identity);changed[index]=value
      with self.subTest(index=index):
        self.assertIs(self.scalar('select public.observe_private_media_avatar_write_success('+','.join(['%s']*8)+')',changed),False)
        self.assertEqual(self.write(args),original)
    self.assertIs(self.observe(args),True)

  def test_unobserved_wrong_owner_wrong_session_and_missing_attempt_cannot_publish(self):
    args=self.args();self.admit(args)
    for changed in (args,(uuid4(),*args[1:]),(args[0],self.other,self.other_sid,*args[3:]),(args[0],self.user,self.sid2,*args[3:])):
      with self.subTest(changed=changed[:3]),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.publish(changed)
    self.assertIsNone(self.read());self.assertIsNone(self.write(args)['published_at'])

  def test_profile_constraint_errors_roll_back_publication_and_revision(self):
    profile=self.save();args=self.ready(revision=profile['profile_revision']);before=self.write(args)
    for username,name in [('bad name','Synthetic'),('synthetic_user','x'*81)]:
      with self.assertRaises(self.psycopg.errors.CheckViolation):self.publish(args,username,name)
      self.assertEqual(self.write(args),before);self.assertEqual(self.read(),profile)
    self.c.execute("insert into public.profiles(id,username) values(%s,'occupied_user')",(self.other,))
    with self.assertRaises(self.psycopg.errors.UniqueViolation):self.publish(args,'occupied_user')
    self.assertEqual(self.write(args),before);self.assertEqual(self.read(),profile)
    self.assertEqual(self.publish(args)['avatar_path'],self.observe_args(args)[4])

  def test_parent_profile_trigger_error_rolls_back_ledger_publication(self):
    args=self.ready()
    self.c.execute("create function public.fixture_reject_profile() returns trigger language plpgsql as $$begin raise exception 'synthetic profile failure'; end$$")
    self.c.execute('create trigger z_fixture_reject_profile before insert or update on public.profiles for each row execute function public.fixture_reject_profile()')
    try:
      with self.assertRaises(self.psycopg.errors.RaiseException):self.publish(args)
      self.assertIsNone(self.write(args)['published_at']);self.assertIsNone(self.read())
    finally:
      self.c.execute('drop trigger z_fixture_reject_profile on public.profiles');self.c.execute('drop function public.fixture_reject_profile()')

  def test_direct_client_paths_and_privileged_unobserved_paths_are_denied(self):
    for role in ('authenticated','service_role'):
      with self.subTest(role=role),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.run_sql('insert into public.profiles(id,avatar_path) values(%s,%s)',(self.user,f'{self.user}/arbitrary.jpg'),role=role)
    args=self.ready();self.run_sql('update public.private_media_avatar_writes set published_at=clock_timestamp(),published_username=%s,published_display_name=%s where attempt_id=%s',('synthetic_user','Synthetic',args[0]))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.run_sql('insert into public.profiles(id,username,display_name,avatar_path) values(%s,%s,%s,%s)',
        (self.user,'synthetic_user','Synthetic',self.observe_args(args)[4]),role='authenticated')
    # Privileged code must match the frozen published profile fields too.
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.run_sql('insert into public.profiles(id,avatar_path) values(%s,%s)',(self.user,self.observe_args(args)[4]))

  def test_unchanged_legacy_avatar_and_clear_reference_remain_cleanup_compatible(self):
    self.c.execute('alter table public.profiles disable trigger fence_profile_avatar_publication')
    try:self.c.execute('insert into public.profiles(id,avatar_path) values(%s,%s)',(self.user,f'{self.user}/legacy.png'))
    finally:self.c.execute('alter table public.profiles enable trigger fence_profile_avatar_publication')
    profile=self.read();args=self.ready(revision=profile['profile_revision'])
    self.assertEqual(self.write(args)['previous_avatar_path'],profile['avatar_path'])
    for role in ('authenticated','service_role'):
      self.run_sql('update public.profiles set display_name=%s where id=%s',('Still compatible',self.user),role=role)
      self.run_sql('update public.profiles set avatar_path=null where id=%s',(self.user,),role=role)

  def test_owner_and_provider_or_app_session_denial_fences_read_save_admit_publish(self):
    for denial in ('owner','missing_owner','provider_policy','provider_session','provider_refresh','banned','local_logout','global_logout','others_logout'):
      with self.subTest(denial=denial):
        self.setUp();args=self.ready()
        if denial=='owner':self.begin()
        elif denial=='missing_owner':self.c.execute('truncate public.private_media_owners cascade')
        elif denial=='provider_policy':self.c.execute('update public.private_media_provider_policy set enabled=false')
        elif denial=='provider_session':self.c.execute('delete from auth.sessions where id=%s',(self.sid,))
        elif denial=='provider_refresh':self.c.execute('update auth.refresh_tokens set revoked=true where session_id=%s',(self.sid,))
        elif denial=='banned':self.c.execute("update auth.users set banned_until=clock_timestamp()+interval '1 hour' where id=%s",(self.user,))
        elif denial=='local_logout':self.logout()
        else:self.scalar('select public.revoke_private_media_session(%s,%s,%s)',(self.user,self.sid2,'global' if denial=='global_logout' else 'others'))
        for call in (self.read,self.save,lambda:self.admit(self.args()),lambda:self.publish(args)):
          with self.assertRaises(self.psycopg.Error):call()
        self.assertIs(self.observe(args),True);self.assertIsNone(self.write(args)['published_at'])

  def test_wrong_or_missing_session_never_admits_even_for_live_owner(self):
    for owner,session in ((self.user,uuid4()),(self.user,self.other_sid),(self.other,self.sid)):
      with self.subTest(owner=owner,session=session),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.admit(self.args(owner=owner,session=session))

  def test_pending_and_late_observation_survive_profile_session_auth_and_owner_loss(self):
    profile=self.save();args=self.args(revision=profile['profile_revision']);self.admit(args);before=self.write(args)
    self.c.execute('delete from public.profiles where id=%s',(self.user,));self.begin()
    self.c.execute('delete from auth.users where id=%s',(self.user,))
    self.assertEqual(self.write(args),before);self.assertIs(self.observe(args),True)
    self.c.execute('truncate public.private_media_owners cascade')
    self.assertIs(self.scalar('select public.private_media_avatar_write_pending(%s)',(self.user,)),True)
    self.assertIs(self.scalar('select public.private_media_avatar_write_pending(%s)',(self.other,)),False)
    self.assertEqual(self.write(args)['state'],'succeeded')
    self.assertEqual(self.c.execute("select count(*) from pg_constraint where conrelid='public.private_media_avatar_writes'::regclass and contype='f'").fetchone()[0],0)

  def test_publication_timestamp_cannot_precede_success_observation(self):
    args=self.ready()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.run_sql('update public.private_media_avatar_writes set published_at=created_at where attempt_id=%s',(args[0],))
    self.assertIsNone(self.write(args)['published_at'])
    self.publish(args);row=self.write(args)
    self.assertGreaterEqual(row['published_at'],row['observed_at'])

  def test_identity_outcomes_and_publication_evidence_cannot_mutate_or_disappear(self):
    args=self.ready();self.publish(args);before=self.write(args)
    updates=("size_bytes=size_bytes+1","storage_path=storage_path||'x'","profile_revision=gen_random_uuid()","session_id=gen_random_uuid()",
      "state='dispatching',observed_at=null","observed_at=clock_timestamp()","published_at=null,published_username=null,published_display_name=null",
      "published_username='other_user'","published_display_name='Changed'","published_at=clock_timestamp()")
    for assignment in updates:
      with self.subTest(assignment=assignment),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.c.execute('update public.private_media_avatar_writes set '+assignment+' where attempt_id=%s',(args[0],))
      self.assertEqual(self.write(args),before)
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.c.execute('delete from public.private_media_avatar_writes where attempt_id=%s',(args[0],))
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.run_sql('delete from public.private_media_avatar_writes where attempt_id=%s',(args[0],))

  def test_sql_boundary_rejects_invalid_size_hash_caps_and_attempt_identity(self):
    for index,value in ((0,UUID(int=0)),(4,0),(4,-1),(4,524289),(4,None),(5,'A'*64),(5,'a'*63),(5,None),(6,0),(7,0),(6,None)):
      args=list(self.args());args[index]=value
      with self.subTest(index=index,value=value),self.assertRaises(self.psycopg.Error):self.admit(args)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_avatar_writes').fetchone()[0],0)
    self.admit(self.args(size=524288))
    self.c.execute('update public.upload_admission_control set enabled=false')
    with self.assertRaises(self.psycopg.errors.NoDataFound):self.admit(self.args())

  def test_capacity_counts_avatar_generated_and_reserved_bytes_in_both_directions(self):
    self.admit(self.args(size=80,limits=(160,160)))
    self.admit(self.args(size=80,limits=(160,160)))
    for owner,session,limits in ((self.user,self.sid,(160,1000)),(self.other,self.other_sid,(1000,160))):
      with self.assertRaises(self.psycopg.errors.RaiseException):self.admit(self.args(owner=owner,session=session,limits=limits))
    with self.assertRaises(self.psycopg.errors.RaiseException):self.reserve_source(size=1,user_limit=160)
    generated_args=self.make_generated()
    with self.assertRaises(self.psycopg.errors.RaiseException):
      generated.GeneratedMediaWritesPostgresTest.admit(self,generated_args,limits=(160,1000))
    self.c.execute('truncate public.private_media_avatar_writes')
    self.reserve_source(size=100,user_limit=200)
    with self.assertRaises(self.psycopg.errors.RaiseException):self.admit(self.args(size=101,limits=(200,1000)))
    generated.GeneratedMediaWritesPostgresTest.admit(self,generated_args,limits=(200,1000))
    with self.assertRaises(self.psycopg.errors.RaiseException):self.admit(self.args(size=21,limits=(200,1000)))
    self.admit(self.args(size=20,limits=(200,1000)))

  def test_avatar_admission_serializes_other_owner_source_and_generated_capacity(self):
    args=self.args(size=80,limits=(1000,100));ready=threading.Event();state={}
    generated_args=self.make_generated(owner=self.other)
    def reserve():
      with self.psycopg.connect(fixture.DATABASE_URL) as c:
        c.execute('set local role service_role');c.execute("set local statement_timeout='4s'")
        state['pid']=c.info.backend_pid;reservation=uuid4();ready.set()
        try:
          self.run_sql('select id from public.reserve_video_upload('+','.join(['%s']*17)+')',
            (reservation,self.other,f'{self.other}/source/{reservation}.mp4','synthetic.mp4','video/mp4',21,
             datetime.now(timezone.utc)+timedelta(minutes=5),'camera_roll','squat','side',1000,None,100,1000,100,100,100),connection=c)
          return 'unexpected admission'
        except self.psycopg.Error as error:return error.sqlstate
    with self.psycopg.connect(fixture.DATABASE_URL) as writer,ThreadPoolExecutor(1) as pool:
      writer.execute('set local role service_role');self.admit(args,connection=writer)
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):
        generated.GeneratedMediaWritesPostgresTest.admit(self,generated_args,limits=(1000,100))
      task=pool.submit(reserve)
      try:
        self.assertTrue(ready.wait(2));grants.PrivateMediaGrantsPostgresTest.wait_for_lock(self,state['pid']);self.assertFalse(task.done())
      finally:writer.commit()
      self.assertEqual(task.result(timeout=4),'P0001')
    with self.assertRaises(self.psycopg.errors.RaiseException):
      generated.GeneratedMediaWritesPostgresTest.admit(self,generated_args,limits=(1000,100))
    self.assertEqual(self.c.execute('select count(*) from public.upload_reservations').fetchone()[0],0)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_generated_writes').fetchone()[0],0)

  def test_other_owners_profile_and_source_work_survive_retained_avatar_and_deletion(self):
    args=self.ready();self.begin()
    profile=self.scalar('select public.save_private_media_profile(%s,%s,null,%s,%s)',
      (self.other,self.other_sid,'other_user','Other owner'))
    self.assertEqual(profile['id'],str(self.other));self.assertTrue(self.reserve_source(owner=self.other))
    self.assertIs(self.scalar('select public.private_media_avatar_write_pending(%s)',(self.user,)),True)
    self.assertIs(self.observe(args),True)

  def test_post_rollout_source_analysis_generated_and_archive_publication_still_work(self):
    from psycopg.types.json import Jsonb
    from test_archive_writes_postgres import ArchiveWritesPostgresTest
    avatar=self.ready();profile=self.publish(avatar)
    profile=self.save(profile['profile_revision'],name='Media owner')
    reservation,lease=uuid4(),uuid4();path=f'{self.user}/source/{reservation}.mp4'
    self.run_sql('select id from public.reserve_video_upload('+','.join(['%s']*17)+')',
      (reservation,self.user,path,'synthetic.mp4','video/mp4',100,
       datetime.now(timezone.utc)+timedelta(minutes=5),'camera_roll','squat','side',1000,None,3,10000,20,100000,100))
    source=(uuid4(),self.user,reservation,'videos',path,'video/mp4',100)
    self.run_sql('select * from public.admit_private_media_source_write('+','.join(['%s']*7)+')',source)
    self.assertIs(self.scalar('select public.observe_private_media_source_write_success('+','.join(['%s']*7)+')',source),True)
    self.run_sql('select id from public.mark_video_upload_received(%s,%s,%s)',(reservation,self.user,lease))
    video=self.scalar('select video_id from public.verify_video_upload(%s,%s,%s,%s,%s,%s)',
      (reservation,self.user,100,Jsonb({'duration_ms':1000,'fps':30,'frame_count':30}),datetime.now(timezone.utc)+timedelta(hours=1),lease))
    job=self.scalar('select id from public.enqueue_video_analysis_job(%s,false,3,20)',(video,))
    worker='synthetic-avatar-compatibility-worker'
    self.assertEqual(self.run_sql('select id,attempt_count from public.claim_video_analysis_job(%s,60)',(worker,)),[(job,1)])
    generated_args=list(self.make_generated(video=video,job=job));generated_args[10]=worker
    self.run_sql('select * from public.admit_private_media_generated_write('+','.join(['%s']*14)+')',(*generated_args,10000,100000))
    self.assertIs(self.scalar('select public.observe_private_media_generated_write_success('+','.join(['%s']*12)+')',generated_args),True)
    self.run_sql('update public.videos set thumbnail_path=%s where id=%s',(generated_args[5],video))
    self.assertIsNotNone(self.scalar('select public.publish_video_analysis(%s,%s,%s,%s,%s,%s,%s)',
      (video,job,worker,1,Jsonb({'status':'completed'}),'synthetic-model',Jsonb({'reps':1}))))
    self.assertIs(self.scalar('select public.complete_video_analysis_job(%s,%s,1)',(job,worker)),True)
    self.run_sql("update public.videos set is_saved=true,save_state='saved' where id=%s",(video,))
    archive=uuid4()
    self.run_sql("insert into public.saved_lift_export_jobs(id,user_id,video_ids,status,attempts,started_at) values(%s,%s,%s,'processing',1,clock_timestamp())",(archive,self.user,[video]))
    plan=self.scalar('select public.plan_private_media_archive(%s,%s)',(self.user,archive))
    args=ArchiveWritesPostgresTest.arguments(self,plan)
    self.run_sql('select public.admit_private_media_archive_write('+','.join(['%s']*13)+')',args)
    self.assertIs(self.scalar('select public.observe_private_media_generated_write_success('+','.join(['%s']*12)+')',
      (args[0],self.user,None,'archive',args[7],args[8],None,'application/zip',args[9],None,None,None)),True)
    receipt=self.scalar('select public.publish_private_media_archive(%s,%s,3600)',(args[0],self.user))
    self.assertEqual(receipt['storage_path'],args[8])
    self.assertEqual(self.scalar('select public.read_private_media_archive(%s,%s)',(self.user,archive)),receipt)
    self.assertEqual(self.read(),profile)

  def test_client_storage_mutations_are_restrictively_denied_and_video_cleanup_still_works(self):
    avatar=f'{self.user}/legacy.jpg';video=f'{self.user}/source/{uuid4()}.mp4'
    for bucket,name in (('profile-avatars',avatar),('videos',video)):
      self.run_sql('insert into storage.objects(bucket_id,name) values(%s,%s)',(bucket,name))
    self.c.execute('create policy fixture_broad_avatar_write on storage.objects for all to authenticated using(true) with check(true)')
    try:
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.run_sql('insert into storage.objects(bucket_id,name) values(%s,%s)',('profile-avatars',f'{self.user}/new.jpg'),role='authenticated')
      for query in ('update storage.objects set metadata=\'{}\' where name=%s returning id','delete from storage.objects where name=%s returning id'):
        self.assertEqual(self.run_sql(query,(avatar,),role='authenticated'),[])
      self.assertTrue(self.run_sql('delete from storage.objects where name=%s returning id',(video,),role='authenticated'))
    finally:self.c.execute('drop policy fixture_broad_avatar_write on storage.objects')
    self.assertEqual(self.c.execute("select count(*) from pg_policies where policyname like 'avatar_backend_%' and permissive='RESTRICTIVE'").fetchone()[0],3)

  def test_service_only_grants_fixed_search_paths_and_no_extra_definer_access(self):
    names=('lock_private_media_profile','assert_private_media_avatar_write','admit_private_media_avatar_write',
      'observe_private_media_avatar_write_success','save_private_media_profile','publish_private_media_avatar','private_media_avatar_write_pending','read_private_media_profile')
    rows=self.c.execute('select oid::regprocedure::text,prosecdef,proconfig from pg_proc where pronamespace=\'public\'::regnamespace and proname=any(%s)',(list(names),)).fetchall()
    self.assertEqual(len(rows),len(names))
    for signature,definer,config in rows:
      self.assertFalse(definer);self.assertIn('search_path=""',config)
      for role in ('anon','authenticated','public_probe'):
        self.assertFalse(self.c.execute('select has_function_privilege(%s,%s,\'execute\')',(role,signature)).fetchone()[0])
      self.assertTrue(self.c.execute('select has_function_privilege(\'service_role\',%s,\'execute\')',(signature,)).fetchone()[0])
    for role in ('anon','authenticated','public_probe'):
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.read(role=role)
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.run_sql('select * from public.private_media_avatar_writes',role=role)

  def test_concurrent_profile_creation_and_update_compare_and_swap(self):
    for exists in (False,True):
      self.c.execute('delete from public.profiles')
      revision=self.save()['profile_revision'] if exists else None
      def save(name):
        try:return self.save(revision,name=name)
        except self.psycopg.Error as error:return error.sqlstate
      with ThreadPoolExecutor(2) as pool:results=list(pool.map(save,('First','Second')))
      self.assertEqual(sum(isinstance(result,dict) for result in results),1)
      self.assertTrue(all(isinstance(result,dict) or result in ('55000','55P03') for result in results))
      if revision is None:self.c.execute('delete from public.profiles')

  def test_concurrent_avatar_publications_only_one_can_change_the_profile(self):
    args=[self.ready(),self.ready()]
    def publish(arg):
      try:return self.publish(arg)
      except self.psycopg.Error as error:return error.sqlstate
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(publish,args))
    self.assertEqual(sum(isinstance(result,dict) for result in results),1)
    self.assertEqual(sum(self.write(arg)['published_at'] is not None for arg in args),1)

  def test_capacity_lock_is_shared_across_owners_without_oversubscription(self):
    args=[self.args(size=80,limits=(1000,100)),self.args(owner=self.other,session=self.other_sid,size=80,limits=(1000,100))]
    def admit(arg):
      try:return self.admit(arg)
      except self.psycopg.Error as error:return error.sqlstate
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(admit,args))
    self.assertEqual(sum(isinstance(result,dict) for result in results),1)
    self.assertEqual(self.c.execute('select sum(size_bytes) from public.private_media_avatar_writes').fetchone()[0],80)

  def test_direct_child_lock_fails_nowait_against_owner_first_deletion(self):
    args=self.ready();profile=self.save()
    # The pending write now has a stale CAS; its child lock must still fail on
    # the busy owner before it can form an owner/profile/ledger lock cycle.
    with self.psycopg.connect(fixture.DATABASE_URL) as owner:
      owner.execute('set local role service_role');self.begin(connection=owner)
      for call in (lambda:self.read(),lambda:self.admit(self.args()),lambda:self.save(profile['profile_revision']),lambda:self.publish(args),
        lambda:self.run_sql('update public.private_media_avatar_writes set published_at=clock_timestamp() where attempt_id=%s',(args[0],)),
        lambda:self.run_sql('update public.profiles set display_name=display_name where id=%s',(self.user,))):
        with self.assertRaises(self.psycopg.errors.LockNotAvailable):call()
      owner.rollback()
    self.assertEqual(self.read(),profile)

  def test_profile_then_ledger_lock_order_never_blocks_an_observer(self):
    profile=self.save();args=self.args(revision=profile['profile_revision']);self.admit(args)
    with self.psycopg.connect(fixture.DATABASE_URL) as holder:
      holder.execute('select id from public.profiles where id=%s for update',(self.user,))
      self.assertIs(self.observe(args),True)
    with self.psycopg.connect(fixture.DATABASE_URL) as observer:
      observer.execute('select attempt_id from public.private_media_avatar_writes where attempt_id=%s for update',(args[0],))
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):self.publish(args)
      # A different owner's profile and video reservation are independent.
      self.assertIsNone(self.read(owner=self.other,session=self.other_sid));self.assertTrue(self.reserve_source(owner=self.other))

  def test_publication_holds_owner_until_commit_and_logout_then_denies_replay(self):
    args=self.ready();ready=threading.Event();state={}
    def logout():
      with self.psycopg.connect(fixture.DATABASE_URL) as c:
        c.execute('set local role service_role');c.execute("set local statement_timeout='4s'")
        state['pid']=c.info.backend_pid;ready.set();return self.logout(connection=c)
    with self.psycopg.connect(fixture.DATABASE_URL) as writer,ThreadPoolExecutor(1) as pool:
      writer.execute('set local role service_role');self.publish(args,connection=writer)
      task=pool.submit(logout)
      try:
        self.assertTrue(ready.wait(2));grants.PrivateMediaGrantsPostgresTest.wait_for_lock(self,state['pid']);self.assertFalse(task.done())
      finally:writer.commit()
      self.assertTrue(task.result(timeout=4))
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.publish(args)
    self.assertIsNotNone(self.write(args)['published_at'])


if __name__=='__main__':unittest.main()
