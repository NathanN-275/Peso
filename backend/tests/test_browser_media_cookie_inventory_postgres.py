from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import time
import unittest
from uuid import UUID, uuid4

import test_avatar_reads_postgres as avatar_fixture
import test_video_revocation_postgres as fixture


NIL = UUID(int=0)


@unittest.skipUnless(fixture.DATABASE_URL, 'Dedicated localhost cookie-inventory database is not configured.')
class BrowserMediaCookieInventoryPostgresTest(unittest.TestCase):
  connect = classmethod(avatar_fixture.AvatarReadsPostgresTest.connect.__func__)
  setUp = avatar_fixture.AvatarReadsPostgresTest.setUp
  session = avatar_fixture.AvatarReadsPostgresTest.session
  run_sql = avatar_fixture.AvatarReadsPostgresTest.run_sql

  @classmethod
  def setUpClass(cls):
    avatar_fixture.AvatarReadsPostgresTest.setUpClass.__func__(cls)
    root = Path(__file__).resolve().parents[2]
    migration = next((root/'supabase/migrations').glob('*_browser_media_cookie_inventory.sql'))
    with cls.psycopg.connect(fixture.DATABASE_URL, autocommit=True) as c:
      c.execute(migration.read_text())

  def add(self, kind, resource, *, owner=None, sid=None, expired=False, revoked=False):
    self.c.execute("insert into public.private_media_grants(token_hash,user_id,session_id,resource_kind,resource_id,asset_kinds,expires_at,revoked_at) values(%s,%s,%s,%s,%s,%s,clock_timestamp()+(case when %s then interval '-1 hour' else interval '1 hour' end),case when %s then clock_timestamp() else null end)",
      (hashlib.sha256(str(uuid4()).encode()).hexdigest(),owner or self.user,sid or self.sid,kind,resource,
       [kind if kind!='video' else 'playback'],expired,revoked))

  def inventory(self, *, owner='current', sid='current', after=(None,None,None), role='service_role', connection=None):
    return self.run_sql('select * from public.private_media_session_cookie_paths_v2(%s,%s,%s,%s,%s)',
      (self.user if owner=='current' else owner,self.sid if sid=='current' else sid,*after),role=role,connection=connection)

  def all_pages(self, **kwargs):
    seen=[];after=(None,None,None);sizes=[]
    for _ in range(100):
      rows=self.inventory(after=after,**kwargs);sizes.append(len(rows));self.assertLessEqual(len(rows),17)
      page=rows[:16];seen.extend(page)
      if len(rows)<17:return seen,sizes
      after=page[-1]
    self.fail('Cookie inventory did not terminate.')

  def test_all_kinds_exact_three_fields_and_nil_legacy_path(self):
    expected=[]
    for kind in ['archive','avatar','video']:
      resource=uuid4();self.add(kind,resource);expected.extend([(kind,resource,NIL),(kind,resource,self.sid)])
    rows=self.inventory();self.assertEqual(rows,sorted(expected));self.assertTrue(all(len(row)==3 for row in rows))

  def test_global_deduplicates_same_resource_across_sessions_and_local_never_leaks_session(self):
    resource=uuid4()
    for sid in [self.sid,self.sid,self.sid2,self.sid2]:self.add('video',resource,sid=sid)
    self.add('video',resource,owner=self.other,sid=self.other_sid)
    self.assertEqual(self.inventory(),[('video',resource,NIL),('video',resource,self.sid)])
    self.assertEqual(self.inventory(sid=self.sid2),[('video',resource,NIL),('video',resource,self.sid2)])
    self.assertEqual(self.inventory(sid=None),[('video',resource,NIL),*sorted([('video',resource,self.sid),('video',resource,self.sid2)])])
    self.assertEqual(self.inventory(owner=self.other,sid=self.other_sid),[('video',resource,NIL),('video',resource,self.other_sid)])
    self.assertEqual(self.inventory(sid=self.other_sid),[])

  def test_lookahead_pages_preserve_all_kind_resource_session_tuples_without_duplicates(self):
    expected=set()
    for i in range(48):
      kind=['archive','avatar','video'][i%3];resource=uuid4()
      for sid in [self.sid,self.sid2]:
        self.add(kind,resource,sid=sid,expired=True,revoked=True)
        self.add(kind,resource,sid=sid)
        expected.update([(kind,resource,NIL),(kind,resource,sid)])
    seen,sizes=self.all_pages(sid=None)
    self.assertEqual(seen,sorted(expected));self.assertEqual(sizes,[17,17,17,17,17,17,17,17,16])
    local,_=self.all_pages();self.assertEqual(local,[row for row in sorted(expected) if row[2] in {NIL,self.sid}])

  def test_many_sessions_on_same_resource_pages_within_session_dimension(self):
    resource=uuid4();sessions=[uuid4() for _ in range(40)]
    for sid in sessions:self.add('avatar',resource,sid=sid)
    rows,sizes=self.all_pages(sid=None)
    self.assertEqual(rows,[('avatar',resource,NIL),*[('avatar',resource,sid) for sid in sorted(sessions)]])
    self.assertEqual(sizes,[17,17,9])
    self.assertEqual(self.inventory(sid=None,after=('avatar',resource,NIL)),rows[1:18])

  def test_expired_revoked_rows_survive_resource_profile_and_provider_session_loss(self):
    expected=[]
    video=fixture.VideoRevocationPostgresTest.video(self)
    self.c.execute("insert into public.profiles(id,username) values(%s,'retained_owner')",(self.user,))
    for kind in ['archive','avatar','video']:
      resource=video if kind=='video' else uuid4();self.add(kind,resource,expired=True,revoked=True)
      expected.extend([(kind,resource,NIL),(kind,resource,self.sid)])
    self.assertEqual(self.c.execute('delete from public.profiles where id=%s returning id',(self.user,)).fetchall(),[(self.user,)])
    self.assertEqual(self.c.execute('delete from public.videos where user_id=%s returning id',(self.user,)).fetchall(),[(video,)])
    self.assertEqual(set(self.c.execute('delete from auth.sessions where user_id=%s returning id',(self.user,)).fetchall()),{(self.sid,),(self.sid2,)})
    self.assertEqual(self.inventory(),sorted(expected));self.assertEqual(self.inventory(sid=None),sorted(expected))

  def test_empty_owner_and_unknown_session_return_no_inventory(self):
    self.add('video',uuid4())
    self.assertEqual(self.inventory(owner=uuid4(),sid=None),[])
    self.assertEqual(self.inventory(sid=uuid4()),[])

  def test_nil_or_missing_context_and_incomplete_or_invalid_cursor_deny(self):
    for owner,sid in [(None,self.sid),(NIL,self.sid),(self.user,NIL)]:
      with self.subTest(owner=owner,sid=sid),self.assertRaises(self.psycopg.errors.InvalidParameterValue):
        self.inventory(owner=owner,sid=sid)
    resource=uuid4()
    for after in [('video',None,None),(None,resource,None),(None,None,self.sid),
        ('video',resource,None),('video',None,self.sid),(None,resource,self.sid),
        ('video',NIL,NIL),('Video',resource,NIL),('bad',resource,self.sid),('',resource,NIL)]:
      with self.subTest(after=after),self.assertRaises(self.psycopg.errors.InvalidParameterValue):self.inventory(after=after)
    # NIL is explicitly permitted only as the complete legacy cursor's final component.
    self.assertEqual(self.inventory(after=('avatar',resource,NIL)),[])

  def test_acl_is_service_only_invoker_empty_search_path_and_two_second_lock_bound(self):
    resource=uuid4();self.add('video',resource)
    row=self.c.execute("select prosecdef,proconfig,has_function_privilege('public_probe',oid,'EXECUTE'),has_function_privilege('anon',oid,'EXECUTE'),has_function_privilege('authenticated',oid,'EXECUTE'),has_function_privilege('service_role',oid,'EXECUTE'),pg_get_function_result(oid) from pg_proc where oid='public.private_media_session_cookie_paths_v2(uuid,uuid,text,uuid,uuid)'::regprocedure").fetchone()
    self.assertIs(row[0],False);self.assertIn('search_path=""',row[1]);self.assertIn('lock_timeout=2s',row[1])
    self.assertEqual(row[2:6],(False,False,False,True));self.assertEqual(row[6],'TABLE(resource_kind text, resource_id uuid, cookie_session_id uuid)')
    for role in ['public_probe','anon','authenticated']:
      with self.subTest(role=role),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.inventory(role=role)
    self.assertTrue(self.inventory())

  def test_owner_share_lock_wait_is_bounded_and_does_not_discard_retained_rows(self):
    resource=uuid4();self.add('archive',resource)
    with self.psycopg.connect(fixture.DATABASE_URL) as blocker,ThreadPoolExecutor(max_workers=1) as pool:
      blocker.execute('select 1 from public.private_media_owners where user_id=%s for update',(self.user,))
      started=time.monotonic();task=pool.submit(self.inventory)
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):task.result(timeout=3)
      self.assertLess(time.monotonic()-started,3);blocker.rollback()
    self.assertEqual(self.inventory(),[('archive',resource,NIL),('archive',resource,self.sid)])

  def test_v1_output_and_body_remain_unchanged_and_local_covering_index_exists(self):
    resource=uuid4();self.add('video',resource,sid=self.sid);self.add('video',resource,sid=self.sid2)
    self.assertEqual(self.run_sql('select * from public.private_media_session_cookie_paths(%s,%s,null,null)',(self.user,None)),[('video',resource)])
    index=self.c.execute("select indexdef from pg_indexes where indexname='private_media_grants_local_cookie_paths_idx'").fetchone()[0]
    self.assertIn('(user_id, session_id, resource_kind, resource_id)',index)
