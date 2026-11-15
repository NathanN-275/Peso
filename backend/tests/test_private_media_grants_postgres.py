from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import time
import unittest
from urllib.parse import urlparse
from uuid import uuid4

DATABASE_URL = os.getenv('PRIVATE_MEDIA_GRANT_TEST_DATABASE_URL', '')


@unittest.skipUnless(DATABASE_URL, 'Dedicated local grant test database is not configured.')
class PrivateMediaGrantsPostgresTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    parsed = urlparse(DATABASE_URL)
    if parsed.hostname not in {'127.0.0.1', 'localhost'} or parsed.path != '/peso_media_grants_test':
      raise RuntimeError('Only owned localhost grant test DB is permitted.')
    import psycopg
    cls.psycopg = psycopg
    root = Path(__file__).resolve().parents[2]
    with psycopg.connect(DATABASE_URL, autocommit=True) as c:
      c.execute((root/'backend/tests/fixtures/security_database.sql').read_text())
      c.execute((root/'backend/tests/fixtures/video_revocation_database.sql').read_text())
      c.execute((root/'backend/tests/fixtures/private_media_grants_database.sql').read_text())
      for name in ['20260713233319_durable_analysis_jobs.sql','20260805055143_saved_lift_export_jobs.sql',
                   '202608170001_analysis_job_observability.sql','202609030001_upload_reservations.sql',
                   '202609210001_unsaved_video_retention.sql','202609210002_retention_deletion_outbox.sql',
                   '20261026170415_atomic_video_media_revocation.sql','20261026173152_private_media_provider_session_decision.sql']:
        c.execute((root/'supabase/migrations'/name).read_text())
      c.execute('grant select, insert, update, delete on public.analysis_jobs to service_role')
      paths = list((root/'supabase/migrations').glob('*_private_media_grants.sql'))
      if len(paths) != 1: raise RuntimeError('Expected one generated grant migration.')
      c.execute(paths[0].read_text())
      c.execute((root/'supabase/migrations/20261026185845_private_media_logout_receipts.sql').read_text())
      c.execute((root/'supabase/migrations/20261029173814_private_media_owner_deletion_fence.sql').read_text())
      # Seed pre-cutover rows to exercise real backfill, including a tombstone.
      legacy_video_owner,legacy_reservation_owner,deleting_owner=uuid4(),uuid4(),uuid4()
      c.execute('insert into auth.users(id) values(%s),(%s),(%s)',(legacy_video_owner,legacy_reservation_owner,deleting_owner))
      c.execute('insert into public.videos(id,user_id) values(%s,%s),(%s,%s)',(uuid4(),legacy_video_owner,uuid4(),deleting_owner))
      rid=uuid4()
      c.execute("insert into public.upload_reservations(id,user_id,blob_path,file_name,content_type,requested_bytes,source_type,exercise_type,view_type,expires_at) values(%s,%s,%s,'synthetic.mp4','video/mp4',100,'camera_roll','squat','side',clock_timestamp()+interval '10 minutes')",(rid,legacy_reservation_owner,f'{legacy_reservation_owner}/source/{rid}.mp4'))
      deletion_at=c.execute('select deleting_at from public.begin_private_media_owner_deletion(%s)',(deleting_owner,)).fetchone()[0]
      c.execute((root/'supabase/migrations/20261029175000_owner_upload_publication_fence.sql').read_text())
      c.execute((root/'supabase/migrations/20261029180203_owner_analysis_admission.sql').read_text())
      c.execute((root/'supabase/migrations/20261029181358_owner_archive_publication_fence.sql').read_text())
      backfill=dict(c.execute('select user_id,deleting_at from public.private_media_owners').fetchall())
      if backfill!={legacy_video_owner:None,legacy_reservation_owner:None,deleting_owner:deletion_at}:
        raise RuntimeError('Migration did not backfill both legacy sources and preserve the deletion tombstone.')

  def setUp(self):
    self.c = self.psycopg.connect(DATABASE_URL, autocommit=True)
    self.addCleanup(self.c.close)
    self.c.execute('truncate public.private_media_grants, public.private_media_logout_events, public.private_media_session_revocations, public.private_media_owners, public.video_deletion_outbox, public.saved_lift_export_jobs, public.videos, auth.users cascade')
    self.c.execute('''update public.private_media_provider_policy set enabled=true, auth_version='v2.197.0',
      auth_source_commit='4eee58f296d9698a1c2c0ae14d7a0b379c7622d3', timebox_seconds=0,inactivity_timeout_seconds=0,
      single_per_user=false,allow_low_aal_seconds=0,refresh_rotation_enabled=true,refresh_reuse_interval_seconds=10,
      refresh_allow_reuse=false,refresh_token_algorithm_version=2,refresh_token_upgrade_percentage=100,
      verified_at=clock_timestamp()-interval '1 minute', verified_until=clock_timestamp()+interval '1 hour' ''')
    self.user, self.other = uuid4(), uuid4()
    self.sid, self.sid2, self.video = uuid4(), uuid4(), uuid4()
    self.c.execute('insert into auth.users(id) values(%s),(%s)', (self.user,self.other))
    self.session(self.sid); self.session(self.sid2)
    self.c.execute('insert into public.private_media_owners(user_id) values(%s),(%s)',(self.user,self.other))
    self.c.execute("insert into public.videos(id,user_id,storage_path,status,save_state,is_saved,storage_state) values(%s,%s,%s,'completed','saved',true,'available')", (self.video,self.user,f'{self.user}/uploads/{self.video}.mp4'))
    self.serial = 0

  def session(self, sid, user=None):
    user = user or self.user
    self.c.execute('insert into auth.sessions(id,user_id,created_at) values(%s,%s,clock_timestamp())', (sid,user))
    self.c.execute('insert into auth.refresh_tokens(user_id,session_id) values(%s,%s)', (str(user),sid))

  def rpc(self, sql, values=(), role='service_role', connection=None):
    if connection:
      return connection.execute(sql, values).fetchall()
    with self.psycopg.connect(DATABASE_URL) as c:
      c.execute(self.psycopg.sql.SQL('set local role {}').format(self.psycopg.sql.Identifier(role)))
      c.execute("set local statement_timeout='3s'")
      return c.execute(sql, values).fetchall()

  def issue(self, sid=None, user=None, kind='video', resource=None, assets=None, expiry=None, token_hash=None, connection=None):
    self.serial += 1
    digest = token_hash if token_hash is not None else hashlib.sha256(f'synthetic-{self.serial}'.encode()).hexdigest()
    rows = self.rpc('select * from public.issue_private_media_grant(%s,%s,%s,%s,%s,%s,%s)',
      (user or self.user,sid or self.sid,digest,kind,resource or self.video, assets if assets is not None else ['playback'],expiry or datetime.now(timezone.utc)+timedelta(hours=1)), connection=connection)
    return digest, rows

  def authorize(self, digest, kind='video', resource=None, asset='playback', connection=None):
    return self.rpc('select * from public.authorize_private_media_grant(%s,%s,%s,%s)', (digest,kind,resource or self.video,asset), connection=connection)

  def logout(self, scope='global', sid=None, connection=None):
    return self.rpc('select public.revoke_private_media_session(%s,%s,%s)', (self.user,sid or self.sid,scope), connection=connection)[0][0]

  def test_issue_and_repeat_authorization_bind_exact_resource_without_raw_grant(self):
    digest, rows = self.issue(assets=['playback','thumbnail'])
    self.assertEqual(rows[0][:2], ('video',self.video))
    self.assertTrue(datetime.now(timezone.utc) < rows[0][2] <= datetime.now(timezone.utc)+timedelta(minutes=5))
    for _ in range(2):
      result = self.authorize(digest)
      self.assertEqual(result[0][:4], (self.user,self.sid,'video',self.video))
      self.assertEqual(result[0][5], [self.video])
    columns = self.c.execute("select column_name from information_schema.columns where table_name='private_media_grants'").fetchall()
    self.assertNotIn(('token',),columns)
    self.assertNotIn(('raw_grant',),columns)

  def test_grant_expiry_is_capped_by_verified_jwt(self):
    expiry=datetime.now(timezone.utc)+timedelta(seconds=40)
    digest, rows=self.issue(expiry=expiry)
    self.assertEqual(rows[0][2],expiry)
    self.c.execute('update public.private_media_grants set expires_at=clock_timestamp() where token_hash=%s',(digest,))
    self.assertEqual(self.authorize(digest),[])
    for value in [datetime.now(timezone.utc)-timedelta(seconds=1),'infinity','-infinity']:
      with self.assertRaises(self.psycopg.Error): self.issue(expiry=value)

  def test_invalid_hash_asset_scope_and_duplicate_hash_fail(self):
    for digest in ['','A'*64,'f'*63,'g'*64,'f'*65]:
      with self.subTest(digest=digest), self.assertRaises(self.psycopg.Error): self.issue(token_hash=digest)
    for assets in [[],[None],['playback','playback'],['archive'],['unknown']]:
      with self.subTest(assets=assets),self.assertRaises(self.psycopg.Error): self.issue(assets=assets)
    digest,_=self.issue()
    with self.assertRaises(self.psycopg.errors.UniqueViolation): self.issue(token_hash=digest)

  def test_wrong_owner_session_resource_and_kind_deny(self):
    for params in [dict(user=self.other),dict(sid=uuid4()),dict(resource=uuid4()),dict(kind='unknown')]:
      with self.subTest(params=params),self.assertRaises(self.psycopg.Error): self.issue(**params)
    digest,_=self.issue()
    for args in [dict(resource=uuid4()),dict(kind='archive'),dict(asset='thumbnail'),dict(asset=None)]:
      self.assertEqual(self.authorize(digest,**args),[])
    self.assertEqual(self.authorize('bad'),[])

  def test_every_authorization_observes_current_video_and_provider_state(self):
    digest,_=self.issue()
    for change in ["discarded_at=clock_timestamp()","storage_state='pruned'","expires_at=clock_timestamp() - interval '1 second'","expires_at='infinity'","user_id='%s'"%self.other]:
      with self.subTest(change=change):
        self.c.execute('update public.videos set '+change)
        self.assertEqual(self.authorize(digest),[])
        self.c.execute("update public.videos set discarded_at=null,storage_state='available',expires_at=null,user_id=%s",(self.user,))
    self.c.execute('update auth.refresh_tokens set revoked=true where session_id=%s',(self.sid,))
    self.assertEqual(self.authorize(digest),[])

  def test_actual_disabled_provider_binding_denies_issue_and_existing_grants(self):
    digest,_=self.issue()
    self.c.execute('update public.private_media_provider_policy set enabled=false')
    self.assertEqual(self.authorize(digest),[])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege): self.issue()

  def test_atomic_video_revoke_denies_existing_and_future_grants(self):
    digest,_=self.issue()
    self.rpc('select * from public.revoke_video_media(%s,%s,false)',(self.user,[self.video]))
    self.assertEqual(self.authorize(digest),[])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege): self.issue()
    self.assertTrue(self.c.execute('select discarded_at is not null from public.videos').fetchone()[0])

  def archive(self):
    job=uuid4()
    self.c.execute("insert into public.saved_lift_export_jobs(id,user_id,video_ids,status,archive_path,completed_at,expires_at) values(%s,%s,%s,'completed',%s,clock_timestamp(),clock_timestamp()+interval '1 hour')",(job,self.user,[self.video],f'{self.user}/{job}.zip'))
    return job

  def test_archive_authorization_checks_every_member_and_job_each_time(self):
    job=self.archive()
    digest,_=self.issue(kind='archive',resource=job,assets=['archive'])
    self.assertEqual(self.authorize(digest,kind='archive',resource=job,asset='archive')[0][5],[self.video])
    self.c.execute("update public.videos set save_state='pending'")
    self.assertEqual(self.authorize(digest,kind='archive',resource=job,asset='archive'),[])
    self.c.execute("update public.videos set save_state='saved'")
    self.c.execute("update public.saved_lift_export_jobs set status='expired',archive_path=null")
    self.assertEqual(self.authorize(digest,kind='archive',resource=job,asset='archive'),[])

  def test_local_logout_is_permanent_and_does_not_revoke_other_sessions(self):
    digest,_=self.issue(); other,_=self.issue(sid=self.sid2)
    self.assertTrue(self.logout('local'))
    self.assertEqual(self.authorize(digest),[])
    self.assertTrue(self.authorize(other))
    self.assertFalse(self.logout('global'))
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_events').fetchone()[0],0)
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege): self.issue()

  def test_global_logout_denies_unseen_old_sessions_and_allows_new_login(self):
    digest,_=self.issue()
    self.assertTrue(self.logout())
    self.assertEqual(self.authorize(digest),[])
    for sid in [self.sid,self.sid2]:
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege): self.issue(sid=sid)
    fresh=uuid4();self.session(fresh)
    newer,_=self.issue(sid=fresh)
    self.assertTrue(self.authorize(newer))
    self.assertFalse(self.logout())
    self.assertTrue(self.authorize(newer))

  def test_others_preserves_current_session_without_erasing_prior_revocations(self):
    current,_=self.issue(); other,_=self.issue(sid=self.sid2)
    self.assertTrue(self.logout('others'))
    self.assertTrue(self.authorize(current));self.assertEqual(self.authorize(other),[])
    self.assertFalse(self.logout('others',sid=self.sid2))
    fresh=uuid4();self.session(fresh)
    self.assertTrue(self.logout('others',sid=fresh))
    self.assertEqual(self.authorize(current),[])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege): self.issue(sid=self.sid2)

  def test_global_then_others_cannot_resurrect_old_exemption(self):
    self.issue();self.logout()
    fresh=uuid4();self.session(fresh)
    self.assertTrue(self.logout('others',sid=fresh))
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege): self.issue()
    self.assertTrue(self.issue(sid=fresh)[1])

  def test_issue_then_logout_serializes_on_owner_mutex(self):
    with self.psycopg.connect(DATABASE_URL) as held, ThreadPoolExecutor(1) as pool:
      held.execute('set local role service_role')
      digest,_=self.issue(connection=held)
      task=pool.submit(self.logout)
      time.sleep(0.05); self.assertFalse(task.done())
      held.commit();self.assertTrue(task.result(timeout=3))
    self.assertEqual(self.authorize(digest),[])

  def test_logout_then_issue_serializes_and_rechecks_after_wait(self):
    self.issue()
    with self.psycopg.connect(DATABASE_URL) as held, ThreadPoolExecutor(1) as pool:
      held.execute('set local role service_role');self.assertTrue(self.logout(connection=held))
      task=pool.submit(self.issue)
      time.sleep(0.05);self.assertFalse(task.done())
      held.commit()
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege): task.result(timeout=3)

  def test_video_revocation_waits_for_prior_authorization_then_denies_new(self):
    digest,_=self.issue()
    with self.psycopg.connect(DATABASE_URL) as held,ThreadPoolExecutor(1) as pool:
      held.execute('set local role service_role');self.assertTrue(self.authorize(digest,connection=held))
      task=pool.submit(self.rpc,'select * from public.revoke_video_media(%s,%s,false)',(self.user,[self.video]))
      time.sleep(0.05);self.assertFalse(task.done())
      held.commit();self.assertTrue(task.result(timeout=3))
    self.assertEqual(self.authorize(digest),[])

  def test_app_tables_and_rpcs_are_not_client_accessible(self):
    calls=[('select * from public.issue_private_media_grant(%s,%s,%s,%s,%s,%s,%s)',(self.user,self.sid,'a'*64,'video',self.video,['playback'],datetime.now(timezone.utc)+timedelta(minutes=1))),
      ('select * from public.authorize_private_media_grant(%s,%s,%s,%s)',('a'*64,'video',self.video,'playback')),
      ('select public.revoke_private_media_session(%s,%s,%s)',(self.user,self.sid,'global'))]
    for role in ['anon','authenticated']:
      for sql,args in calls:
        with self.subTest(role=role,sql=sql),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.rpc(sql,args,role)
      for table in ['private_media_owners','private_media_session_revocations','private_media_logout_events','private_media_grants']:
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.rpc('select * from public.'+table,role=role)
    rows=self.c.execute("select prosecdef,proconfig from pg_catalog.pg_proc where proname in ('issue_private_media_grant','authorize_private_media_grant','revoke_private_media_session')").fetchall()
    self.assertEqual(len(rows),3)
    self.assertTrue(all(not row[0] and 'search_path=""' in row[1] for row in rows))

  def test_provider_revocation_during_video_lock_wait_denies_issue(self):
    with self.psycopg.connect(DATABASE_URL) as held,ThreadPoolExecutor(1) as pool:
      held.execute('select id from public.videos where id=%s for update',(self.video,))
      task=pool.submit(self.issue)
      time.sleep(0.08);self.assertFalse(task.done())
      self.c.execute('update auth.refresh_tokens set revoked=true where session_id=%s',(self.sid,))
      held.commit()
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):task.result(timeout=3)

  def test_provider_revocation_during_video_lock_wait_denies_authorization(self):
    digest,_=self.issue()
    with self.psycopg.connect(DATABASE_URL) as held,ThreadPoolExecutor(1) as pool:
      held.execute('select id from public.videos where id=%s for update',(self.video,))
      task=pool.submit(self.authorize,digest)
      time.sleep(0.08);self.assertFalse(task.done())
      self.c.execute('update auth.refresh_tokens set revoked=true where session_id=%s',(self.sid,))
      held.commit();self.assertEqual(task.result(timeout=3),[])

  def test_wall_clock_expiry_during_video_lock_wait_denies(self):
    digest,_=self.issue()
    self.c.execute("update public.videos set expires_at=clock_timestamp()+interval '0.1 seconds'")
    with self.psycopg.connect(DATABASE_URL) as held,ThreadPoolExecutor(1) as pool:
      held.execute('select id from public.videos where id=%s for update',(self.video,))
      task=pool.submit(self.authorize,digest)
      time.sleep(0.15);self.assertFalse(task.done())
      held.commit();self.assertEqual(task.result(timeout=3),[])

  def logout_once(self, request_id, scope='global', sid=None, user=None, connection=None, role='service_role'):
    return self.rpc('select * from public.revoke_private_media_session_once(%s,%s,%s,%s)',
      (user or self.user, sid or self.sid, scope, request_id), connection=connection, role=role)

  def test_logout_receipt_global_replay_does_not_revoke_later_login(self):
    old,_=self.issue();request=uuid4()
    result=self.logout_once(request)
    self.assertFalse(result[0][1]);self.assertEqual(self.authorize(old),[])
    cutoff=self.c.execute('select cutoff from public.private_media_logout_events').fetchall()
    fresh=uuid4();self.session(fresh);current,_=self.issue(sid=fresh)
    replay=self.logout_once(request)
    self.assertEqual(replay,[(result[0][0],True)])
    self.assertEqual(self.c.execute('select cutoff from public.private_media_logout_events').fetchall(),cutoff)
    self.assertTrue(self.authorize(current))
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.logout_once(uuid4())
    self.assertTrue(self.authorize(current))

  def test_logout_receipt_local_replay_keeps_other_session_active(self):
    current,_=self.issue();other,_=self.issue(sid=self.sid2);request=uuid4()
    result=self.logout_once(request,'local')
    self.assertEqual(self.authorize(current),[]);self.assertTrue(self.authorize(other))
    self.assertEqual(self.logout_once(request,'local'),[(result[0][0],True)])
    self.assertTrue(self.authorize(other))

  def test_logout_receipt_others_replay_keeps_later_session_active(self):
    current,_=self.issue();other,_=self.issue(sid=self.sid2);request=uuid4()
    result=self.logout_once(request,'others')
    self.assertTrue(self.authorize(current));self.assertEqual(self.authorize(other),[])
    fresh=uuid4();self.session(fresh);later,_=self.issue(sid=fresh)
    self.assertEqual(self.logout_once(request,'others'),[(result[0][0],True)])
    self.assertTrue(self.authorize(current));self.assertTrue(self.authorize(later))

  def test_logout_receipt_rejects_request_rebinding(self):
    request=uuid4();self.logout_once(request,'others')
    for scope,sid in [('global',self.sid),('local',self.sid),('others',self.sid2)]:
      with self.subTest(scope=scope,sid=sid),self.assertRaises(self.psycopg.errors.InvalidParameterValue):
        self.logout_once(request,scope,sid)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_receipts').fetchone()[0],1)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_events').fetchone()[0],1)

  def test_logout_receipt_is_owner_scoped(self):
    request=uuid4();self.logout_once(request)
    sid=uuid4();self.session(sid,user=self.other)
    result=self.logout_once(request,sid=sid,user=self.other)
    self.assertFalse(result[0][1])
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_receipts').fetchone()[0],2)

  def test_logout_receipt_replay_survives_provider_denial_without_new_cutoff(self):
    request=uuid4();result=self.logout_once(request)
    self.c.execute('delete from auth.sessions where id=%s',(self.sid,))
    self.c.execute('update public.private_media_provider_policy set enabled=false')
    self.assertEqual(self.logout_once(request),[(result[0][0],True)])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.logout_once(uuid4())
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_events').fetchone()[0],1)

  def test_logout_receipt_provider_denial_never_creates_receipt(self):
    request=uuid4();self.c.execute('update public.private_media_provider_policy set enabled=false')
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.logout_once(request)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_receipts').fetchone()[0],0)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_events').fetchone()[0],0)

  def test_logout_receipt_and_revocation_roll_back_together(self):
    digest,_=self.issue();request=uuid4()
    with self.psycopg.connect(DATABASE_URL) as held:
      held.execute('set local role service_role');self.logout_once(request,connection=held);held.rollback()
    self.assertTrue(self.authorize(digest))
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_receipts').fetchone()[0],0)
    self.assertFalse(self.logout_once(request)[0][1]);self.assertEqual(self.authorize(digest),[])

  def test_logout_receipt_concurrent_replay_commits_once(self):
    self.issue();request=uuid4()
    with self.psycopg.connect(DATABASE_URL) as held,ThreadPoolExecutor(1) as pool:
      held.execute('set local role service_role');first=self.logout_once(request,connection=held)
      task=pool.submit(self.logout_once,request)
      time.sleep(0.05);self.assertFalse(task.done())
      held.commit();self.assertEqual(task.result(timeout=3),[(first[0][0],True)])
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_receipts').fetchone()[0],1)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_events').fetchone()[0],1)

  def test_logout_receipt_rejects_invalid_request_without_mutation(self):
    for request in (None,'00000000-0000-0000-0000-000000000000'):
      with self.subTest(request=request),self.assertRaises(self.psycopg.errors.InvalidParameterValue):self.logout_once(request)
    with self.assertRaises(self.psycopg.errors.InvalidParameterValue):self.logout_once(uuid4(),'invalid')
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_receipts').fetchone()[0],0)
    self.assertEqual(self.c.execute('select count(*) from public.private_media_logout_events').fetchone()[0],0)

  def test_logout_receipt_acl_and_fixed_invoker_search_path(self):
    for role in ('anon','authenticated','unrelated_caller'):
      with self.subTest(role=role),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.logout_once(uuid4(),role=role)
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.rpc('select * from public.private_media_logout_receipts',role=role)
    row=self.c.execute("select prosecdef,proconfig from pg_catalog.pg_proc where proname='revoke_private_media_session_once'").fetchone()
    self.assertFalse(row[0]);self.assertIn('search_path=""',row[1])
    self.assertTrue(self.c.execute("select relrowsecurity from pg_catalog.pg_class where oid='public.private_media_logout_receipts'::regclass").fetchone()[0])
    for command in ('update public.private_media_logout_receipts set scope=scope','delete from public.private_media_logout_receipts'):
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.rpc(command)


  def begin_owner_deletion(self, user=None, connection=None, role='service_role'):
    return self.rpc('select * from public.begin_private_media_owner_deletion(%s)',
      (user or self.user,), connection=connection, role=role)

  def read_owner_deletion(self, user=None, connection=None, role='service_role'):
    return self.rpc('select * from public.read_private_media_owner_deletion(%s)',
      (user or self.user,), connection=connection, role=role)

  def wait_for_lock(self, pid):
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
      row=self.c.execute('select wait_event_type from pg_catalog.pg_stat_activity where pid=%s',(pid,)).fetchone()
      if row and row[0]=='Lock':return
      time.sleep(0.01)
    self.fail('Expected database operation to wait on an actual PostgreSQL lock.')

  def test_owner_deletion_is_idempotent_and_revokes_current_and_future_sessions(self):
    digest,_=self.issue();other,_=self.issue(sid=self.sid2)
    first=self.begin_owner_deletion()
    self.assertFalse(first[0][1]);self.assertEqual(self.read_owner_deletion(),[(True,first[0][0])])
    self.assertEqual(self.begin_owner_deletion(),[(first[0][0],True)])
    self.assertEqual(self.authorize(digest),[]);self.assertEqual(self.authorize(other),[])
    self.assertEqual(self.c.execute('select count(*) from public.private_media_grants where revoked_at is null').fetchone()[0],0)
    fresh=uuid4();self.session(fresh)
    for sid in (self.sid,self.sid2,fresh):
      with self.subTest(sid=sid),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.issue(sid=sid)

  def test_owner_deletion_read_distinguishes_absent_live_and_deleting(self):
    self.assertEqual(self.read_owner_deletion(uuid4()),[(False,None)])
    self.issue();self.assertEqual(self.read_owner_deletion(),[(True,None)])
    first=self.begin_owner_deletion();self.assertEqual(self.read_owner_deletion(),[(True,first[0][0])])

  def test_owner_deletion_preserves_other_owner_and_existing_revocation_time(self):
    digest,_=self.issue();self.logout('local')
    at=self.c.execute('select revoked_at from public.private_media_grants where token_hash=%s',(digest,)).fetchone()[0]
    sid=uuid4();video=uuid4();self.session(sid,user=self.other)
    self.c.execute("insert into public.videos(id,user_id,storage_path,status,save_state,is_saved,storage_state) values(%s,%s,%s,'completed','saved',true,'available')",(video,self.other,f'{self.other}/uploads/{video}.mp4'))
    unrelated,_=self.issue(user=self.other,sid=sid,resource=video)
    self.begin_owner_deletion()
    self.assertEqual(self.c.execute('select revoked_at from public.private_media_grants where token_hash=%s',(digest,)).fetchone()[0],at)
    self.assertTrue(self.authorize(unrelated,resource=video));self.assertEqual(self.read_owner_deletion(self.other),[(True,None)])

  def test_owner_deletion_and_grant_revocation_roll_back_together(self):
    digest,_=self.issue()
    with self.psycopg.connect(DATABASE_URL) as held:
      held.execute('set local role service_role');self.begin_owner_deletion(connection=held);held.rollback()
    self.assertEqual(self.read_owner_deletion(),[(True,None)]);self.assertTrue(self.authorize(digest))
    self.assertFalse(self.begin_owner_deletion()[0][1])

  def test_owner_deletion_survives_auth_removal_and_disabled_provider(self):
    self.issue();first=self.begin_owner_deletion()
    self.c.execute('delete from auth.users where id=%s',(self.user,))
    self.c.execute('update public.private_media_provider_policy set enabled=false')
    self.assertEqual(self.read_owner_deletion(),[(True,first[0][0])])
    self.assertEqual(self.begin_owner_deletion(),[(first[0][0],True)])

  def test_owner_deletion_can_begin_without_auth_or_grants(self):
    unknown=uuid4();first=self.begin_owner_deletion(unknown)
    self.assertFalse(first[0][1]);self.assertEqual(self.read_owner_deletion(unknown),[(True,first[0][0])])

  def test_owner_deletion_rejects_invalid_ids_without_writes(self):
    for value in (None,'00000000-0000-0000-0000-000000000000'):
      for function in ('begin_private_media_owner_deletion','read_private_media_owner_deletion'):
        with self.subTest(value=value,function=function),self.assertRaises(self.psycopg.errors.InvalidParameterValue):
          self.rpc('select * from public.'+function+'(%s)',(value,))
    self.assertEqual(self.c.execute('select count(*) from public.private_media_owners').fetchone()[0],2)

  def test_owner_deletion_fence_is_monotonic_even_for_direct_table_writes(self):
    self.issue();first=self.begin_owner_deletion()[0][0]
    mutations=[('update public.private_media_owners set deleting_at=null where user_id=%s',(self.user,)),
      ("update public.private_media_owners set deleting_at=deleting_at+interval '1 second' where user_id=%s",(self.user,)),
      ('update public.private_media_owners set user_id=%s where user_id=%s',(self.other,self.user)),
      ('delete from public.private_media_owners where user_id=%s',(self.user,))]
    for sql,values in mutations:
      with self.subTest(sql=sql),self.assertRaises(self.psycopg.Error):self.rpc(sql,values)
    self.assertEqual(self.read_owner_deletion(),[(True,first)])
    for value in ('infinity','-infinity'):
      with self.subTest(value=value),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.rpc('insert into public.private_media_owners(user_id,deleting_at) values(%s,%s)',(uuid4(),value))
    live=uuid4();self.rpc('insert into public.private_media_owners(user_id) values(%s) returning user_id',(live,))
    for value in ('infinity','-infinity'):
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.rpc('update public.private_media_owners set deleting_at=%s where user_id=%s',(value,live))
    # The row trigger protects privileged maintenance writes as well.
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.c.execute('delete from public.private_media_owners where user_id=%s',(self.user,))

  def test_owner_deletion_service_only_acl_and_invoker_search_path(self):
    for role in ('anon','authenticated','unrelated_caller'):
      for function in ('begin_private_media_owner_deletion','read_private_media_owner_deletion'):
        with self.subTest(role=role,function=function),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
          self.rpc('select * from public.'+function+'(%s)',(self.user,),role=role)
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.rpc('select * from public.private_media_owners',role=role)
    rows=self.c.execute("select prosecdef,proconfig from pg_catalog.pg_proc where proname in ('begin_private_media_owner_deletion','read_private_media_owner_deletion','guard_private_media_owner_deletion')").fetchall()
    self.assertEqual(len(rows),3);self.assertTrue(all(not r[0] and 'search_path=""' in r[1] for r in rows))
    self.assertTrue(self.c.execute("select relrowsecurity from pg_catalog.pg_class where oid='public.private_media_owners'::regclass").fetchone()[0])

  def test_owner_deletion_keeps_prior_logout_receipt_replay(self):
    request=uuid4();receipt=self.logout_once(request,'local');self.begin_owner_deletion()
    self.assertEqual(self.logout_once(request,'local'),[(receipt[0][0],True)])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.logout_once(uuid4())

  def test_owner_deletion_waits_for_an_earlier_grant_before_revoking_it(self):
    with self.psycopg.connect(DATABASE_URL) as held,self.psycopg.connect(DATABASE_URL) as waiting,ThreadPoolExecutor(1) as pool:
      held.execute('set local role service_role');digest,_=self.issue(connection=held)
      waiting.execute('set local role service_role');waiting.execute("set local statement_timeout='5s'");pid=waiting.info.backend_pid
      task=pool.submit(self.begin_owner_deletion,connection=waiting)
      self.wait_for_lock(pid);self.assertFalse(task.done());held.commit()
      self.assertFalse(task.result(timeout=3)[0][1]);waiting.commit()
    self.assertEqual(self.authorize(digest),[])

  def test_owner_deletion_blocks_issue_authorization_and_read_until_commit(self):
    for operation in ('issue','authorize','read'):
      with self.subTest(operation=operation):
        # Restore only the synthetic fixture between the three distinct races.
        self.c.execute('truncate public.private_media_owners cascade');self.c.execute('insert into public.private_media_owners(user_id) values(%s)',(self.user,));digest,_=self.issue()
        with self.psycopg.connect(DATABASE_URL) as held,self.psycopg.connect(DATABASE_URL) as waiting,ThreadPoolExecutor(1) as pool:
          held.execute('set local role service_role');first=self.begin_owner_deletion(connection=held)
          waiting.execute('set local role service_role');waiting.execute("set local statement_timeout='5s'");pid=waiting.info.backend_pid
          if operation=='issue':task=pool.submit(self.issue,connection=waiting)
          elif operation=='authorize':task=pool.submit(self.authorize,digest,connection=waiting)
          else:task=pool.submit(self.read_owner_deletion,connection=waiting)
          self.wait_for_lock(pid);self.assertFalse(task.done());held.commit()
          if operation=='issue':
            with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):task.result(timeout=3)
            waiting.rollback()
          else:
            result=task.result(timeout=3);waiting.commit()
            self.assertEqual(result,[] if operation=='authorize' else [(True,first[0][0])])

  def test_owner_deletion_concurrent_begin_preserves_first_timestamp(self):
    self.issue()
    with self.psycopg.connect(DATABASE_URL) as held,self.psycopg.connect(DATABASE_URL) as waiting,ThreadPoolExecutor(1) as pool:
      held.execute('set local role service_role');first=self.begin_owner_deletion(connection=held)
      waiting.execute('set local role service_role');waiting.execute("set local statement_timeout='5s'");task=pool.submit(self.begin_owner_deletion,connection=waiting)
      self.wait_for_lock(waiting.info.backend_pid);held.commit()
      self.assertEqual(task.result(timeout=3),[(first[0][0],True)]);waiting.commit()



  def test_direct_privileged_owner_transition_revokes_grants_atomically(self):
    digest,_=self.issue()
    self.rpc('update public.private_media_owners set deleting_at=clock_timestamp() where user_id=%s returning user_id',(self.user,))
    self.assertIsNotNone(self.c.execute('select revoked_at from public.private_media_grants where token_hash=%s',(digest,)).fetchone()[0])
    self.assertEqual(self.authorize(digest),[])
    self.assertTrue(self.begin_owner_deletion()[0][1])

  def test_recreated_auth_identity_cannot_clear_owner_deletion(self):
    self.issue();first=self.begin_owner_deletion()
    self.c.execute('delete from auth.users where id=%s',(self.user,))
    self.c.execute('insert into auth.users(id) values(%s)',(self.user,))
    fresh=uuid4();self.session(fresh)
    self.assertEqual(self.read_owner_deletion(),[(True,first[0][0])])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.issue(sid=fresh)

  def test_owner_deletion_waits_for_prior_authorization_transaction(self):
    digest,_=self.issue()
    with self.psycopg.connect(DATABASE_URL) as held,self.psycopg.connect(DATABASE_URL) as waiting,ThreadPoolExecutor(1) as pool:
      held.execute('set local role service_role');self.assertTrue(self.authorize(digest,connection=held))
      waiting.execute('set local role service_role');waiting.execute("set local statement_timeout='5s'");task=pool.submit(self.begin_owner_deletion,connection=waiting)
      self.wait_for_lock(waiting.info.backend_pid);held.commit()
      self.assertFalse(task.result(timeout=3)[0][1]);waiting.commit()
    self.assertEqual(self.authorize(digest),[])



  def reserve_upload(self, user=None, connection=None, expiry=None):
    owner=user or self.user;rid=uuid4()
    rows=self.rpc('select id from public.reserve_video_upload(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
      (rid,owner,f'{owner}/source/{rid}.mp4','synthetic.mp4','video/mp4',100,expiry or datetime.now(timezone.utc)+timedelta(minutes=10),
       'camera_roll','squat','side',1000,None,100,100000,100,100000,100),connection=connection)
    return rows[0][0]

  def receive_upload(self, rid, lease=None, connection=None):
    lease=lease or uuid4()
    rows=self.rpc('select id from public.mark_video_upload_received(%s,%s,%s)',(rid,self.user,lease),connection=connection)
    return lease,rows

  def verify_upload(self,rid,lease,connection=None):
    return self.rpc('select video_id from public.verify_video_upload(%s,%s,%s,%s::jsonb,%s,%s)',
      (rid,self.user,100,'{"duration_ms":1000,"fps":60,"frame_count":60}',datetime.now(timezone.utc)+timedelta(hours=24),lease),connection=connection)

  def test_upload_owner_fence_keeps_normal_admission_receive_verify_and_replay(self):
    rid=self.reserve_upload();lease,rows=self.receive_upload(rid);self.assertEqual(rows,[(rid,)])
    first=self.verify_upload(rid,lease);self.assertEqual(len(first),1)
    self.assertEqual(self.verify_upload(rid,lease),first)
    self.assertEqual(self.c.execute('select state from public.upload_reservations where id=%s',(rid,)).fetchone()[0],'verified')

  def test_upload_admission_creates_a_new_owner_before_child_insert(self):
    user=uuid4();self.c.execute('insert into auth.users(id) values(%s)',(user,))
    self.assertEqual(self.read_owner_deletion(user),[(False,None)])
    self.assertTrue(self.reserve_upload(user));self.assertEqual(self.read_owner_deletion(user),[(True,None)])

  def test_deleting_owner_denies_all_upload_rpc_stages_including_verified_replay(self):
    issued=self.reserve_upload();uploaded=self.reserve_upload();verified=self.reserve_upload()
    lease,_=self.receive_upload(uploaded);vlease,_=self.receive_upload(verified);self.verify_upload(verified,vlease)
    before=self.c.execute('select id,state,video_id from public.upload_reservations order by id').fetchall()
    self.begin_owner_deletion()
    for operation in (lambda:self.reserve_upload(),lambda:self.receive_upload(issued),lambda:self.verify_upload(uploaded,lease),lambda:self.verify_upload(verified,vlease)):
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):operation()
    self.assertEqual(self.c.execute('select id,state,video_id from public.upload_reservations order by id').fetchall(),before)

  def test_deleting_owner_denies_direct_reservation_and_video_publication(self):
    rid=self.reserve_upload();self.begin_owner_deletion()
    mutations=[("update public.upload_reservations set state='uploaded' where id=%s returning id",(rid,)),
      ('update public.videos set playback_path=%s where id=%s returning id',(f'{self.user}/new.mp4',self.video)),
      ("update public.videos set is_saved=true,save_state='saved' where id=%s returning id",(self.video,)),
      ('insert into public.videos(id,user_id) values(%s,%s) returning id',(uuid4(),self.user))]
    for sql,args in mutations:
      with self.subTest(sql=sql),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.rpc(sql,args)
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.rpc('update public.videos set user_id=%s where id=%s returning id',(self.other,self.video))

  def test_revoke_only_video_update_remains_possible_without_hidden_path_change(self):
    self.begin_owner_deletion()
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.rpc("update public.videos set discarded_at=clock_timestamp(),is_saved=false,save_state='pending',expires_at=null,playback_path=%s where id=%s returning id",(f'{self.user}/hidden.mp4',self.video))
    self.assertTrue(self.rpc('select * from public.revoke_video_media(%s,%s,false)',(self.user,[self.video])))
    self.assertTrue(self.c.execute('select discarded_at is not null from public.videos where id=%s',(self.video,)).fetchone()[0])
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.rpc('update public.videos set discarded_at=null where id=%s returning id',(self.video,))

  def test_reservation_cleanup_rejection_and_fk_nulling_survive_owner_deletion(self):
    rid=self.reserve_upload();self.begin_owner_deletion()
    with self.psycopg.connect(DATABASE_URL) as c:
      c.execute('set local role service_role');c.execute('select public.reject_video_upload(%s,%s,%s)',(rid,self.user,'owner_deleting'))
      c.execute('update public.upload_reservations set blob_deleted_at=clock_timestamp(),cleanup_confirmed_at=clock_timestamp() where id=%s',(rid,))
    self.c.execute('delete from auth.users where id=%s',(self.user,))
    row=self.c.execute('select user_id,state,blob_deleted_at is not null,cleanup_confirmed_at is not null from public.upload_reservations where id=%s',(rid,)).fetchone()
    self.assertEqual(row,(None,'rejected',True,True))

  def test_reservation_cleanup_cannot_hide_media_or_identity_changes(self):
    rid=self.reserve_upload();self.begin_owner_deletion()
    updates=["state='expired',media_metadata='{}'::jsonb", "state='rejected',requested_bytes=101", "state='expired',validation_owner=gen_random_uuid()", "blob_path='changed'", "user_id='%s'"%self.other]
    for update in updates:
      with self.subTest(update=update),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.rpc('update public.upload_reservations set '+update+' where id=%s returning id',(rid,))
    self.assertEqual(self.c.execute('select state from public.upload_reservations where id=%s',(rid,)).fetchone()[0],'issued')

  def test_missing_owner_direct_writes_deny_without_creating_a_row(self):
    user=uuid4();self.c.execute('insert into auth.users(id) values(%s)',(user,))
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.rpc('insert into public.videos(id,user_id) values(%s,%s) returning id',(uuid4(),user))
    self.assertEqual(self.read_owner_deletion(user),[(False,None)])

  def test_reservation_identity_and_path_cannot_change_while_owner_is_active(self):
    rid=self.reserve_upload()
    for update in ("id=gen_random_uuid()","blob_path=blob_path||'.other'","user_id='%s'"%self.other):
      with self.subTest(update=update),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.rpc('update public.upload_reservations set '+update+' where id=%s returning id',(rid,))

  def test_reservation_owner_lock_orders_before_admission_and_rechecks_deletion(self):
    with self.psycopg.connect(DATABASE_URL) as held,self.psycopg.connect(DATABASE_URL) as waiting,ThreadPoolExecutor(1) as pool:
      held.execute('set local role service_role');self.begin_owner_deletion(connection=held)
      waiting.execute('set local role service_role');waiting.execute("set local statement_timeout='5s'")
      task=pool.submit(self.reserve_upload,connection=waiting);self.wait_for_lock(waiting.info.backend_pid);held.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):task.result(timeout=3)
      waiting.rollback()
    self.assertEqual(self.c.execute('select count(*) from public.upload_reservations').fetchone()[0],0)

  def test_accepted_reservation_transaction_finishes_before_owner_deletion(self):
    with self.psycopg.connect(DATABASE_URL) as held,self.psycopg.connect(DATABASE_URL) as waiting,ThreadPoolExecutor(1) as pool:
      held.execute('set local role service_role');rid=self.reserve_upload(connection=held)
      waiting.execute('set local role service_role');waiting.execute("set local statement_timeout='5s'")
      task=pool.submit(self.begin_owner_deletion,connection=waiting);self.wait_for_lock(waiting.info.backend_pid);held.commit()
      self.assertFalse(task.result(timeout=3)[0][1]);waiting.commit()
    self.assertEqual(self.c.execute('select state from public.upload_reservations where id=%s',(rid,)).fetchone()[0],'issued')
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):self.receive_upload(rid)

  def test_child_video_writer_fails_fast_instead_of_waiting_for_owner(self):
    with self.psycopg.connect(DATABASE_URL) as held:
      held.execute('select user_id from public.private_media_owners where user_id=%s for update',(self.user,))
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):
        self.rpc('update public.videos set fps=30 where id=%s returning id',(self.video,))
    self.assertTrue(self.rpc('update public.videos set fps=30 where id=%s returning id',(self.video,)))

  def test_child_reservation_writer_fails_fast_instead_of_waiting_for_owner(self):
    rid=self.reserve_upload()
    with self.psycopg.connect(DATABASE_URL) as held:
      held.execute('select user_id from public.private_media_owners where user_id=%s for update',(self.user,))
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):
        self.rpc("update public.upload_reservations set state='uploaded' where id=%s returning id",(rid,))
    self.assertTrue(self.receive_upload(rid)[1])

  def test_upload_owner_helpers_and_triggers_are_service_only_invokers(self):
    for role in ('anon','authenticated','unrelated_caller'):
      for sql,args in [('select public.lock_active_private_media_owner(%s,true)',(self.user,)),('select public.assert_active_private_media_owner(%s)',(self.user,))]:
        with self.subTest(role=role,sql=sql),self.assertRaises(self.psycopg.errors.InsufficientPrivilege):self.rpc(sql,args,role=role)
    rows=self.c.execute("select prosecdef,proconfig from pg_catalog.pg_proc where proname in ('lock_active_private_media_owner','assert_active_private_media_owner','fence_owner_upload_reservation','fence_owner_video_publication')").fetchall()
    self.assertEqual(len(rows),4);self.assertTrue(all(not row[0] and 'search_path=""' in row[1] for row in rows))



  def test_receive_and_verify_wait_for_owner_then_observe_committed_deletion(self):
    for operation in ('receive','verify'):
      with self.subTest(operation=operation):
        self.c.execute('truncate public.private_media_owners cascade')
        self.c.execute('insert into public.private_media_owners(user_id) values(%s),(%s)',(self.user,self.other))
        rid=self.reserve_upload();lease=None
        if operation=='verify':lease,_=self.receive_upload(rid)
        with self.psycopg.connect(DATABASE_URL) as held,self.psycopg.connect(DATABASE_URL) as waiting,ThreadPoolExecutor(1) as pool:
          held.execute('set local role service_role');self.begin_owner_deletion(connection=held)
          waiting.execute('set local role service_role');waiting.execute("set local statement_timeout='5s'")
          task=pool.submit(self.receive_upload,rid,connection=waiting) if operation=='receive' else pool.submit(self.verify_upload,rid,lease,connection=waiting)
          self.wait_for_lock(waiting.info.backend_pid);held.commit()
          with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):task.result(timeout=3)
          waiting.rollback()
        self.assertEqual(self.c.execute('select state from public.upload_reservations where id=%s',(rid,)).fetchone()[0],'issued' if operation=='receive' else 'uploaded')



  def wait_past_database_deadline(self,deadline):
    limit=time.monotonic()+3
    while time.monotonic()<limit:
      if self.c.execute('select clock_timestamp()>%s',(deadline,)).fetchone()[0]:return
      time.sleep(.01)
    self.fail('Synthetic database deadline did not pass.')

  def test_reserve_cannot_use_transaction_start_time_after_owner_wait(self):
    expiry=datetime.now(timezone.utc)+timedelta(seconds=.3)
    with self.psycopg.connect(DATABASE_URL) as held,self.psycopg.connect(DATABASE_URL) as waiting,ThreadPoolExecutor(1) as pool:
      held.execute('select user_id from public.private_media_owners where user_id=%s for update',(self.user,))
      waiting.execute('set local role service_role');waiting.execute("set local statement_timeout='5s'")
      task=pool.submit(self.reserve_upload,connection=waiting,expiry=expiry)
      self.wait_for_lock(waiting.info.backend_pid);self.wait_past_database_deadline(expiry);held.commit()
      with self.assertRaises(self.psycopg.errors.InvalidParameterValue):task.result(timeout=3)
      waiting.rollback()
    self.assertEqual(self.c.execute('select count(*) from public.upload_reservations').fetchone()[0],0)

  def test_receive_cannot_promote_expired_reservation_after_owner_wait(self):
    rid=self.reserve_upload();expiry=datetime.now(timezone.utc)+timedelta(seconds=.3)
    self.c.execute('update public.upload_reservations set expires_at=%s where id=%s',(expiry,rid))
    with self.psycopg.connect(DATABASE_URL) as held,self.psycopg.connect(DATABASE_URL) as waiting,ThreadPoolExecutor(1) as pool:
      held.execute('select user_id from public.private_media_owners where user_id=%s for update',(self.user,))
      waiting.execute('set local role service_role');waiting.execute("set local statement_timeout='5s'")
      task=pool.submit(self.receive_upload,rid,connection=waiting)
      self.wait_for_lock(waiting.info.backend_pid);self.wait_past_database_deadline(expiry);held.commit()
      self.assertEqual(task.result(timeout=3)[1],[]);waiting.commit()
    self.assertEqual(self.c.execute('select state from public.upload_reservations where id=%s',(rid,)).fetchone()[0],'issued')

  def test_verify_rechecks_reservation_and_validation_deadlines_after_owner_wait(self):
    for column in ('expires_at','validation_expires_at'):
      with self.subTest(column=column):
        rid=self.reserve_upload();lease,_=self.receive_upload(rid);expiry=datetime.now(timezone.utc)+timedelta(seconds=.3)
        self.c.execute('update public.upload_reservations set '+column+'=%s where id=%s',(expiry,rid))
        with self.psycopg.connect(DATABASE_URL) as held,self.psycopg.connect(DATABASE_URL) as waiting,ThreadPoolExecutor(1) as pool:
          held.execute('select user_id from public.private_media_owners where user_id=%s for update',(self.user,))
          waiting.execute('set local role service_role');waiting.execute("set local statement_timeout='5s'")
          task=pool.submit(self.verify_upload,rid,lease,connection=waiting)
          self.wait_for_lock(waiting.info.backend_pid);self.wait_past_database_deadline(expiry);held.commit()
          with self.assertRaises(self.psycopg.errors.RaiseException):task.result(timeout=3)
          waiting.rollback()
        self.assertEqual(self.c.execute('select state from public.upload_reservations where id=%s',(rid,)).fetchone()[0],'uploaded')



  def test_direct_upload_publication_requires_finite_live_validation_lease(self):
    rid=self.reserve_upload()
    for expiry in (None,'infinity','-infinity',datetime.now(timezone.utc)-timedelta(seconds=1)):
      with self.subTest(expiry=expiry),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.rpc("update public.upload_reservations set state='uploaded',validation_owner=%s,validation_expires_at=%s where id=%s returning id",(uuid4(),expiry,rid))
    self.assertTrue(self.receive_upload(rid)[1])



  def test_deleting_owner_allows_only_expiry_shortening_without_publication(self):
    rid=self.reserve_upload();self.begin_owner_deletion()
    self.assertTrue(self.rpc("update public.upload_reservations set expires_at=clock_timestamp()-interval '1 second' where id=%s returning id",(rid,)))
    for fields in ("expires_at=clock_timestamp()+interval '1 hour'", "expires_at=clock_timestamp()-interval '2 seconds',media_metadata='{}'"):
      with self.subTest(fields=fields),self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        self.rpc('update public.upload_reservations set '+fields+' where id=%s returning id',(rid,))


if __name__=='__main__':unittest.main()
