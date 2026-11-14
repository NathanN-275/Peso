from __future__ import annotations

import json
import ipaddress
import os
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from refresh_us_ip_dataset import Dataset, release_window, replace_dataset


DATABASE_URL = os.getenv("SECURITY_TEST_DATABASE_URL", "")


@unittest.skipUnless(DATABASE_URL, "Dedicated Postgres security test database is not configured.")
class UploadReservationsPostgresTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    parsed = urlparse(DATABASE_URL)
    if parsed.hostname not in {"localhost", "127.0.0.1"} or parsed.path != "/peso_security_test":
      raise RuntimeError("Security integration tests require the dedicated localhost peso_security_test database.")
    import psycopg
    cls.psycopg = psycopg
    root = Path(__file__).resolve().parents[2]
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
      connection.execute((Path(__file__).parent / "fixtures/security_database.sql").read_text())
      connection.execute((Path(__file__).parent / "fixtures/video_revocation_database.sql").read_text())
      connection.execute((Path(__file__).parent / "fixtures/private_media_grants_database.sql").read_text())
      for name in ("20260713233319_durable_analysis_jobs.sql", "20260805055143_saved_lift_export_jobs.sql", "202608170001_analysis_job_observability.sql"):
        connection.execute((root / "supabase/migrations" / name).read_text())
      connection.execute("grant select, insert, update, delete on public.analysis_jobs to service_role")
      connection.execute((root / "supabase/migrations/202609030001_upload_reservations.sql").read_text())
      connection.execute((root / "supabase/migrations/202609210001_unsaved_video_retention.sql").read_text())
      connection.execute((root / "supabase/migrations/202609210002_retention_deletion_outbox.sql").read_text())
      connection.execute((root / "supabase/migrations/20260922002632_intake_stop_reason.sql").read_text())
      connection.execute((root / "supabase/migrations/20260922003008_us_ip_beta_admission.sql").read_text())
      connection.execute((root / "supabase/migrations/20261029020225_us_ip_expiry_wall_clock.sql").read_text())
      connection.execute((root / "supabase/migrations/20260923224101_budget_alert_delivery.sql").read_text())
      connection.execute((root / "supabase/migrations/20261027182727_queue_video_revocation_fence.sql").read_text())
      for name in ("20261026170415_atomic_video_media_revocation.sql", "20261026173152_private_media_provider_session_decision.sql",
                   "20261026182051_private_media_grants.sql", "20261026185845_private_media_logout_receipts.sql",
                   "20261029173814_private_media_owner_deletion_fence.sql", "20261029175000_owner_upload_publication_fence.sql", "20261029180203_owner_analysis_admission.sql", "20261029181358_owner_archive_publication_fence.sql"):
        connection.execute((root / "supabase/migrations" / name).read_text())

  def setUp(self):
    self.user = uuid4()
    self.other = uuid4()
    with self.psycopg.connect(DATABASE_URL, autocommit=True) as connection:
      connection.execute("truncate public.private_media_owners, public.us_beta_ip_ranges, public.budget_alert_delivery, public.video_deletion_outbox, public.analysis_jobs, public.videos, public.upload_reservations, auth.users cascade")
      connection.execute("update public.upload_admission_control set enabled = true where id = 1")
      connection.execute("insert into auth.users values (%s), (%s)", (self.user, self.other))
      connection.execute("insert into public.private_media_owners(user_id) values (%s), (%s)", (self.user, self.other))

  def rpc(self, sql, values=(), role="service_role"):
    with self.psycopg.connect(DATABASE_URL) as connection:
      connection.execute(f"set local role {role}")
      return connection.execute(sql, values).fetchall()

  def reserve(self, user=None, max_user=3, max_global=4, size=100):
    reservation = uuid4()
    owner = user or self.user
    self.rpc(
      "select id from public.reserve_video_upload(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
      (reservation, owner, f"{owner}/source/{reservation}.mp4", "lift.mp4", "video/mp4", size,
       datetime.now(timezone.utc) + timedelta(minutes=10), "camera_roll", "squat", "side",
       1, None, max_user, 10000, max_global, 10000, 100),
    )
    return reservation

  def verify(self, reservation, owner=None):
    owner = owner or self.user
    lease = uuid4()
    self.rpc("select id from public.mark_video_upload_received(%s,%s,%s)", (reservation, owner, lease))
    return self.rpc(
      "select video_id from public.verify_video_upload(%s,%s,%s,%s::jsonb,%s,%s)",
      (reservation, owner, 100, json.dumps({"duration_ms": 1000, "fps": 60, "frame_count": 60}),
       datetime.now(timezone.utc) + timedelta(hours=24), lease),
    )[0][0]

  def test_concurrent_reservations_never_exceed_user_or_global_count(self):
    def attempt(index):
      try:
        self.reserve(self.user if index % 2 else self.other, max_user=3, max_global=4)
        return True
      except self.psycopg.errors.RaiseException:
        return False
    with ThreadPoolExecutor(max_workers=16) as pool:
      accepted = list(pool.map(attempt, range(24)))
    self.assertEqual(sum(accepted), 4)
    counts = self.rpc("select user_id, count(*) from public.upload_reservations group by user_id")
    self.assertTrue(all(count <= 3 for _, count in counts))

  def test_budget_alert_claim_is_unique_and_client_roles_cannot_access_ledger(self):
    month = '2026-09-01'
    identifiers = [uuid4() for _ in range(12)]
    def attempt(claim_id):
      return self.rpc('select public.claim_budget_alert(%s,%s,%s)', (month, 15, claim_id))[0][0]
    with ThreadPoolExecutor(max_workers=12) as pool:
      results = list(pool.map(attempt, identifiers))
    self.assertEqual(sum(results), 1)
    winning = identifiers[results.index(True)]
    self.assertEqual(self.rpc('select public.complete_budget_alert(%s,%s,%s)', (month, 15, winning)), [(True,)])
    self.assertEqual(attempt(uuid4()), False)
    self.assertEqual(self.rpc('select public.release_budget_alert(%s,%s,%s)', (month, 15, winning)), [(False,)])
    for role in ('anon', 'authenticated'):
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.rpc('select * from public.budget_alert_delivery', role=role)
      with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.rpc('select public.claim_budget_alert(%s,%s,%s)', (month, 25, uuid4()), role=role)

  def test_concurrent_byte_reservations_do_not_overbook(self):
    def attempt(_index):
      try:
        self.reserve(max_user=100, max_global=100, size=3000)
        return True
      except self.psycopg.errors.RaiseException:
        return False
    with ThreadPoolExecutor(max_workers=8) as pool:
      accepted = list(pool.map(attempt, range(10)))
    self.assertEqual(sum(accepted), 3)

  def test_queue_requires_verified_upload_and_enforces_user_limit_atomically(self):
    videos = [self.verify(self.reserve()) for _ in range(2)]
    first = self.rpc("select id from public.enqueue_video_analysis_job(%s,false,1,20)", (videos[0],))
    self.assertEqual(first, self.rpc("select id from public.enqueue_video_analysis_job(%s,false,1,20)", (videos[0],)))
    with self.assertRaises(self.psycopg.errors.RaiseException):
      self.rpc("select id from public.enqueue_video_analysis_job(%s,false,1,20)", (videos[1],))
    states = self.rpc("select state from public.upload_reservations order by state")
    self.assertEqual(states, [("consumed",), ("verified",)])

  def test_foreign_user_cannot_claim_or_verify_reservation(self):
    reservation = self.reserve()
    rows = self.rpc("select id from public.mark_video_upload_received(%s,%s,%s)", (reservation, self.other, uuid4()))
    self.assertEqual(rows, [])
    with self.assertRaises(self.psycopg.errors.RaiseException):
      self.verify(reservation, self.other)

  def test_validation_leases_bound_concurrency_and_prevent_duplicate_completion(self):
    reservations = [self.reserve() for _ in range(3)]
    lease = uuid4()
    self.rpc("select id from public.mark_video_upload_received(%s,%s,%s)", (reservations[0], self.user, lease))
    self.assertEqual(self.rpc("select id from public.mark_video_upload_received(%s,%s,%s)",
                             (reservations[0], self.user, uuid4())), [])
    self.rpc("select id from public.mark_video_upload_received(%s,%s,%s)", (reservations[1], self.user, uuid4()))
    with self.assertRaises(self.psycopg.errors.RaiseException):
      self.rpc("select id from public.mark_video_upload_received(%s,%s,%s)", (reservations[2], self.user, uuid4()))

  def test_legacy_unverified_video_cannot_enter_analysis_queue(self):
    video = uuid4()
    with self.psycopg.connect(DATABASE_URL) as connection:
      connection.execute("insert into public.videos (id,user_id,storage_path,status) values (%s,%s,%s,'uploaded')",
                         (video, self.user, f"{self.user}/legacy.mp4"))
    with self.assertRaises(self.psycopg.errors.RaiseException):
      self.rpc("select id from public.enqueue_video_analysis_job(%s,false,3,20)", (video,))

  def test_client_roles_cannot_read_or_mutate_security_tables_or_invoke_admission(self):
    for role in ("anon", "authenticated"):
      for sql in (
        "select * from public.upload_reservations",
        "select * from public.upload_admission_control",
        "select public.disable_video_upload_admission()",
      ):
        with self.subTest(role=role, sql=sql), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
          self.rpc(sql, role=role)

  def test_expiry_and_budget_shutdown_are_database_enforced(self):
    reservation = self.reserve()
    with self.psycopg.connect(DATABASE_URL) as connection:
      connection.execute("update public.upload_reservations set expires_at=now()-interval '1 second' where id=%s", (reservation,))
    rows = self.rpc("select id from public.mark_video_upload_received(%s,%s,%s)", (reservation, self.user, uuid4()))
    self.assertEqual(rows, [])
    expired = self.rpc("select reservation_id from public.expire_video_upload_reservations(100)")
    self.assertEqual(expired, [(reservation,)])
    self.rpc("select public.disable_video_upload_admission()")
    with self.assertRaises(self.psycopg.errors.NoDataFound):
      self.reserve()

  def test_account_deletion_preserves_cleanup_tombstone(self):
    reservation = self.reserve()
    with self.psycopg.connect(DATABASE_URL) as connection:
      connection.execute("delete from auth.users where id=%s", (self.user,))
    self.assertEqual(self.rpc("select user_id from public.upload_reservations where id=%s", (reservation,)), [(None,)])

  def test_intake_stop_preserves_accepted_uploads_and_queue_admission(self):
    accepted = self.reserve()
    self.rpc('select public.disable_video_upload_admission()')
    with self.assertRaises(self.psycopg.errors.NoDataFound):
      self.reserve()
    self.assertEqual(self.rpc('select count(*) from public.upload_reservations'), [(1,)])
    video = self.verify(accepted)
    self.assertTrue(self.rpc('select id from public.enqueue_video_analysis_job(%s,false,3,20)', (video,)))
    self.assertEqual(self.rpc('select state from public.upload_reservations where id=%s', (accepted,)), [('consumed',)])
    self.assertEqual(self.rpc('select enabled from public.upload_admission_control'), [(False,)])

  def test_admission_stop_waits_for_existing_reservation_transaction(self):
    with ThreadPoolExecutor(max_workers=1) as pool:
      with self.psycopg.connect(DATABASE_URL) as connection:
        connection.execute("select pg_advisory_xact_lock(hashtextextended('peso:upload-capacity',0))")
        stopping = pool.submit(self.rpc, 'select public.disable_video_upload_admission()')
        self.assertEqual(connection.execute('select enabled from public.upload_admission_control').fetchall(), [(True,)])
      stopping.result(timeout=10)
    with self.assertRaises(self.psycopg.errors.NoDataFound):
      self.reserve()

  def expired_video(self):
    video = self.verify(self.reserve())
    self.rpc("insert into public.analysis_results(video_id,result_json) values (%s,'{}') returning id", (video,))
    self.rpc("update public.videos set expires_at=now()-interval '1 second', status='completed' where id=%s returning id", (video,))
    return video

  def test_retention_atomically_removes_history_results_and_keeps_retry_paths(self):
    video = self.expired_video()
    paths = self.rpc("select storage_path from public.videos where id=%s", (video,))
    claimed = self.rpc("select video_id, storage_paths from public.claim_expired_video_deletion(%s)", (video,))
    self.assertEqual(claimed, [(video, [paths[0][0]])])
    self.assertEqual(self.rpc("select id from public.videos where id=%s", (video,)), [])
    self.assertEqual(self.rpc("select id from public.analysis_results where video_id=%s", (video,)), [])
    self.assertEqual(self.rpc("select video_id from public.claim_expired_video_deletion(%s)", (video,)), [])
    self.assertEqual(self.rpc("select video_id from public.video_deletion_outbox"), [(video,)])
    # A late result cannot resurrect a deleted analysis/history entry.
    with self.assertRaises(self.psycopg.errors.ForeignKeyViolation):
      self.rpc("insert into public.analysis_results(video_id,result_json) values (%s,'{}') returning id", (video,))

  def test_retention_preserves_saved_and_unexpired_videos_and_active_jobs(self):
    video = self.expired_video()
    for assignment in ("save_state='saved'", "save_state='pending',is_saved=true", "is_saved=false,expires_at=now()+interval '1 hour'"):
      self.rpc(f"update public.videos set {assignment} where id=%s returning id", (video,))
      self.assertEqual(self.rpc("select * from public.claim_expired_video_deletion(%s)", (video,)), [])
    self.rpc("update public.videos set expires_at=now()-interval '1 second' where id=%s returning id", (video,))
    for state in ('queued', 'processing', 'retry_wait'):
      self.rpc("update public.videos set expires_at=now()+interval '1 hour' where id=%s returning id", (video,))
      job = self.rpc("insert into public.analysis_jobs(video_id,status,lease_owner,lease_expires_at) values (%s,%s,%s,%s) returning id",
                     (video, state, "synthetic-worker" if state == "processing" else None,
                      datetime.now(timezone.utc)+timedelta(minutes=1) if state == "processing" else None))[0][0]
      self.rpc("update public.videos set expires_at=now()-interval '1 second' where id=%s returning id", (video,))
      self.assertEqual(self.rpc("select * from public.claim_expired_video_deletion(%s)", (video,)), [])
      self.rpc("delete from public.analysis_jobs where id=%s returning id", (job,))

  def test_save_winning_lock_prevents_retention_deletion(self):
    video = self.expired_video()
    with ThreadPoolExecutor(max_workers=1) as pool:
      with self.psycopg.connect(DATABASE_URL) as connection:
        connection.execute("update public.videos set save_state='saved', expires_at=null where id=%s", (video,))
        cleanup = pool.submit(self.rpc, "select * from public.claim_expired_video_deletion(%s)", (video,))
      self.assertEqual(cleanup.result(timeout=10), [])
    self.assertEqual(self.rpc("select save_state from public.videos where id=%s", (video,)), [('saved',)])

  def test_cleanup_winning_lock_cannot_be_undone_by_a_late_save(self):
    video = self.expired_video()
    with ThreadPoolExecutor(max_workers=1) as pool:
      with self.psycopg.connect(DATABASE_URL) as connection:
        connection.execute("select * from public.claim_expired_video_deletion(%s)", (video,)).fetchall()
        save = pool.submit(self.rpc, "update public.videos set save_state='saved' where id=%s returning id", (video,))
      self.assertEqual(save.result(timeout=10), [])
    self.assertEqual(self.rpc("select video_id from public.video_deletion_outbox"), [(video,)])

  def test_concurrent_retention_claims_create_one_durable_deletion(self):
    video = self.expired_video()
    with ThreadPoolExecutor(max_workers=8) as pool:
      claims = list(pool.map(lambda _: self.rpc("select video_id from public.claim_expired_video_deletion(%s)", (video,)), range(8)))
    self.assertEqual(sum(len(rows) for rows in claims), 1)

  def test_client_roles_cannot_read_or_claim_media_deletions(self):
    for role in ('anon', 'authenticated'):
      for sql in ('select * from public.video_deletion_outbox', "select * from public.claim_expired_video_deletion('00000000-0000-0000-0000-000000000000')"):
        with self.subTest(role=role), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
          self.rpc(sql, role=role)

  def test_signup_hook_uses_only_auth_ip_and_fails_closed_without_current_ranges(self):
    def hook(ip, **extra):
      event = {'metadata': {'name':'before-user-created', 'ip_address':ip}, **extra}
      return self.rpc('select public.hook_us_ip_before_user_created(%s::jsonb)',
                      (json.dumps(event),), role='supabase_auth_admin')[0][0]
    self.assertEqual(hook('192.0.2.1')['error']['http_code'], 403)
    with self.psycopg.connect(DATABASE_URL) as connection:
      connection.execute("insert into public.us_beta_ip_ranges values ('192.0.2.0/24','test-only',now()+interval '1 hour')")
    try:
      self.assertEqual(hook('192.0.2.1'), {})
      for address in ('198.51.100.1', 'invalid', '', None):
        self.assertEqual(hook(address, user={'user_metadata': {'country':'US', 'ip_address':'192.0.2.1'}})['error']['http_code'], 403)
      for role in ('anon','authenticated','service_role'):
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
          self.rpc("select public.hook_us_ip_before_user_created('{}')", role=role)
      with self.psycopg.connect(DATABASE_URL) as connection:
        connection.execute("update public.us_beta_ip_ranges set valid_until=now()-interval '1 second'")
      self.assertEqual(hook('192.0.2.1')['error']['http_code'], 403)
    finally:
      with self.psycopg.connect(DATABASE_URL) as connection:
        connection.execute('delete from public.us_beta_ip_ranges')


  def test_geography_requires_finite_current_ranges_for_ipv4_and_ipv6(self):
    with self.psycopg.connect(DATABASE_URL) as connection:
      for network, deadline in [
        ('192.0.2.0/24', "clock_timestamp()+interval '1 hour'"),
        ('2001:db8:1::/48', "clock_timestamp()+interval '1 hour'"),
        ('198.51.100.0/24', "clock_timestamp()-interval '1 second'"),
        ('203.0.113.0/24', "'infinity'::timestamptz"),
        ('2001:db8:2::/48', "'infinity'::timestamptz"),
        ('2001:db8:3::/48', "'-infinity'::timestamptz"),
      ]:
        connection.execute(f"insert into public.us_beta_ip_ranges values (%s,'test-only',{deadline})", (network,))
    for address, expected in [('192.0.2.1', True), ('2001:db8:1::1', True),
      ('198.51.100.1', False), ('203.0.113.1', False), ('2001:db8:2::1', False),
      ('2001:db8:3::1', False), ('2001:db8:4::1', False), (None, False)]:
      with self.subTest(address=address):
        for role in ('service_role', 'supabase_auth_admin'):
          self.assertEqual(self.rpc('select public.is_us_beta_ip(%s::inet)', (address,), role=role), [(expected,)])
        event = {'metadata': {'name': 'before-user-created', 'ip_address': address},
                 'user': {'user_metadata': {'country': 'US', 'ip_address': '192.0.2.1'}}}
        result = self.rpc('select public.hook_us_ip_before_user_created(%s::jsonb)',
                          (json.dumps(event),), role='supabase_auth_admin')[0][0]
        self.assertEqual(result, {} if expected else {'error': {
          'http_code': 403,
          'message': 'This beta accepts signup from US IP addresses. VPNs and proxies may affect detection; IP location does not establish residency.',
        }})

  def test_geography_expiry_advances_inside_one_transaction_for_rpc_and_hook(self):
    addresses = ['192.0.2.1', '2001:db8:1::1']
    for role in ('service_role', 'supabase_auth_admin'):
      with self.subTest(role=role), self.psycopg.connect(DATABASE_URL) as connection:
        connection.execute('delete from public.us_beta_ip_ranges')
        deadline = connection.execute("select clock_timestamp()+interval '1 second'").fetchone()[0]
        for network in ('192.0.2.0/24', '2001:db8:1::/48'):
          connection.execute("insert into public.us_beta_ip_ranges values (%s,'test-only',%s)", (network, deadline))
        connection.execute(f'set local role {role}')
        transaction = connection.execute('select txid_current()').fetchone()[0]
        def allowed(address):
          return connection.execute('select public.is_us_beta_ip(%s::inet)', (address,)).fetchone()[0]
        def hook(address):
          event = {'metadata': {'name': 'before-user-created', 'ip_address': address}}
          return connection.execute('select public.hook_us_ip_before_user_created(%s::jsonb)', (json.dumps(event),)).fetchone()[0]
        for address in addresses:
          self.assertTrue(allowed(address))
          if role == 'supabase_auth_admin': self.assertEqual(hook(address), {})
        # Wait until database wall time passes expiry without ending this transaction.
        connection.execute('select pg_sleep(greatest(0, extract(epoch from %s::timestamptz-clock_timestamp()))+0.02)', (deadline,))
        self.assertEqual(connection.execute('select now() < %s, clock_timestamp() >= %s, txid_current()',
                                           (deadline, deadline)).fetchone(), (True, True, transaction))
        for address in addresses:
          self.assertFalse(allowed(address))
          if role == 'supabase_auth_admin': self.assertEqual(hook(address)['error']['http_code'], 403)

  def test_geography_lookup_retains_internal_only_invoker_permissions_and_volatile_clock(self):
    with self.psycopg.connect(DATABASE_URL) as connection:
      self.assertEqual(connection.execute("select provolatile, prosecdef, proconfig from pg_proc where oid='public.is_us_beta_ip(inet)'::regprocedure").fetchone(),
                       ('v', False, ['search_path=""']))
      for role, allowed in [('anon', False), ('authenticated', False), ('service_role', True), ('supabase_auth_admin', True)]:
        self.assertEqual(connection.execute("select has_function_privilege(%s,'public.is_us_beta_ip(inet)','EXECUTE'), has_table_privilege(%s,'public.us_beta_ip_ranges','SELECT')",
                                           (role, role)).fetchone(), (allowed, allowed))
    for role in ('anon', 'authenticated'):
      with self.subTest(role=role), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.rpc("select public.is_us_beta_ip('192.0.2.1')", role=role)


  def geography_dataset(self, digest="a", networks=("192.0.2.0/25", "2001:db8:1::/48")):
    # Documentation-only ranges; these bypass the production parser solely to
    # exercise SQL transactions, never to become a deployable dataset.
    now = datetime.now(timezone.utc)
    release = now.strftime("%Y-%m")
    return Dataset(release, digest * 64, release_window(release, now), networks, 2, {4: 1, 6: 1}, 0)

  def geography_rows(self):
    with self.psycopg.connect(DATABASE_URL) as connection:
      return connection.execute('select network::text, source_version, valid_until from public.us_beta_ip_ranges order by network').fetchall()

  def test_geography_refresh_is_atomic_for_readers_and_replay_does_not_extend_expiry(self):
    first = self.geography_dataset()
    second = self.geography_dataset(networks=("192.0.2.128/25", "2001:db8:2::/48"))
    with self.psycopg.connect(DATABASE_URL, autocommit=True) as writer:
      replace_dataset(writer, first)
      original = self.geography_rows()
      with writer.transaction():
        replace_dataset(writer, second)
        self.assertEqual(self.geography_rows(), original)
      self.assertEqual({row[0] for row in self.geography_rows()}, set(second.networks))
      replace_dataset(writer, second)
    self.assertEqual({row[2] for row in self.geography_rows()}, {first.valid_until})
    self.assertEqual(self.rpc("select public.is_us_beta_ip('192.0.2.1'), public.is_us_beta_ip('192.0.2.129')"), [(False, True)])

  def test_geography_refresh_insert_failure_rolls_back_deleted_rows_and_is_retryable(self):
    first = self.geography_dataset()
    second = self.geography_dataset(networks=("192.0.2.128/25", "2001:db8:2::/48"))
    with self.psycopg.connect(DATABASE_URL, autocommit=True) as writer:
      replace_dataset(writer, first)
      original = self.geography_rows()
      writer.execute("alter table public.us_beta_ip_ranges add constraint fixture_reject_new_range check (network <> '192.0.2.128/25'::cidr) not valid")
      try:
        with self.assertRaises(self.psycopg.errors.CheckViolation):
          replace_dataset(writer, second)
        self.assertEqual(self.geography_rows(), original)
      finally:
        writer.execute('alter table public.us_beta_ip_ranges drop constraint fixture_reject_new_range')
      replace_dataset(writer, second)
      self.assertEqual({row[0] for row in self.geography_rows()}, set(second.networks))

  def test_geography_refresh_rejects_concurrent_conflicting_versions_and_coverage_changes(self):
    datasets = [self.geography_dataset(digest="a"), self.geography_dataset(digest="b")]
    def attempt(dataset):
      with self.psycopg.connect(DATABASE_URL, autocommit=True) as writer:
        try:
          replace_dataset(writer, dataset)
          return True
        except ValueError:
          return False
    with ThreadPoolExecutor(max_workers=2) as pool:
      self.assertEqual(sorted(pool.map(attempt, datasets)), [False, True])
    original = self.geography_rows()
    digest = 'a' if '/'+ 'a'*64 == original[0][1][-65:] else 'b'
    changed = self.geography_dataset(digest=digest, networks=("192.0.2.0/24", "2001:db8:1::/48"))
    with self.psycopg.connect(DATABASE_URL, autocommit=True) as writer:
      with self.assertRaisesRegex(ValueError, 'coverage'):
        replace_dataset(writer, changed)
    self.assertEqual(self.geography_rows(), original)

  def test_geography_refresh_rejects_unknown_or_newer_current_source_without_replacing_it(self):
    dataset = self.geography_dataset()
    with self.psycopg.connect(DATABASE_URL, autocommit=True) as writer:
      replace_dataset(writer, dataset)
      for version in ('unreviewed-source', 'dbip-country-lite/9999-12/' + 'a'*64):
        writer.execute('update public.us_beta_ip_ranges set source_version=%s', (version,))
        original = self.geography_rows()
        with self.assertRaises(ValueError):
          replace_dataset(writer, dataset)
        self.assertEqual(self.geography_rows(), original)


  def test_geography_refresh_rejects_identical_bytes_relabeled_as_a_new_month(self):
    dataset = self.geography_dataset()
    release_start = datetime.strptime(dataset.release, "%Y-%m").replace(tzinfo=timezone.utc)
    previous_release = (release_start - timedelta(days=1)).strftime("%Y-%m")
    with self.psycopg.connect(DATABASE_URL, autocommit=True) as writer:
      replace_dataset(writer, dataset)
      writer.execute('update public.us_beta_ip_ranges set source_version=%s',
                     (f"dbip-country-lite/{previous_release}/{dataset.sha256}",))
      original = self.geography_rows()
      with self.assertRaises(ValueError):
        replace_dataset(writer, dataset)
    self.assertEqual(self.geography_rows(), original)


  def test_geography_refresh_coverage_limit_is_exact_for_large_ipv6_counts(self):
    start = ipaddress.ip_address('2001:db8::')
    unit = 2**90
    def networks(addresses):
      end = ipaddress.ip_address(int(start) + addresses - 1)
      return ('192.0.2.0/25',) + tuple(map(str, ipaddress.summarize_address_range(start, end)))
    first = self.geography_dataset(networks=networks(5*unit))
    boundary = self.geography_dataset(networks=networks(6*unit))
    beyond = self.geography_dataset(networks=networks(6*unit+1))
    with self.psycopg.connect(DATABASE_URL, autocommit=True) as writer:
      replace_dataset(writer, first)
      original = self.geography_rows()
      with self.assertRaisesRegex(RuntimeError, 'fixture rollback'):
        with writer.transaction():
          replace_dataset(writer, boundary)  # Exactly +20 percent is accepted.
          raise RuntimeError('fixture rollback')
      self.assertEqual(self.geography_rows(), original)
      with self.assertRaisesRegex(ValueError, 'coverage'):
        replace_dataset(writer, beyond)  # One IPv6 address more must reject.
    self.assertEqual(self.geography_rows(), original)
