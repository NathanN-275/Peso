from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import time
import unittest
from uuid import UUID, uuid4

import test_avatar_writes_postgres as avatar_fixture
import test_video_revocation_postgres as fixture


@unittest.skipUnless(fixture.DATABASE_URL, 'Dedicated localhost avatar-reader database is not configured.')
class AvatarReadsPostgresTest(unittest.TestCase):
  # Reuse the production-chain fixture without inheriting its unrelated tests.
  connect = classmethod(avatar_fixture.AvatarWritesPostgresTest.connect.__func__)
  setUp = avatar_fixture.AvatarWritesPostgresTest.setUp
  session = avatar_fixture.AvatarWritesPostgresTest.session
  sql = avatar_fixture.AvatarWritesPostgresTest.sql
  run_sql = avatar_fixture.AvatarWritesPostgresTest.run_sql
  scalar = avatar_fixture.AvatarWritesPostgresTest.scalar
  save = avatar_fixture.AvatarWritesPostgresTest.save
  read = avatar_fixture.AvatarWritesPostgresTest.read
  args = avatar_fixture.AvatarWritesPostgresTest.args
  admit = avatar_fixture.AvatarWritesPostgresTest.admit
  observe_args = avatar_fixture.AvatarWritesPostgresTest.observe_args
  observe = avatar_fixture.AvatarWritesPostgresTest.observe
  publish = avatar_fixture.AvatarWritesPostgresTest.publish
  ready = avatar_fixture.AvatarWritesPostgresTest.ready
  write = avatar_fixture.AvatarWritesPostgresTest.write
  begin = avatar_fixture.AvatarWritesPostgresTest.begin
  logout = avatar_fixture.AvatarWritesPostgresTest.logout

  @classmethod
  def setUpClass(cls):
    avatar_fixture.AvatarWritesPostgresTest.setUpClass.__func__(cls)
    root=Path(__file__).resolve().parents[2]
    cls.reader_migration=next((root/'supabase/migrations').glob('*_avatar_reader_grants.sql'))
    with cls.psycopg.connect(fixture.DATABASE_URL,autocommit=True) as c:
      c.execute((root/'supabase/migrations/20261030232852_session_replacement_cookie_paths.sql').read_text())
      c.execute(cls.reader_migration.read_text())

  def current(self):
    args=self.ready();return args,self.publish(args)

  def issue(self, revision, *, owner=None, session=None, expiry=None, digest=None, connection=None, role='service_role'):
    digest=digest or hashlib.sha256(str(uuid4()).encode()).hexdigest()
    rows=self.run_sql('select * from public.issue_private_media_avatar_grant(%s,%s,%s,%s,%s)',
      (owner or self.user,session or self.sid,digest,revision,expiry or datetime.now(timezone.utc)+timedelta(hours=1)),connection=connection,role=role)
    return digest,rows

  def authorize(self,digest,revision,**kwargs):
    return self.run_sql('select * from public.authorize_private_media_avatar_grant(%s,%s)',(digest,revision),**kwargs)

  def inventory(self, *, sid='current', after=None, owner=None):
    return self.run_sql('select * from public.private_media_session_cookie_paths(%s,%s,%s,%s)',
      (owner or self.user,self.sid if sid=='current' else sid,after[0] if after else None,after[1] if after else None))

  def test_current_published_generation_issues_and_authorizes_exact_retained_identity(self):
    args,profile=self.current();revision=profile['profile_revision']
    self.assertIsNone(self.write(args)['profile_revision'])
    digest,rows=self.issue(revision);self.assertEqual(rows[0][:2],('avatar',UUID(revision)))
    authorized=self.authorize(digest,revision);self.assertEqual(len(authorized),1)
    row=authorized[0]
    self.assertEqual(len(row),13);self.assertEqual(row[:4],(self.user,self.sid,'avatar',UUID(revision)))
    self.assertEqual(row[5:12],(args[0],'supabase','profile-avatars',self.observe_args(args)[4],'image/jpeg',80,'a'*64))
    self.assertIsNotNone(row[12]);self.assertEqual(self.inventory(),[('avatar',UUID(revision))])
    self.assertEqual(self.authorize(digest,uuid4()),[])

  def test_jwt_expiry_and_five_minute_upper_bound(self):
    _,profile=self.current();revision=profile['profile_revision']
    expiry=datetime.now(timezone.utc)+timedelta(seconds=40)
    _,rows=self.issue(revision,expiry=expiry);self.assertEqual(rows[0][2],expiry)
    _,rows=self.issue(revision);self.assertLessEqual(rows[0][2],datetime.now(timezone.utc)+timedelta(minutes=5))
    for bad in [datetime.now(timezone.utc)-timedelta(seconds=1),'infinity','-infinity']:
      with self.subTest(expiry=bad),self.assertRaises(self.psycopg.Error):self.issue(revision,expiry=bad)

  def test_cross_owner_wrong_session_missing_profile_and_nil_identifiers_deny(self):
    _,profile=self.current();revision=profile['profile_revision']
    for values in [{'owner':self.other,'session':self.other_sid},{'session':self.other_sid},{'session':uuid4()},
        {'session':UUID(int=0)},{'owner':UUID(int=0)}]:
      with self.subTest(values=values),self.assertRaises(self.psycopg.Error):self.issue(revision,**values)
    for bad in [None,uuid4(),UUID(int=0)]:
      with self.subTest(revision=bad),self.assertRaises(self.psycopg.Error):self.issue(bad)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_grants').fetchone()[0],0)

  def test_bad_hash_or_no_current_avatar_never_creates_grant(self):
    profile=self.save()
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.issue(profile['profile_revision'])
    args=self.ready(revision=profile['profile_revision']);profile=self.publish(args)
    for digest in ['A'*64,'a'*63,'','x'*64]:
      with self.subTest(digest=digest),self.assertRaises(self.psycopg.errors.InvalidParameterValue):
        self.run_sql('select * from public.issue_private_media_avatar_grant(%s,%s,%s,%s,clock_timestamp()+interval \'1 minute\')',
          (self.user,self.sid,digest,profile['profile_revision']))
    self.assertEqual(self.c.execute('select count(*) from public.private_media_grants').fetchone()[0],0)
    for bad in [None,'','x'*64]:self.assertEqual(self.authorize(bad,profile['profile_revision']),[])

  def test_text_edit_same_value_and_replacement_rotate_and_invalidate_old_grant(self):
    args,profile=self.current();digest,_=self.issue(profile['profile_revision'])
    updated=self.save(profile['profile_revision']);self.assertNotEqual(updated['profile_revision'],profile['profile_revision'])
    self.assertEqual(self.authorize(digest,profile['profile_revision']),[])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.issue(profile['profile_revision'])
    digest2,_=self.issue(updated['profile_revision']);self.assertTrue(self.authorize(digest2,updated['profile_revision']))
    new=self.ready(revision=updated['profile_revision']);latest=self.publish(new)
    self.assertEqual(self.authorize(digest2,updated['profile_revision']),[])
    self.assertTrue(self.issue(latest['profile_revision'])[1])
    self.assertEqual(set(self.inventory()),{('avatar',UUID(profile['profile_revision'])),('avatar',UUID(updated['profile_revision'])),('avatar',UUID(latest['profile_revision']))})

  def test_profile_delete_recreate_and_avatar_removal_invalidate(self):
    _,profile=self.current();digest,_=self.issue(profile['profile_revision'])
    self.run_sql('delete from public.profiles where id=%s',(self.user,),role='authenticated');self.save()
    self.assertEqual(self.authorize(digest,profile['profile_revision']),[])
    current=self.read();args=self.ready(revision=current['profile_revision']);current=self.publish(args)
    digest,_=self.issue(current['profile_revision']);self.run_sql('update public.profiles set avatar_path=null where id=%s',(self.user,))
    self.assertEqual(self.authorize(digest,current['profile_revision']),[])

  def test_exact_local_logout_preserves_second_session_and_global_denies_both(self):
    _,profile=self.current();revision=profile['profile_revision']
    first,_=self.issue(revision);second,_=self.issue(revision,session=self.sid2)
    self.logout();self.assertEqual(self.authorize(first,revision),[]);self.assertTrue(self.authorize(second,revision))
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.issue(revision)
    self.scalar("select public.revoke_private_media_session(%s,%s,'global')",(self.user,self.sid2))
    self.assertEqual(self.authorize(second,revision),[])

  def test_provider_and_owner_denials_invalidate_grants_and_prevent_new_issue(self):
    for denial in ['policy','session','refresh','banned','deleted_owner','missing_owner']:
      with self.subTest(denial=denial):
        self.setUp();_,profile=self.current();revision=profile['profile_revision'];digest,_=self.issue(revision)
        if denial=='policy':self.c.execute('update public.private_media_provider_policy set enabled=false')
        elif denial=='session':self.c.execute('delete from auth.sessions where id=%s',(self.sid,))
        elif denial=='refresh':self.c.execute('update auth.refresh_tokens set revoked=true where session_id=%s',(self.sid,))
        elif denial=='banned':self.c.execute("update auth.users set banned_until=clock_timestamp()+interval '1 hour' where id=%s",(self.user,))
        elif denial=='deleted_owner':self.begin()
        else:self.c.execute('truncate public.private_media_owners cascade')
        self.assertEqual(self.authorize(digest,revision),[])
        with self.assertRaises(self.psycopg.Error):self.issue(revision)

  def seed_legacy(self,path):
    # Disposable fixture only: represent historical pointers predating retained writes.
    with self.c.transaction():
      self.c.execute('alter table public.profiles disable trigger fence_profile_avatar_publication')
      self.c.execute('update public.profiles set avatar_path=%s where id=%s',(path,self.user))
      self.c.execute('alter table public.profiles enable trigger fence_profile_avatar_publication')
    return self.read()

  def test_legacy_reupload_classification_requires_current_safe_owned_path_and_live_session(self):
    self.save();profile=self.seed_legacy(f'{self.user}/old.png')
    with self.assertRaises(self.psycopg.errors.NoDataFound):self.issue(profile['profile_revision'])
    for kwargs in [{'session':self.other_sid},{'owner':self.other,'session':self.other_sid}]:
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.issue(profile['profile_revision'],**kwargs)
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.issue(uuid4())
    self.assertEqual(self.c.execute('select count(*) from public.private_media_grants').fetchone()[0],0)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_avatar_writes').fetchone()[0],0)
    self.logout()
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.issue(profile['profile_revision'])

  def test_unsafe_legacy_paths_and_present_unpublished_ledger_are_not_reupload_certificates(self):
    self.save()
    for path in [f'{self.user}/../x.jpg',f'{self.user}//x.jpg',f'{self.user}/x\\y.jpg']:
      profile=self.seed_legacy(path)
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.issue(profile['profile_revision'])
    before=self.read();args=self.ready(revision=before['profile_revision']);profile=self.seed_legacy(self.observe_args(args)[4])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.issue(profile['profile_revision'])
    self.assertIsNone(self.write(args)['published_at'])

  def test_malformed_retained_rows_are_denied_without_legacy_fallback(self):
    args,profile=self.current();revision=profile['profile_revision'];digest,_=self.issue(revision)
    changes=[("user_id=%s",(self.other,)),("provider='azure'",()),("bucket='videos'",()),("content_type='image/png'",()),
      ("size_bytes=0",()),("size_bytes=524289",()),("content_sha256='bad'",()),("state='dispatching'",()),
      ("published_at=null",()),("published_at=clock_timestamp()+interval '1 hour'",())]
    for assignment,values in changes:
      with self.subTest(assignment=assignment):
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
          with self.c.transaction():
            self.c.execute('alter table public.private_media_avatar_writes disable trigger user')
            for constraint, in self.c.execute("select conname from pg_constraint where conrelid='public.private_media_avatar_writes'::regclass and contype='c'"):
              self.c.execute(self.psycopg.sql.SQL('alter table public.private_media_avatar_writes drop constraint {}').format(self.psycopg.sql.Identifier(constraint)))
            self.c.execute('update public.private_media_avatar_writes set '+assignment+' where attempt_id=%s',(*values,args[0]))
            self.assertEqual(self.authorize(digest,revision,connection=self.c),[])
            self.issue(revision,connection=self.c)
        self.assertTrue(self.authorize(digest,revision))

  def test_service_only_acl_and_invoker_empty_search_path_bounded_locks(self):
    _,profile=self.current();revision=profile['profile_revision'];digest,_=self.issue(revision)
    funcs=[('private_media_current_avatar','uuid,uuid,uuid,boolean'),('issue_private_media_avatar_grant','uuid,uuid,text,uuid,timestamptz'),
      ('authorize_private_media_avatar_grant','text,uuid')]
    for name,signature in funcs:
      row=self.c.execute("select prosecdef,proconfig,has_function_privilege('anon',oid,'EXECUTE'),has_function_privilege('authenticated',oid,'EXECUTE'),has_function_privilege('service_role',oid,'EXECUTE'),has_function_privilege('public_probe',oid,'EXECUTE') from pg_proc where oid=%s::regprocedure",(f'public.{name}({signature})',)).fetchone()
      self.assertEqual(row[0],False);self.assertIn('search_path=""',row[1]);self.assertIn('lock_timeout=2s',row[1]);self.assertEqual(row[2:],(False,False,True,False))
    for role in ['anon','authenticated','public_probe']:
      with self.subTest(role=role),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.issue(revision,role=role)
      with self.subTest(role=role),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.authorize(digest,revision,role=role)

  def test_storage_select_denial_only_subtracts_avatar_access_and_keeps_service_read(self):
    avatar=f'{self.user}/old.png';video=f'{self.user}/old.mp4'
    self.c.execute("insert into storage.objects(bucket_id,name) values('profile-avatars',%s),('videos',%s)",(avatar,video))
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
      self.run_sql('select bucket_id,name from storage.objects order by bucket_id',role='anon')
    self.assertEqual(self.run_sql('select bucket_id,name from storage.objects order by bucket_id',role='authenticated'),[('videos',video)])
    # The real fixture grants anon no Storage schema/table access or permissive policy.
    self.assertEqual(self.c.execute("select count(*) from pg_policies where schemaname='storage' and tablename='objects' and permissive='PERMISSIVE' and roles && array['anon','public']::name[]").fetchone()[0],0)
    self.assertEqual(self.run_sql("select name from storage.objects where bucket_id='profile-avatars'"),[(avatar,)])
    self.assertEqual(self.c.execute("select permissive,cmd,roles,qual from pg_policies where policyname='avatar_backend_select_only'").fetchone()[:3],('RESTRICTIVE','SELECT',['authenticated']))

  def test_cookie_inventory_mixes_avatar_and_old_paths_across_pages_after_resource_loss(self):
    _,profile=self.current();self.issue(profile['profile_revision'])
    expected={('avatar',UUID(profile['profile_revision']))}
    for i in range(70):
      kind=['archive','avatar','video'][i%3];resource=uuid4();expected.add((kind,resource))
      for duplicate in range(1+(i%9==0)):
        self.c.execute("insert into public.private_media_grants values(%s,%s,%s,%s,%s,%s,clock_timestamp()-interval '1 second',clock_timestamp()-interval '2 seconds',clock_timestamp())",
          (hashlib.sha256(str(uuid4()).encode()).hexdigest(),self.user,self.sid,kind,resource,[kind if kind!='video' else 'playback']))
    self.c.execute('delete from public.profiles where id=%s',(self.user,))
    seen=[];after=None
    while True:
      rows=self.inventory(after=after);self.assertLessEqual(len(rows),33);seen.extend(rows[:32])
      if len(rows)<33:break
      after=rows[31]
    self.assertEqual(seen,sorted(expected));self.assertEqual(self.inventory(owner=self.other),[])
    self.assertEqual(self.inventory(sid=self.sid2),[])
    for cursor in [('Avatar',uuid4()),('avatar',UUID(int=0)),('avatar',None),(None,uuid4())]:
      with self.subTest(cursor=cursor),self.assertRaises(self.psycopg.errors.InvalidParameterValue):self.inventory(after=cursor)

  def test_post_wait_jwt_expiry_session_denial_and_bounded_owner_lock(self):
    _,profile=self.current();revision=profile['profile_revision']
    with self.psycopg.connect(fixture.DATABASE_URL) as blocker,ThreadPoolExecutor(max_workers=1) as pool:
      blocker.execute('select 1 from public.private_media_owners where user_id=%s for update',(self.user,))
      task=pool.submit(self.issue,revision,expiry=datetime.now(timezone.utc)+timedelta(seconds=.2))
      time.sleep(.3);blocker.commit()
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):task.result(timeout=3)
    with self.psycopg.connect(fixture.DATABASE_URL) as blocker,ThreadPoolExecutor(max_workers=1) as pool:
      blocker.execute('select 1 from public.private_media_owners where user_id=%s for update',(self.user,))
      task=pool.submit(self.issue,revision);time.sleep(.1)
      blocker.execute('delete from auth.sessions where id=%s',(self.sid,));blocker.commit()
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):task.result(timeout=3)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_grants').fetchone()[0],0)

  def test_profile_lock_wait_authorization_rechecks_wall_clock_expiry(self):
    _,profile=self.current();revision=profile['profile_revision'];digest,_=self.issue(revision)
    self.c.execute("update public.private_media_grants set expires_at=clock_timestamp()+interval '.2 seconds' where token_hash=%s",(digest,))
    with self.psycopg.connect(fixture.DATABASE_URL) as blocker,ThreadPoolExecutor(max_workers=1) as pool:
      blocker.execute('select 1 from public.profiles where id=%s for update',(self.user,))
      task=pool.submit(self.authorize,digest,revision);time.sleep(.3);blocker.commit()
      self.assertEqual(task.result(timeout=3),[])

  def test_profile_authorization_lock_is_bounded_and_tombstone_wait_denies(self):
    _,profile=self.current();revision=profile['profile_revision'];digest,_=self.issue(revision)
    with self.psycopg.connect(fixture.DATABASE_URL) as blocker,ThreadPoolExecutor(max_workers=1) as pool:
      blocker.execute('select 1 from public.profiles where id=%s for update',(self.user,))
      task=pool.submit(self.authorize,digest,revision)
      started=time.monotonic();self.assertEqual(task.result(timeout=3),[])
      # The authorizer maps the SQLSTATE55 denial category to an empty result.
      self.assertLess(time.monotonic()-started,3);blocker.rollback()
    with self.psycopg.connect(fixture.DATABASE_URL) as blocker,ThreadPoolExecutor(max_workers=1) as pool:
      blocker.execute('select 1 from public.private_media_owners where user_id=%s for update',(self.user,))
      task=pool.submit(self.authorize,digest,revision);time.sleep(.1)
      blocker.execute('select * from public.begin_private_media_owner_deletion(%s)',(self.user,));blocker.commit()
      self.assertEqual(task.result(timeout=3),[])


  def test_profile_edit_committed_before_issuance_lock_release_denies_old_revision(self):
    _,profile=self.current();revision=profile['profile_revision']
    with self.psycopg.connect(fixture.DATABASE_URL) as blocker,ThreadPoolExecutor(max_workers=1) as pool:
      blocker.execute("update public.profiles set display_name='Later' where id=%s",(self.user,))
      task=pool.submit(self.issue,revision);time.sleep(.1);blocker.commit()
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):task.result(timeout=3)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_grants').fetchone()[0],0)

  def test_issued_grant_transaction_blocks_late_profile_writer_without_deadlock(self):
    _,profile=self.current();revision=profile['profile_revision']
    with self.psycopg.connect(fixture.DATABASE_URL) as hold,ThreadPoolExecutor(max_workers=1) as pool:
      self.issue(revision,connection=hold)
      task=pool.submit(self.save,revision,name='Late')
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):task.result(timeout=3)
      hold.commit()
    updated=self.save(revision,name='Later');self.assertNotEqual(updated['profile_revision'],revision)

  def test_legacy_pointer_metadata_remains_editable_and_no_current_ledger_is_fabricated(self):
    self.save();profile=self.seed_legacy(f'{self.user}/legacy.png')
    with self.assertRaises(self.psycopg.errors.NoDataFound):self.issue(profile['profile_revision'])
    changed=self.save(profile['profile_revision'],name='Editable')
    self.assertEqual(changed['avatar_path'],profile['avatar_path'])
    self.assertNotEqual(changed['profile_revision'],profile['profile_revision'])
    self.assertEqual(self.c.execute('select count(*) from public.private_media_avatar_writes').fetchone()[0],0)
    normalized=self.ready(revision=changed['profile_revision']);current=self.publish(normalized,name='Editable')
    self.assertTrue(self.issue(current['profile_revision'])[1])


  def test_legacy_classification_does_not_outlive_captured_jwt_during_lock_wait(self):
    self.save();profile=self.seed_legacy(f'{self.user}/legacy.png');revision=profile['profile_revision']
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
      self.issue(revision,expiry=datetime.now(timezone.utc)-timedelta(seconds=1))
    with self.psycopg.connect(fixture.DATABASE_URL) as blocker,ThreadPoolExecutor(max_workers=1) as pool:
      blocker.execute('select 1 from public.profiles where id=%s for update',(self.user,))
      task=pool.submit(self.issue,revision,expiry=datetime.now(timezone.utc)+timedelta(seconds=.2))
      time.sleep(.3);blocker.commit()
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):task.result(timeout=3)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_grants').fetchone()[0],0)
