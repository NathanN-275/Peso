from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import time
import unittest
from uuid import NAMESPACE_URL, uuid4, uuid5

import test_private_media_grants_postgres as fixture


@unittest.skipUnless(fixture.DATABASE_URL, 'Dedicated localhost replacement database is not configured.')
class SessionReplacementPostgresTest(unittest.TestCase):
  # Reuse the unchanged, source-pinned migration fixture without inheriting its tests.
  setUp = fixture.PrivateMediaGrantsPostgresTest.setUp
  session = fixture.PrivateMediaGrantsPostgresTest.session
  rpc = fixture.PrivateMediaGrantsPostgresTest.rpc
  issue = fixture.PrivateMediaGrantsPostgresTest.issue
  authorize = fixture.PrivateMediaGrantsPostgresTest.authorize
  logout_once = fixture.PrivateMediaGrantsPostgresTest.logout_once

  @classmethod
  def setUpClass(cls):
    fixture.PrivateMediaGrantsPostgresTest.setUpClass.__func__(cls)
    root = Path(__file__).resolve().parents[2]
    with cls.psycopg.connect(fixture.DATABASE_URL, autocommit=True) as connection:
      connection.execute((root / 'supabase/migrations/20261030232852_session_replacement_cookie_paths.sql').read_text())

  def operation(self, sid=None):
    return uuid5(NAMESPACE_URL, f'https://usepeso.com/private-media/session-replacement/v1/{self.user}/{sid or self.sid}')

  def inventory(self, *, sid='current', after=None, owner=None, role='service_role'):
    return self.rpc('select * from public.private_media_session_cookie_paths(%s,%s,%s,%s)',
      (owner or self.user, self.sid if sid == 'current' else sid, after[0] if after else None, after[1] if after else None), role=role)

  def add_path(self, kind, resource, *, sid=None, owner=None, expired=False):
    self.serial += 1
    digest = hashlib.sha256(f'synthetic-cookie-{self.serial}'.encode()).hexdigest()
    self.c.execute("insert into public.private_media_grants(token_hash,user_id,session_id,resource_kind,resource_id,asset_kinds,expires_at,revoked_at) values(%s,%s,%s,%s,%s,%s,clock_timestamp()+interval '1 minute',clock_timestamp())",
      (digest, owner or self.user, sid or self.sid, kind, resource, ['archive' if kind == 'archive' else 'playback']))
    if expired:
      self.c.execute("update public.private_media_grants set expires_at=clock_timestamp()-interval '1 second' where token_hash=%s", (digest,))

  def test_local_receipt_preserves_already_created_incoming_same_owner_session(self):
    outgoing, _ = self.issue()
    incoming, _ = self.issue(sid=self.sid2)
    self.assertNotEqual(self.operation(), self.sid)
    receipt = self.logout_once(self.operation(), 'local')
    self.assertEqual(self.authorize(outgoing), [])
    self.assertTrue(self.authorize(incoming))
    self.assertTrue(self.issue(sid=self.sid2)[1])
    self.assertEqual(self.logout_once(self.operation(), 'local'), [(receipt[0][0], True)])
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_events').fetchone()[0], 0)

  def test_inventory_keeps_deleted_resource_expired_revoked_and_duplicate_paths_without_other_sessions(self):
    missing = uuid4()
    self.add_path('video', missing, expired=True)
    self.add_path('video', missing)
    archive = uuid4()
    self.add_path('archive', archive)
    unrelated_session = uuid4()
    self.add_path('video', unrelated_session, sid=self.sid2)
    unrelated_owner = uuid4()
    self.add_path('video', unrelated_owner, owner=self.other)
    self.assertEqual(self.inventory(), [('archive', archive), ('video', missing)])
    self.assertEqual(self.inventory(sid=None), [('archive', archive), *sorted([('video', missing), ('video', unrelated_session)])])
    self.assertEqual(self.c.execute('select id from public.videos where id=%s', (missing,)).fetchall(), [])

  def test_inventory_keyset_has_33_row_lookahead_and_no_lost_or_duplicate_paths(self):
    wanted = []
    for index in range(65):
      item = ('archive' if index < 34 else 'video', uuid4())
      wanted.append(item)
      self.add_path(*item)
      if index % 7 == 0:
        self.add_path(*item)
    seen = []
    after = None
    sizes = []
    while True:
      rows = self.inventory(after=after)
      sizes.append(len(rows))
      self.assertLessEqual(len(rows), 33)
      page = rows[:32]
      seen.extend(page)
      if len(rows) < 33:
        break
      after = page[-1]
    self.assertEqual(sizes, [33, 33, 1])
    self.assertEqual(seen, sorted(wanted))

  def test_inventory_validates_cursor_and_excludes_unrelated_owner(self):
    self.add_path('video', self.video)
    self.assertEqual(self.inventory(owner=self.other), [])
    nil = '00000000-0000-0000-0000-000000000000'
    for args in ((None, self.sid, None, None), (nil, self.sid, None, None), (self.user, nil, None, None),
                 (self.user, self.sid, 'other', self.video), (self.user, self.sid, 'video', None),
                 (self.user, self.sid, None, self.video), (self.user, self.sid, 'video', nil)):
      with self.subTest(args=args), self.assertRaises(self.psycopg.errors.InvalidParameterValue):
        self.rpc('select * from public.private_media_session_cookie_paths(%s,%s,%s,%s)', args)

  def test_inventory_acl_and_index_are_service_only_invoker_and_keyset_ordered(self):
    for role in ('anon', 'authenticated', 'unrelated_caller'):
      with self.subTest(role=role), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.inventory(role=role)
    definition = self.c.execute("select prosecdef,proconfig from pg_proc where oid='public.private_media_session_cookie_paths(uuid,uuid,text,uuid)'::regprocedure").fetchone()
    self.assertEqual(definition, (False, ['search_path=""']))
    index = self.c.execute("select pg_get_indexdef('public.private_media_grants_cookie_paths_idx'::regclass)").fetchone()[0]
    self.assertIn('(user_id, resource_kind, resource_id, session_id)', index)

  def test_sql_replay_after_provider_denial_does_not_bypass_first_revocation_auth(self):
    self.issue()
    receipt = self.logout_once(self.operation(), 'local')
    self.c.execute('delete from auth.sessions where id=%s', (self.sid,))
    self.assertEqual(self.logout_once(self.operation(), 'local'), [(receipt[0][0], True)])
    self.assertEqual(self.inventory(), [('video', self.video)])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
      self.logout_once(uuid4(), 'local')
    self.assertTrue(self.issue(sid=self.sid2)[1])

  def test_local_commit_serializes_issuance_and_rollback_retains_old_session(self):
    outgoing, _ = self.issue()
    with self.psycopg.connect(fixture.DATABASE_URL) as held:
      held.execute('set local role service_role')
      self.logout_once(self.operation(), 'local', connection=held)
      held.rollback()
    self.assertTrue(self.authorize(outgoing))
    with self.psycopg.connect(fixture.DATABASE_URL) as held, ThreadPoolExecutor(1) as pool:
      held.execute('set local role service_role')
      self.logout_once(self.operation(), 'local', connection=held)
      waiting = pool.submit(self.issue)
      time.sleep(.08)
      self.assertFalse(waiting.done())
      held.commit()
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        waiting.result(timeout=3)
    self.assertEqual(self.authorize(outgoing), [])
    self.assertTrue(self.issue(sid=self.sid2)[1])


if __name__ == '__main__':
  unittest.main()
