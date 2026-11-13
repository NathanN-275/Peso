from __future__ import annotations

import os
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4


DATABASE_URL = os.getenv("VIDEO_REVOCATION_TEST_DATABASE_URL", "")


@unittest.skipUnless(DATABASE_URL, "Dedicated video-revocation Postgres database is not configured.")
class VideoRevocationPostgresTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    parsed = urlparse(DATABASE_URL)
    if parsed.hostname not in {"localhost", "127.0.0.1"} or parsed.path != "/peso_revocation_test":
      raise RuntimeError("Revocation tests require the dedicated localhost peso_revocation_test database.")
    import psycopg
    from psycopg.rows import dict_row
    cls.psycopg = psycopg
    cls.dict_row = staticmethod(dict_row)
    root = Path(__file__).resolve().parents[2]
    migrations = root / "supabase/migrations"
    selected = [
      "20260713233319_durable_analysis_jobs.sql",
      "20260805055143_saved_lift_export_jobs.sql",
      "202608170001_analysis_job_observability.sql",
      "202609030001_upload_reservations.sql",
      "202609210001_unsaved_video_retention.sql",
      "202609210002_retention_deletion_outbox.sql",
    ]
    new_migrations = list(migrations.glob("*_atomic_video_media_revocation.sql"))
    if len(new_migrations) != 1:
      raise RuntimeError("Exactly one CLI-generated atomic revocation migration is required.")
    with cls.connect(autocommit=True) as connection:
      version = int(connection.execute("show server_version_num").fetchone()["server_version_num"])
      if not 170000 <= version < 180000:
        raise RuntimeError("This fixture requires the pinned PostgreSQL17 test image.")
      connection.execute((Path(__file__).parent / "fixtures/security_database.sql").read_text())
      connection.execute((Path(__file__).parent / "fixtures/video_revocation_database.sql").read_text())
      connection.execute((Path(__file__).parent / "fixtures/private_media_grants_database.sql").read_text())
      for name in selected:
        connection.execute((migrations / name).read_text())
      connection.execute("grant select, insert, update, delete on public.analysis_jobs to service_role")
      connection.execute(new_migrations[0].read_text())
      connection.execute((migrations / "20261027173544_complete_video_media_deletion.sql").read_text())
      connection.execute((migrations / "20261027182727_queue_video_revocation_fence.sql").read_text())
      connection.execute((migrations / "20261027194638_archive_publication_fence.sql").read_text())
      connection.execute((migrations / "20261027194652_analysis_publication_fence.sql").read_text())
      connection.execute((migrations / "20261028190657_saved_lift_deletion_receipts.sql").read_text())
      for name in ("20261026173152_private_media_provider_session_decision.sql", "20261026182051_private_media_grants.sql",
                   "20261026185845_private_media_logout_receipts.sql", "20261029173814_private_media_owner_deletion_fence.sql",
                   "20261029175000_owner_upload_publication_fence.sql", "20261029180203_owner_analysis_admission.sql", "20261029181358_owner_archive_publication_fence.sql", "20261029211904_source_write_attempts.sql", "20261029214355_generated_media_write_attempts.sql", "20261029221218_analyzed_export_write_attempts.sql", "20261029225507_archive_write_attempts.sql"):
        connection.execute((migrations / name).read_text())

  @classmethod
  def connect(cls, **kwargs):
    return cls.psycopg.connect(DATABASE_URL, row_factory=cls.dict_row, connect_timeout=3, **kwargs)

  def setUp(self):
    self.user = uuid4()
    self.other = uuid4()
    with self.connect(autocommit=True) as connection:
      connection.execute("truncate public.private_media_generated_writes, public.private_media_write_attempts, public.private_media_owners, public.saved_lift_deletion_receipts, public.saved_lift_export_jobs, public.video_deletion_outbox, public.analysis_jobs, public.videos, public.upload_reservations, auth.users cascade")
      connection.execute("insert into auth.users(id) values (%s), (%s)", (self.user, self.other))
      connection.execute("insert into public.private_media_owners(user_id) values (%s), (%s)", (self.user, self.other))

  def sql(self, sql, values=()):
    with self.connect(autocommit=True) as connection:
      cursor = connection.execute(sql, values)
      return cursor.fetchall() if cursor.description else []

  def rpc(self, ids, *, owner=None, delete=False, role="service_role"):
    self.assertIn(role, {"service_role", "anon", "authenticated", "public_probe"})
    with self.connect() as connection:
      connection.execute("set local statement_timeout = '3s'")
      connection.execute("set local role " + role)
      return connection.execute("select * from public.revoke_video_media(%s,%s,%s)", (owner or self.user, ids, delete)).fetchall()

  def video(self, owner=None, **overrides):
    owner = owner or self.user
    video_id = uuid4()
    fields = {"id": video_id, "user_id": owner, "status": "completed", "save_state": "saved", "is_saved": True,
              "storage_path": f"{owner}/source/{video_id}.mp4", "original_storage_path": f"{owner}/source/{video_id}.mp4",
              "playback_path": f"{owner}/playback/{video_id}.mp4", "thumbnail_path": f"{owner}/thumbnails/{video_id}.jpg"}
    fields.update(overrides)
    columns = list(fields)
    # Seed historical paths only in this disposable fixture; runtime publication
    # must pass the new observed-generation boundary, including privileged writes.
    with self.connect() as connection:
      connection.execute('alter table public.videos disable trigger fence_generated_media_publication')
      connection.execute("insert into public.videos (" + ",".join(columns) + ") values (" + ",".join(["%s"] * len(columns)) + ")", tuple(fields.values()))
      connection.execute('alter table public.videos enable trigger fence_generated_media_publication')
    return video_id

  def legacy_video_fields(self, video_id, fields):
    # Fault injection represents corrupt/late historical metadata, never a
    # supported writer. Keep every other production trigger active.
    with self.connect() as connection:
      connection.execute('alter table public.videos disable trigger fence_generated_media_publication')
      connection.execute('update public.videos set '+','.join(name+'=%s' for name in fields)+' where id=%s',
                         (*fields.values(),video_id))
      connection.execute('alter table public.videos enable trigger fence_generated_media_publication')

  def job(self, video_id, status="processing", *, legacy=False):
    job_id = uuid4()
    lease = "synthetic-worker" if status == "processing" else None
    expiry = datetime.now(timezone.utc) + timedelta(minutes=1) if lease else None
    with self.connect() as connection:
      # Deliberately seed an obsolete writer only in this disposable fixture.
      if legacy:connection.execute('alter table public.analysis_jobs disable trigger fence_owner_analysis_job')
      connection.execute("insert into public.analysis_jobs(id,video_id,status,attempt_count,lease_owner,lease_expires_at) values (%s,%s,%s,1,%s,%s)", (job_id, video_id, status, lease, expiry))
      if legacy:connection.execute('alter table public.analysis_jobs enable trigger fence_owner_analysis_job')
    return job_id

  def archive(self, ids, *, owner=None, status="completed", path=None, legacy=False):
    owner = owner or self.user
    job_id = uuid4()
    if path is None and status == "completed":
      path = f"{owner}/{job_id}.zip"
    now = datetime.now(timezone.utc)
    with self.connect() as connection:
      # Construct deliberately malformed historical rows only in this isolated
      # synthetic fixture; runtime writes always execute the publication fence.
      if legacy or status == "completed":
        # Historical completed fixtures predate tracked ZIP writes.
        connection.execute("alter table public.saved_lift_export_jobs disable trigger fence_saved_lift_export_publication")
      connection.execute("insert into public.analysis_results(video_id,result_json) select id,'{}'::jsonb from public.videos v where id=any(%s) and not exists(select 1 from public.analysis_results r where r.video_id=v.id)", (ids,))
      connection.execute("insert into public.saved_lift_export_jobs(id,user_id,video_ids,status,archive_path,completed_at,expires_at) values (%s,%s,%s,%s,%s,%s,%s)",
                         (job_id, owner, ids, status, path, now if status == "completed" else None, now + timedelta(hours=1) if status == "completed" else None))
      if legacy or status == "completed":
        connection.execute("alter table public.saved_lift_export_jobs enable trigger fence_saved_lift_export_publication")
    return job_id

  def assert_active(self, ids):
    self.assertEqual(len(self.sql("select id from public.videos where id = any(%s) and discarded_at is null and is_saved", (ids,))), len(ids))
    self.assertEqual(self.sql("select video_id from public.video_deletion_outbox"), [])

  def test_service_only_execution_and_fixed_invoker_scope(self):
    video = self.video()
    for role in ("anon", "authenticated", "public_probe"):
      with self.subTest(role=role), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.rpc([video], role=role)
    proc = self.sql("select prosecdef,proconfig from pg_proc where oid = 'public.revoke_video_media(uuid,uuid[],boolean)'::regprocedure")[0]
    self.assertFalse(proc["prosecdef"])
    self.assertEqual(proc["proconfig"], ['search_path=""'])
    self.assert_active([video])
    self.assertEqual(len(self.rpc([video])), 1)

  def test_rejects_invalid_bounded_selections_without_mutation(self):
    video = self.video()
    for ids in (None, [], [None], [video, video], [uuid4() for _ in range(51)], [[video]]):
      with self.subTest(ids=ids), self.assertRaises(self.psycopg.errors.InvalidParameterValue):
        self.rpc(ids)
      self.assert_active([video])
    with self.assertRaises(self.psycopg.errors.InvalidParameterValue):
      self.rpc([video], delete=None)
    with self.connect() as connection, self.assertRaises(self.psycopg.errors.InvalidParameterValue):
      connection.execute("set local role service_role")
      connection.execute("select * from public.revoke_video_media(null,%s,false)", ([video],))

  def test_missing_or_foreign_member_rolls_back_complete_selection(self):
    video = self.video()
    foreign = self.video(self.other)
    job = self.job(video)
    archive = self.archive([video])
    for unavailable in (uuid4(), foreign):
      with self.subTest(unavailable=unavailable), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.rpc([video, unavailable])
      self.assert_active([video, foreign])
      self.assertEqual(self.sql("select status from public.analysis_jobs where id=%s", (job,))[0]["status"], "processing")
      self.assertEqual(self.sql("select status from public.saved_lift_export_jobs where id=%s", (archive,))[0]["status"], "completed")

  def test_accepts_complete_fifty_video_boundary(self):
    videos = [self.video() for _ in range(50)]
    rows = self.rpc(list(reversed(videos)), delete=True)
    self.assertEqual([row["video_id"] for row in rows], sorted(videos))
    self.assertTrue(all(row["delete_metadata"] for row in rows))
    self.assertEqual(len(self.sql("select id from public.videos where discarded_at is not null")), 50)

  def test_all_four_video_paths_are_validated_before_writes(self):
    safe = self.video()
    unsafe = self.video()
    for column in ("storage_path", "original_storage_path", "playback_path", "thumbnail_path"):
      for bad in (f"{self.other}/wrong.mp4", f"{self.user}/../wrong.mp4", f"{self.user}/./wrong.mp4", f"{self.user}/x//wrong.mp4", f"{self.user}/bad\\name", f"{self.user}/bad\nname", f" {self.user}/bad", f"{self.user}/bad ", f"{self.user}/bad\u00a0", f"{self.user}/bad\u2007", f"{self.user}/bad\u202f", f"{self.user}/bad\u3000", f"{self.user}/", f"{self.user}/https://bad", ""):
        with self.subTest(column=column, bad=bad):
          self.legacy_video_fields(unsafe,{column:bad})
          with self.assertRaises(self.psycopg.errors.InvalidParameterValue):
            self.rpc([safe, unsafe])
          self.assert_active([safe, unsafe])
          self.legacy_video_fields(unsafe,{column:f"{self.user}/safe.mp4"})

  def test_null_optional_paths_and_pruned_rows_are_supported(self):
    video = self.video(storage_path=None, original_storage_path=None, playback_path=None, thumbnail_path=None)
    row = self.rpc([video])[0]
    self.assertEqual(row["storage_paths"], [])
    self.assertEqual(row["export_prefixes"], [f"{self.user}/exports/{video}-"])

  def test_existing_outbox_owner_and_snapshots_are_validated(self):
    video = self.video()
    self.sql("insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values (%s,%s,%s)", (video, self.other, [f"{self.other}/old.mp4"]))
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
      self.rpc([video])
    self.sql("update public.video_deletion_outbox set user_id=%s where video_id=%s", (self.user, video))
    with self.assertRaises(self.psycopg.errors.InvalidParameterValue):
      self.rpc([video])
    self.sql("update public.video_deletion_outbox set storage_paths=%s where video_id=%s", ([None], video))
    with self.assertRaises(self.psycopg.errors.InvalidParameterValue):
      self.rpc([video])
    self.sql("update public.video_deletion_outbox set storage_paths=%s,archive_paths=%s where video_id=%s", ([f"{self.user}/old.mp4"], [f"{self.other}/wrong.zip"], video))
    with self.assertRaises(self.psycopg.errors.InvalidParameterValue):
      self.rpc([video])
    self.sql("update public.video_deletion_outbox set archive_paths='{}',export_prefixes=%s where video_id=%s", ([f"{self.user}/exports/"], video))
    with self.assertRaises(self.psycopg.errors.InvalidParameterValue):
      self.rpc([video])
    self.assertIsNone(self.sql("select discarded_at from public.videos where id=%s", (video,))[0]["discarded_at"])

  def test_unsafe_archive_path_aborts_all_video_and_job_changes(self):
    video = self.video()
    job = self.job(video)
    archive = self.archive([video], path=f"{self.user}/../unsafe.zip", legacy=True)
    with self.assertRaises(self.psycopg.errors.InvalidParameterValue):
      self.rpc([video])
    self.assert_active([video])
    self.assertEqual(self.sql("select status from public.analysis_jobs where id=%s", (job,))[0]["status"], "processing")
    self.assertEqual(self.sql("select status from public.saved_lift_export_jobs where id=%s", (archive,))[0]["status"], "completed")

  def test_cancellation_tombstones_and_snapshots_commit_atomically(self):
    videos = [self.video() for _ in range(3)]
    jobs = [self.job(video, status) for video, status in zip(videos, ("queued", "processing", "retry_wait"))]
    completed = self.job(videos[0], "completed")
    rows = self.rpc(list(reversed(videos)), delete=True)
    self.assertEqual([row["video_id"] for row in rows], sorted(videos))
    for row in rows:
      video = self.sql("select * from public.videos where id=%s", (row["video_id"],))[0]
      self.assertTrue(video["discarded_at"])
      self.assertFalse(video["is_saved"])
      self.assertEqual(video["save_state"], "pending")
      self.assertIsNone(video["expires_at"])
      self.assertEqual(row["storage_paths"], sorted({video[field] for field in ("storage_path", "original_storage_path", "playback_path", "thumbnail_path")}))
      self.assertEqual(row["export_prefixes"], [f"{self.user}/exports/{video['id']}-"])
      self.assertTrue(row["delete_metadata"])
    for job in self.sql("select * from public.analysis_jobs where id=any(%s)", (jobs,)):
      self.assertEqual(job["status"], "cancelled")
      self.assertEqual(job["failure_class"], "video_revoked")
      self.assertIsNone(job["lease_owner"])
      self.assertIsNone(job["lease_expires_at"])
      self.assertTrue(job["completed_at"])
    self.assertEqual(self.sql("select status from public.analysis_jobs where id=%s", (completed,))[0]["status"], "completed")

  def test_archive_jobs_expire_and_snapshot_actual_and_late_upload_paths(self):
    first, second = self.video(), self.video()
    unrelated = self.archive([uuid4()], legacy=True)
    foreign = self.archive([first], owner=self.other, legacy=True)
    archives = [self.archive([first, second], status=status) for status in ("queued", "processing", "completed", "failed", "expired")]
    legacy = self.archive([first], path=f"{self.user}/legacy.zip", legacy=True)
    rows = {row["video_id"]: row for row in self.rpc([first, second])}
    expected = {f"{self.user}/{job}.zip" for job in archives}
    self.assertEqual(set(rows[second]["archive_paths"]), expected)
    self.assertEqual(set(rows[first]["archive_paths"]), expected | {f"{self.user}/{legacy}.zip", f"{self.user}/legacy.zip"})
    for job in self.sql("select * from public.saved_lift_export_jobs where id=any(%s)", (archives + [legacy],)):
      self.assertEqual(job["status"], "expired")
      self.assertIsNone(job["archive_path"])
      self.assertEqual(job["failure_code"], "video_revoked")
      self.assertLessEqual(job["expires_at"], datetime.now(timezone.utc))
    for job in (unrelated, foreign):
      self.assertEqual(self.sql("select status from public.saved_lift_export_jobs where id=%s", (job,))[0]["status"], "completed")

  def test_retry_merges_paths_preserves_timestamp_and_upgrades_delete_flag(self):
    video = self.video()
    first = self.rpc([video])[0]
    discarded = self.sql("select discarded_at from public.videos where id=%s", (video,))[0]["discarded_at"]
    self.legacy_video_fields(video,{'playback_path':f"{self.user}/late.mp4"})
    with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
      self.archive([video])
    upgraded = self.rpc([video], delete=True)[0]
    self.assertEqual(set(upgraded["storage_paths"]), set(first["storage_paths"]) | {f"{self.user}/late.mp4"})
    self.assertEqual(upgraded["archive_paths"], first["archive_paths"])
    repeated = self.rpc([video], delete=False)[0]
    self.assertTrue(repeated["delete_metadata"])
    self.assertEqual(repeated["created_at"], first["created_at"])
    self.assertEqual(repeated["storage_paths"], upgraded["storage_paths"])
    self.assertEqual(repeated["archive_paths"], upgraded["archive_paths"])
    self.assertEqual(self.sql("select discarded_at from public.videos where id=%s", (video,))[0]["discarded_at"], discarded)

  def test_owned_outbox_allows_retry_after_video_metadata_disappears(self):
    video = self.video()
    first = self.rpc([video])[0]
    self.sql("delete from public.videos where id=%s", (video,))
    retry = self.rpc([video], delete=True)[0]
    self.assertEqual(retry["storage_paths"], first["storage_paths"])
    self.assertTrue(retry["delete_metadata"])
    self.assertEqual(retry["created_at"], first["created_at"])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
      self.rpc([video], owner=self.other)

  def test_later_statement_failure_rolls_back_outbox_and_job_mutations(self):
    video = self.video()
    job = self.job(video)
    archive = self.archive([video])
    self.sql("create function public.fixture_reject_tombstone() returns trigger language plpgsql as $$ begin if new.discarded_at is not null then raise exception 'synthetic tombstone failure'; end if; return new; end $$")
    self.sql("create trigger fixture_reject_tombstone before update on public.videos for each row execute function public.fixture_reject_tombstone()")
    try:
      with self.assertRaises(self.psycopg.errors.RaiseException):
        self.rpc([video])
      self.assert_active([video])
      self.assertEqual(self.sql("select status from public.analysis_jobs where id=%s", (job,))[0]["status"], "processing")
      self.assertEqual(self.sql("select status from public.saved_lift_export_jobs where id=%s", (archive,))[0]["status"], "completed")
    finally:
      self.sql("drop trigger fixture_reject_tombstone on public.videos")
      self.sql("drop function public.fixture_reject_tombstone()")

  def test_existing_retention_function_keeps_legacy_default_shape(self):
    video = self.video(save_state="pending", is_saved=False, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    with self.connect() as connection:
      connection.execute("set local role service_role")
      row = connection.execute("select * from public.claim_expired_video_deletion(%s)", (video,)).fetchone()
    self.assertEqual(row["archive_paths"], [])
    self.assertEqual(row["export_prefixes"], [])
    self.assertFalse(row["delete_metadata"])
    self.assertEqual(self.sql("select id from public.videos where id=%s", (video,)), [])

  def test_temp_search_path_cannot_shadow_qualified_tables(self):
    video = self.video()
    with self.connect() as connection:
      connection.execute("create temporary table videos(id uuid, user_id uuid)")
      connection.execute("insert into pg_temp.videos values (%s,%s)", (video, self.other))
      connection.execute("set local search_path=pg_temp,public")
      connection.execute("set local role service_role")
      row = connection.execute("select * from public.revoke_video_media(%s,%s,false)", (self.user, [video])).fetchone()
    self.assertEqual(row["user_id"], self.user)

  def wait_blocked(self, pid, blocker):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
      blocked = self.sql("select pg_blocking_pids(%s) as pids", (pid,))[0]["pids"]
      if blocker in blocked:
        return
      time.sleep(0.01)
    self.fail("Expected the controlled concurrent write to block on the held video lock.")

  def test_save_first_then_revoke_serializes_and_revokes_saved_row(self):
    video = self.video()
    ready = threading.Event()
    waiter = {}
    def revoke():
      with self.connect() as connection:
        connection.execute("set local statement_timeout='5s'")
        connection.execute("set local role service_role")
        waiter["pid"] = connection.info.backend_pid
        ready.set()
        return connection.execute("select * from public.revoke_video_media(%s,%s,false)", (self.user, [video])).fetchall()
    with ThreadPoolExecutor(max_workers=1) as pool, self.connect() as saver:
      saver.execute("set local role service_role")
      saver.execute("update public.videos set save_state='saved',is_saved=true where id=%s and discarded_at is null", (video,))
      future = pool.submit(revoke)
      try:
        self.assertTrue(ready.wait(3))
        self.wait_blocked(waiter["pid"], saver.info.backend_pid)
      finally:
        saver.commit()
      self.assertEqual(len(future.result(timeout=5)), 1)
    self.assertTrue(self.sql("select discarded_at from public.videos where id=%s", (video,))[0]["discarded_at"])

  def test_revoke_first_prevents_waiting_conditional_save_from_resurrection(self):
    video = self.video()
    ready = threading.Event()
    waiter = {}
    def save():
      with self.connect() as connection:
        connection.execute("set local statement_timeout='5s'")
        connection.execute("set local role service_role")
        waiter["pid"] = connection.info.backend_pid
        ready.set()
        return connection.execute("update public.videos set save_state='saved',is_saved=true where id=%s and discarded_at is null returning id", (video,)).fetchall()
    with ThreadPoolExecutor(max_workers=1) as pool, self.connect() as revoker:
      revoker.execute("set local role service_role")
      revoker.execute("select * from public.revoke_video_media(%s,%s,false)", (self.user, [video])).fetchall()
      future = pool.submit(save)
      try:
        self.assertTrue(ready.wait(3))
        self.wait_blocked(waiter["pid"], revoker.info.backend_pid)
      finally:
        revoker.commit()
      self.assertEqual(future.result(timeout=5), [])
    row = self.sql("select discarded_at,is_saved from public.videos where id=%s", (video,))[0]
    self.assertTrue(row["discarded_at"])
    self.assertFalse(row["is_saved"])

  def test_busy_analysis_job_fails_nowait_then_existing_completion_can_finish(self):
    video = self.video()
    job = self.job(video)
    with self.connect() as worker:
      worker.execute("set local role service_role")
      worker.execute("select id from public.analysis_jobs where id=%s for update", (job,))
      start = time.monotonic()
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):
        self.rpc([video])
      self.assertLess(time.monotonic() - start, 2)
      result = worker.execute("select public.complete_video_analysis_job(%s,'synthetic-worker',1) as completed", (job,)).fetchone()
      self.assertTrue(result["completed"])
    self.assert_active([video])
    self.assertEqual(self.sql("select status from public.analysis_jobs where id=%s", (job,))[0]["status"], "completed")

  def test_busy_archive_job_fails_nowait_without_partial_mutation(self):
    video = self.video()
    archive = self.archive([video])
    with self.connect() as worker:
      worker.execute("select id from public.saved_lift_export_jobs where id=%s for update", (archive,))
      with self.assertRaises(self.psycopg.errors.LockNotAvailable):
        self.rpc([video])
    self.assert_active([video])

  def test_uncommitted_archive_insert_serializes_then_revoke_captures_the_job(self):
    video = self.video()
    self.sql("insert into public.analysis_results(video_id,result_json) values (%s,'{}')", (video,))
    archive = uuid4()
    ready = threading.Event(); waiter = {}
    def revoke():
      with self.connect() as connection:
        connection.execute("set local statement_timeout='5s'")
        connection.execute("set local role service_role")
        waiter["pid"] = connection.info.backend_pid; ready.set()
        return connection.execute("select * from public.revoke_video_media(%s,%s,false)", (self.user,[video])).fetchall()
    with ThreadPoolExecutor(max_workers=1) as pool, self.connect() as creator:
      creator.execute("set local role service_role")
      creator.execute("insert into public.saved_lift_export_jobs(id,user_id,video_ids) values (%s,%s,%s)", (archive, self.user, [video]))
      future = pool.submit(revoke)
      try:
        self.assertTrue(ready.wait(3))
        self.wait_blocked(waiter["pid"], creator.info.backend_pid)
      finally:
        creator.commit()
      row = future.result(timeout=5)[0]
    self.assertIn(f"{self.user}/{archive}.zip", row["archive_paths"])
    self.assertEqual(self.sql("select status from public.saved_lift_export_jobs where id=%s", (archive,))[0]["status"], "expired")

  def test_archive_insertion_waits_for_the_revocation_transaction(self):
    video = self.video()
    archive = uuid4()
    ready = threading.Event()
    waiter = {}
    def insert():
      with self.connect() as connection:
        connection.execute("set local statement_timeout='5s'")
        connection.execute("set local role service_role")
        waiter["pid"] = connection.info.backend_pid
        ready.set()
        return connection.execute("insert into public.saved_lift_export_jobs(id,user_id,video_ids) values (%s,%s,%s) returning id", (archive, self.user, [video])).fetchone()
    with ThreadPoolExecutor(max_workers=1) as pool, self.connect() as revoker:
      revoker.execute("set local role service_role")
      revoker.execute("select * from public.revoke_video_media(%s,%s,false)", (self.user, [video])).fetchall()
      future = pool.submit(insert)
      try:
        self.assertTrue(ready.wait(3))
        self.wait_blocked(waiter["pid"], revoker.info.backend_pid)
      finally:
        revoker.commit()
      with self.assertRaises(self.psycopg.errors.ObjectNotInPrerequisiteState):
        future.result(timeout=5)
    self.assertEqual(self.sql("select id from public.saved_lift_export_jobs where id=%s", (archive,)), [])
    self.assertTrue(self.sql("select discarded_at from public.videos where id=%s", (video,))[0]["discarded_at"])

  def test_overlapping_reverse_selections_serialize_without_deadlock(self):
    videos = [self.video(), self.video()]
    gate = threading.Barrier(2)
    def attempt(ids):
      gate.wait(timeout=3)
      return self.rpc(ids)
    with ThreadPoolExecutor(max_workers=2) as pool:
      futures = [pool.submit(attempt, videos), pool.submit(attempt, list(reversed(videos)))]
      results = [future.result(timeout=5) for future in futures]
    self.assertTrue(all(len(rows) == 2 for rows in results))
    self.assertEqual(len(self.sql("select video_id from public.video_deletion_outbox")), 2)


  def finalize(self, row, *, owner=None, role="service_role"):
    with self.connect() as connection:
      connection.execute("set local statement_timeout='3s'")
      connection.execute("set local role " + role)
      return connection.execute(
        "select public.complete_video_media_deletion(%s,%s,%s,%s,%s,%s) as completed",
        (row["video_id"], owner or row["user_id"], row["storage_paths"], row["archive_paths"],
         row["export_prefixes"], row["delete_metadata"])).fetchone()["completed"]

  def test_finalizer_service_only_and_fixed_invoker_scope(self):
    row = self.rpc([self.video()])[0]
    for role in ("anon", "authenticated", "public_probe"):
      with self.subTest(role=role), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.finalize(row, role=role)
    proc = self.sql("select prosecdef,proconfig from pg_proc where oid='public.complete_video_media_deletion(uuid,uuid,text[],text[],text[],boolean)'::regprocedure")[0]
    self.assertFalse(proc["prosecdef"])
    self.assertEqual(proc["proconfig"], ['search_path=""', 'lock_timeout=2s'])
    self.assertTrue(self.finalize(row))

  def test_finalizer_discard_preserves_tombstone_and_analysis(self):
    video = self.video()
    self.sql("insert into public.analysis_results(video_id,result_json) values (%s,'{}'::jsonb)", (video,))
    row = self.rpc([video])[0]
    self.assertTrue(self.finalize(row))
    self.assertTrue(self.sql("select discarded_at from public.videos where id=%s", (video,))[0]["discarded_at"])
    self.assertEqual(len(self.sql("select id from public.analysis_results where video_id=%s", (video,))), 1)
    self.assertEqual(self.sql("select video_id from public.video_deletion_outbox"), [])
    self.assertFalse(self.finalize(row))

  def test_discard_retry_after_completed_cleanup_recreates_task_without_resurrecting_metadata(self):
    video = self.video()
    self.sql("insert into public.analysis_results(video_id,result_json) values (%s,'{}'::jsonb)", (video,))
    job = self.job(video)
    archive = self.archive([video])
    first = self.rpc([video], delete=False)[0]
    tombstone = self.sql('select discarded_at from public.videos where id=%s', (video,))[0]['discarded_at']
    self.assertTrue(self.finalize(first))
    # A lost successful HTTP response retries the same video after task removal.
    retry = self.rpc([video], delete=False)[0]
    self.assertFalse(retry['delete_metadata'])
    self.assertEqual(retry['storage_paths'], first['storage_paths'])
    self.assertEqual(retry['archive_paths'], first['archive_paths'])
    self.assertEqual(self.sql('select discarded_at from public.videos where id=%s', (video,))[0]['discarded_at'], tombstone)
    self.assertEqual(self.sql('select status from public.analysis_jobs where id=%s', (job,))[0]['status'], 'cancelled')
    self.assertEqual(self.sql('select status from public.saved_lift_export_jobs where id=%s', (archive,))[0]['status'], 'expired')
    self.assertTrue(self.finalize(retry))
    self.assertEqual(len(self.sql('select id from public.analysis_results where video_id=%s', (video,))), 1)
    self.assertEqual(self.sql('select video_id from public.video_deletion_outbox'), [])

  def test_finalizer_permanent_delete_removes_analysis_video_and_task_atomically(self):
    video = self.video()
    self.sql("insert into public.analysis_results(video_id,result_json) values (%s,'{}'::jsonb)", (video,))
    row = self.rpc([video], delete=True)[0]
    self.assertTrue(self.finalize(row))
    for table in ('videos', 'analysis_results', 'video_deletion_outbox'):
      self.assertEqual(self.sql("select * from public." + table), [])

  def test_finalizer_supports_retention_task_after_metadata_disappeared(self):
    video = self.video()
    self.sql("insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values (%s,%s,%s)",
             (video, self.user, [f"{self.user}/retained.mp4"]))
    self.sql("delete from public.videos where id=%s", (video,))
    row = self.sql("select * from public.video_deletion_outbox where video_id=%s", (video,))[0]
    self.assertEqual(row['archive_paths'], [])
    self.assertEqual(row['export_prefixes'], [])
    self.assertFalse(row['delete_metadata'])
    self.assertTrue(self.finalize(row))

  def test_finalizer_rejects_every_stale_snapshot_field_without_mutation(self):
    row = self.rpc([self.video()])[0]
    changes = {'storage_paths': [f'{self.user}/changed.mp4'],
               'archive_paths': [f'{self.user}/changed.zip'],
               'export_prefixes': [f'{self.user}/exports/changed-'], 'delete_metadata': True}
    for key, value in changes.items():
      with self.subTest(key=key):
        stale = dict(row); stale[key] = value
        self.assertFalse(self.finalize(stale))
        self.assertEqual(len(self.sql('select * from public.video_deletion_outbox')), 1)
        self.assertEqual(len(self.sql('select * from public.videos')), 1)
    self.assertTrue(self.finalize(row))

  def test_finalizer_rejects_foreign_owner_and_non_tombstoned_rows(self):
    video = self.video()
    row = self.rpc([video], delete=True)[0]
    self.assertFalse(self.finalize(row, owner=self.other))
    self.sql('update public.videos set discarded_at=null where id=%s', (video,))
    self.assertFalse(self.finalize(row))
    self.sql('update public.videos set discarded_at=now(),is_saved=true where id=%s', (video,))
    self.assertFalse(self.finalize(row))
    self.sql("update public.videos set is_saved=false,save_state='saved' where id=%s", (video,))
    self.assertFalse(self.finalize(row))
    self.assertEqual(len(self.sql('select * from public.video_deletion_outbox')), 1)
    self.assertEqual(len(self.sql('select * from public.videos')), 1)

  def test_finalizer_rejects_active_job_that_appeared_after_revocation(self):
    video = self.video()
    row = self.rpc([video], delete=True)[0]
    # Fault-inject a pre-cutover writer after revocation to test finalizer defense.
    job = self.job(video, 'queued', legacy=True)
    self.assertFalse(self.finalize(row))
    self.assertEqual(len(self.sql('select * from public.video_deletion_outbox')), 1)
    self.sql("select public.cancel_video_analysis_jobs(%s)", (video,))
    self.assertTrue(self.finalize(row))

  def test_finalizer_metadata_failure_rolls_back_acknowledgement(self):
    video = self.video()
    row = self.rpc([video], delete=True)[0]
    self.sql("create function public.fixture_reject_delete() returns trigger language plpgsql as $$ begin raise exception 'synthetic delete failure'; end $$")
    self.sql("create trigger fixture_reject_delete before delete on public.videos for each row execute function public.fixture_reject_delete()")
    try:
      with self.assertRaises(self.psycopg.errors.RaiseException):
        self.finalize(row)
      self.assertEqual(len(self.sql('select * from public.video_deletion_outbox')), 1)
      self.assertEqual(len(self.sql('select * from public.videos')), 1)
    finally:
      self.sql('drop trigger fixture_reject_delete on public.videos')
      self.sql('drop function public.fixture_reject_delete()')
    self.assertTrue(self.finalize(row))

  def test_finalizer_missing_snapshot_fields_raise_without_acknowledgement(self):
    row = self.rpc([self.video()], delete=True)[0]
    for key in ('video_id', 'user_id', 'storage_paths', 'archive_paths', 'export_prefixes', 'delete_metadata'):
      with self.subTest(key=key):
        incomplete = dict(row); incomplete[key] = None
        with self.assertRaises(self.psycopg.errors.InvalidParameterValue):
          self.finalize(incomplete)
        self.assertEqual(len(self.sql('select * from public.video_deletion_outbox')), 1)
        self.assertEqual(len(self.sql('select * from public.videos')), 1)

  def test_finalizer_busy_child_rows_fail_fast_and_preserve_task(self):
    for table in ('analysis_jobs', 'analysis_results', 'upload_reservations'):
      with self.subTest(table=table):
        video = self.video()
        if table == 'analysis_jobs':
          child = self.job(video, 'cancelled')
        elif table == 'analysis_results':
          child = uuid4()
          self.sql("insert into public.analysis_results(id,video_id,result_json) values (%s,%s,'{}'::jsonb)", (child,video))
        else:
          child = uuid4()
          self.sql("insert into public.upload_reservations(id,user_id,blob_path,file_name,content_type,requested_bytes,source_type,exercise_type,view_type,video_id,expires_at) values (%s,%s,%s,'fixture.mp4','video/mp4',1,'camera_roll','squat','side',%s,now()+interval '1 hour')",
                   (child,self.user,f'{self.user}/source/{child}.mp4',video))
        row = self.rpc([video], delete=True)[0]
        with self.connect() as writer:
          writer.execute('select id from public.' + table + ' where id=%s for update', (child,))
          started = time.monotonic()
          with self.assertRaises(self.psycopg.errors.LockNotAvailable):
            self.finalize(row)
          self.assertLess(time.monotonic() - started, 2)
          self.assertEqual(len(self.sql('select * from public.video_deletion_outbox where video_id=%s', (video,))), 1)
          self.assertEqual(len(self.sql('select * from public.videos where id=%s', (video,))), 1)
        self.assertTrue(self.finalize(row))

  def test_finalizer_waits_for_revoker_and_retains_newly_merged_snapshot(self):
    video = self.video()
    row = self.rpc([video])[0]
    self.legacy_video_fields(video,{'thumbnail_path':f'{self.user}/new-thumb.jpg'})
    ready = threading.Event(); waiter = {}
    def complete():
      with self.connect() as connection:
        connection.execute("set local role service_role")
        connection.execute("set local statement_timeout='5s'")
        waiter['pid'] = connection.info.backend_pid; ready.set()
        return connection.execute(
          'select public.complete_video_media_deletion(%s,%s,%s,%s,%s,%s) as completed',
          (video,self.user,row['storage_paths'],row['archive_paths'],row['export_prefixes'],False)).fetchone()['completed']
    with ThreadPoolExecutor(max_workers=1) as pool, self.connect() as revoker:
      revoker.execute('set local role service_role')
      revoker.execute('select * from public.revoke_video_media(%s,%s,false)', (self.user,[video])).fetchall()
      future = pool.submit(complete)
      try:
        self.assertTrue(ready.wait(3))
        self.wait_blocked(waiter['pid'], revoker.info.backend_pid)
      finally:
        revoker.commit()
      self.assertFalse(future.result(timeout=5))
    merged = self.sql('select * from public.video_deletion_outbox where video_id=%s', (video,))[0]
    self.assertIn(f'{self.user}/new-thumb.jpg', merged['storage_paths'])
    self.assertTrue(self.finalize(merged))


  def queueable_video(self, owner=None, **overrides):
    owner = owner or self.user
    fields = {'status': 'uploaded', 'save_state': 'pending', 'is_saved': False,
              'storage_state': 'available', 'expires_at': datetime.now(timezone.utc) + timedelta(hours=1)}
    fields.update(overrides)
    video = self.video(owner, **fields)
    reservation = uuid4()
    self.sql("insert into public.upload_reservations(id,user_id,blob_path,file_name,content_type,requested_bytes,state,source_type,exercise_type,view_type,video_id,expires_at) values (%s,%s,%s,'fixture.mp4','video/mp4',1,'verified','camera_roll','squat','side',%s,now()+interval '1 hour')",
             (reservation,owner,f'{owner}/source/{reservation}.mp4',video))
    self.sql('update public.videos set upload_reservation_id=%s where id=%s', (reservation,video))
    return video

  def enqueue(self, video, allow_completed=False, max_user=3, max_global=20, role='service_role'):
    self.assertIn(role, {'service_role', 'anon', 'authenticated', 'public_probe'})
    with self.connect() as connection:
      connection.execute("set local statement_timeout='5s'")
      connection.execute('set local role ' + role)
      return connection.execute('select * from public.enqueue_video_analysis_job(%s,%s,%s,%s)',
                                (video,allow_completed,max_user,max_global)).fetchall()

  def test_enqueue_is_service_only_fixed_invoker_and_old_overload_is_absent(self):
    video = self.queueable_video()
    for role in ('anon','authenticated','public_probe'):
      with self.subTest(role=role), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.enqueue(video, role=role)
    proc = self.sql("select prosecdef,proconfig from pg_proc where oid='public.enqueue_video_analysis_job(uuid,boolean,integer,integer)'::regprocedure")[0]
    self.assertFalse(proc['prosecdef']); self.assertEqual(proc['proconfig'], ['search_path=""'])
    self.assertIsNone(self.sql("select to_regprocedure('public.enqueue_video_analysis_job(uuid,boolean)') as old")[0]['old'])
    self.assertEqual(len(self.enqueue(video)), 1)

  def test_enqueue_preserves_uploaded_failed_and_force_completed_states_and_consumption(self):
    for state in ('uploaded','failed','completed'):
      video = self.queueable_video(status=state)
      if state == 'completed':
        with self.assertRaisesRegex(self.psycopg.errors.RaiseException, 'Video cannot be queued from this state'):
          self.enqueue(video)
      row = self.enqueue(video, allow_completed=state == 'completed')[0]
      self.assertEqual(row['status'], 'queued'); self.assertEqual(row['video_id'], video)
      self.assertEqual(row['attempt_count'], 0)
      self.assertEqual(self.sql('select status from public.videos where id=%s', (video,))[0]['status'], 'queued')
      reservation = self.sql('select r.state,r.consumed_at from public.upload_reservations r join public.videos v on v.upload_reservation_id=r.id where v.id=%s', (video,))[0]
      self.assertEqual(reservation['state'], 'consumed'); self.assertTrue(reservation['consumed_at'])

  def test_enqueue_preserves_missing_unverified_and_invalid_state_errors(self):
    with self.assertRaisesRegex(self.psycopg.errors.RaiseException, 'Video not found'):
      self.enqueue(uuid4())
    legacy = self.video(status='uploaded')
    with self.assertRaisesRegex(self.psycopg.errors.RaiseException, 'Only verified uploads can be queued'):
      self.enqueue(legacy)
    invalid = self.queueable_video(status='processing')
    with self.assertRaisesRegex(self.psycopg.errors.RaiseException, 'Video cannot be queued from this state'):
      self.enqueue(invalid)
    self.assertEqual(self.sql('select id from public.analysis_jobs'), [])

  def test_enqueue_active_job_idempotence_stays_before_capacity_and_legacy_upload_validation(self):
    for state in ('queued','processing','retry_wait'):
      video = self.video(status='processing', expires_at=None)
      job = self.job(video, state)
      rows = self.enqueue(video, max_user=0, max_global=0)
      self.assertEqual(rows[0]['id'], job); self.assertEqual(rows[0]['status'], state)
      self.assertEqual(len(self.sql('select id from public.analysis_jobs where video_id=%s', (video,))), 1)

  def test_enqueue_rejects_tombstone_after_revocation_and_after_completed_cleanup(self):
    video = self.queueable_video()
    row = self.rpc([video])[0]
    for cleanup in (False, True):
      if cleanup: self.assertTrue(self.finalize(row))
      with self.assertRaisesRegex(self.psycopg.errors.RaiseException, 'Video cannot be queued from this state'):
        self.enqueue(video, allow_completed=True)
    self.assertEqual(self.sql('select id from public.analysis_jobs where video_id=%s', (video,)), [])

  def test_enqueue_never_reuses_old_active_job_for_discarded_pruned_expired_or_outboxed_video(self):
    variants = [
      {'discarded_at': datetime.now(timezone.utc)}, {'storage_state': 'pruned'},
      {'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)},
      {'expires_at': 'infinity'}, {'expires_at': '-infinity'}, {'outbox': True},
    ]
    for variant in variants:
      for state in ('queued','processing','retry_wait'):
        fields = dict(variant); outbox = fields.pop('outbox', False)
        video = self.queueable_video(); job = self.job(video,state)
        if fields:
          self.sql('update public.videos set '+','.join(key+'=%s' for key in fields)+' where id=%s',(*fields.values(),video))
        if outbox:
          self.sql("insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values (%s,%s,'{}')", (video,self.user))
        with self.subTest(variant=variant,state=state), self.assertRaisesRegex(self.psycopg.errors.RaiseException, 'Video cannot be queued from this state'):
          self.enqueue(video, allow_completed=True)
        self.assertEqual(self.sql('select status from public.analysis_jobs where id=%s', (job,))[0]['status'], state)

  def test_enqueue_outbox_guard_does_not_depend_on_tombstone_or_owner_match(self):
    video = self.queueable_video()
    self.sql("insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values (%s,%s,'{}')", (video,self.other))
    with self.assertRaises(self.psycopg.errors.RaiseException): self.enqueue(video)
    self.assertEqual(self.sql('select id from public.analysis_jobs'), [])

  def test_enqueue_allows_no_deadline_but_does_not_ignore_finite_saved_expiry(self):
    video = self.queueable_video(expires_at=None)
    self.assertEqual(len(self.enqueue(video)), 1)
    expired = self.queueable_video(status='completed', save_state='saved', is_saved=True,
                                   expires_at=datetime.now(timezone.utc)-timedelta(seconds=1))
    with self.assertRaises(self.psycopg.errors.RaiseException): self.enqueue(expired, allow_completed=True)

  def test_enqueue_first_revoker_waits_then_cancels_the_committed_job(self):
    video = self.queueable_video(); ready = threading.Event(); waiter = {}
    def revoke():
      with self.connect() as connection:
        connection.execute("set local statement_timeout='5s'"); connection.execute('set local role service_role')
        waiter['pid'] = connection.info.backend_pid; ready.set()
        return connection.execute('select * from public.revoke_video_media(%s,%s,false)', (self.user,[video])).fetchall()
    with ThreadPoolExecutor(max_workers=1) as pool, self.connect() as creator:
      creator.execute('set local role service_role')
      job = creator.execute('select * from public.enqueue_video_analysis_job(%s,false,3,20)', (video,)).fetchone()['id']
      future = pool.submit(revoke)
      try:
        self.assertTrue(ready.wait(3)); self.wait_blocked(waiter['pid'], creator.info.backend_pid)
      finally: creator.commit()
      self.assertEqual(len(future.result(timeout=5)), 1)
    row = self.sql('select status,failure_class from public.analysis_jobs where id=%s', (job,))[0]
    self.assertEqual(row['status'], 'cancelled'); self.assertEqual(row['failure_class'], 'video_revoked')
    with self.assertRaises(self.psycopg.errors.RaiseException): self.enqueue(video)

  def test_revoker_first_enqueue_waits_and_cannot_return_the_old_job(self):
    video = self.queueable_video(); job = self.job(video); ready = threading.Event(); waiter = {}
    def enqueue():
      with self.connect() as connection:
        connection.execute("set local statement_timeout='5s'"); connection.execute('set local role service_role')
        waiter['pid'] = connection.info.backend_pid; ready.set()
        return connection.execute('select * from public.enqueue_video_analysis_job(%s,false,3,20)', (video,)).fetchall()
    with ThreadPoolExecutor(max_workers=1) as pool, self.connect() as revoker:
      revoker.execute('set local role service_role')
      revoker.execute('select * from public.revoke_video_media(%s,%s,false)', (self.user,[video])).fetchall()
      future = pool.submit(enqueue)
      try:
        self.assertTrue(ready.wait(3)); self.wait_blocked(waiter['pid'], revoker.info.backend_pid)
      finally: revoker.commit()
      with self.assertRaises(self.psycopg.errors.RaiseException): future.result(timeout=5)
    self.assertEqual(self.sql('select status from public.analysis_jobs where id=%s', (job,))[0]['status'], 'cancelled')
    self.assertEqual(len(self.sql('select id from public.analysis_jobs where video_id=%s', (video,))), 1)

  def test_enqueue_rechecks_wall_clock_expiry_after_waiting_on_video_lock(self):
    video = self.queueable_video(); ready = threading.Event(); waiter = {}
    def enqueue():
      with self.connect() as connection:
        connection.execute("set local statement_timeout='5s'"); connection.execute('set local role service_role')
        waiter['pid'] = connection.info.backend_pid; ready.set()
        return connection.execute('select * from public.enqueue_video_analysis_job(%s,false,3,20)', (video,)).fetchall()
    with ThreadPoolExecutor(max_workers=1) as pool, self.connect() as holder:
      # The waiting transaction starts before this uncommitted deadline elapses.
      holder.execute("update public.videos set expires_at=clock_timestamp()+interval '400 milliseconds' where id=%s", (video,))
      future = pool.submit(enqueue)
      try:
        self.assertTrue(ready.wait(3)); self.wait_blocked(waiter['pid'], holder.info.backend_pid)
        holder.execute("select pg_sleep(0.5)")
      finally: holder.commit()
      with self.assertRaises(self.psycopg.errors.RaiseException): future.result(timeout=5)
    self.assertEqual(self.sql('select id from public.analysis_jobs'), [])

  def test_enqueue_rechecks_expiry_and_outbox_after_active_job_lock_wait(self):
    for revoke_with_outbox in (False, True):
      video = self.queueable_video(); job = self.job(video); ready = threading.Event(); waiter = {}
      self.sql("update public.videos set expires_at=clock_timestamp()+interval '700 milliseconds' where id=%s", (video,))
      def enqueue():
        with self.connect() as connection:
          connection.execute("set local statement_timeout='5s'"); connection.execute('set local role service_role')
          waiter['pid'] = connection.info.backend_pid; ready.set()
          return connection.execute('select * from public.enqueue_video_analysis_job(%s,false,3,20)', (video,)).fetchall()
      with ThreadPoolExecutor(max_workers=1) as pool, self.connect() as holder:
        holder.execute('select id from public.analysis_jobs where id=%s for update', (job,))
        future = pool.submit(enqueue)
        try:
          self.assertTrue(ready.wait(3)); self.wait_blocked(waiter['pid'], holder.info.backend_pid)
          if revoke_with_outbox:
            holder.execute("insert into public.video_deletion_outbox(video_id,user_id,storage_paths) values (%s,%s,'{}')", (video,self.user))
          else: holder.execute('select pg_sleep(0.8)')
        finally: holder.commit()
        with self.assertRaises(self.psycopg.errors.RaiseException): future.result(timeout=5)

  def test_enqueue_concurrent_user_and_global_quota_counts_stay_serialized(self):
    videos = [self.queueable_video(self.user if i < 6 else self.other) for i in range(12)]
    def attempt(video):
      try: return bool(self.enqueue(video,max_user=3,max_global=4))
      except self.psycopg.errors.RaiseException as error:
        self.assertIn('Analysis queue capacity is full',str(error)); return False
    with ThreadPoolExecutor(max_workers=12) as pool: accepted = list(pool.map(attempt,videos))
    self.assertEqual(sum(accepted),4)
    counts = self.sql("select v.user_id,count(*) as count from public.analysis_jobs j join public.videos v on v.id=j.video_id group by v.user_id")
    self.assertTrue(all(row['count'] <= 3 for row in counts))
    self.assertEqual(sum(row['count'] for row in counts),4)

  def test_enqueue_user_limit_failure_keeps_video_and_reservation_unchanged(self):
    first, second = self.queueable_video(), self.queueable_video()
    self.enqueue(first,max_user=1)
    with self.assertRaisesRegex(self.psycopg.errors.RaiseException,'Analysis queue capacity is full'):
      self.enqueue(second,max_user=1)
    self.assertEqual(self.sql('select status from public.videos where id=%s',(second,))[0]['status'],'uploaded')
    self.assertEqual(self.sql('select r.state from public.upload_reservations r join public.videos v on v.upload_reservation_id=r.id where v.id=%s',(second,))[0]['state'],'verified')

  def test_enqueue_qualified_relations_ignore_temporary_shadow_tables(self):
    video = self.queueable_video()
    with self.connect() as connection:
      connection.execute('create temporary table video_deletion_outbox(video_id uuid)')
      connection.execute('insert into pg_temp.video_deletion_outbox values (%s)',(video,))
      connection.execute('create temporary table videos(id uuid)')
      connection.execute('set local search_path=pg_temp,public'); connection.execute('set local role service_role')
      rows = connection.execute('select * from public.enqueue_video_analysis_job(%s,false,3,20)',(video,)).fetchall()
    self.assertEqual(len(rows),1); self.assertEqual(rows[0]['video_id'],video)


if __name__ == "__main__":
  unittest.main()
