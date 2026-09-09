from __future__ import annotations

import json
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4


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
      connection.execute((root / "supabase/migrations/202609030001_upload_reservations.sql").read_text())

  def setUp(self):
    self.user = uuid4()
    self.other = uuid4()
    with self.psycopg.connect(DATABASE_URL, autocommit=True) as connection:
      connection.execute("truncate public.analysis_jobs, public.videos, public.upload_reservations, auth.users cascade")
      connection.execute("update public.upload_admission_control set enabled = true where id = 1")
      connection.execute("insert into auth.users values (%s), (%s)", (self.user, self.other))

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
