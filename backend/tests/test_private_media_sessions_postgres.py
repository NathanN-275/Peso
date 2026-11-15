from __future__ import annotations

import os
from pathlib import Path
import unittest
from urllib.parse import urlparse


DATABASE_URL = os.getenv("PRIVATE_MEDIA_SESSION_TEST_DATABASE_URL", "")
USER = "33333333-3333-4333-8333-333333333333"
OTHER_USER = "44444444-4444-4444-8444-444444444444"
SESSION = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
OTHER_SESSION = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
NIL = "00000000-0000-0000-0000-000000000000"


@unittest.skipUnless(DATABASE_URL, "Dedicated private-media session test database is not configured.")
class PrivateMediaSessionPostgresTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    parsed = urlparse(DATABASE_URL)
    if parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.path != "/peso_private_media_session_test":
      raise RuntimeError("Only the owned localhost private-media session test database may be used.")
    import psycopg
    cls.psycopg = psycopg
    root = Path(__file__).resolve().parents[2]
    migrations = list((root / "supabase/migrations").glob("*_private_media_provider_session_decision.sql"))
    if len(migrations) != 1:
      raise RuntimeError("Expected exactly one private-media provider-session migration.")
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
      connection.execute((root / "backend/tests/fixtures/private_media_sessions_database.sql").read_text())
      connection.execute(migrations[0].read_text())
      disabled = connection.execute("select enabled from public.private_media_provider_policy").fetchone()[0]
      if disabled is not False:
        raise RuntimeError("Migration must install a disabled provider policy.")

  def setUp(self):
    self.connection = self.psycopg.connect(DATABASE_URL, autocommit=True)
    self.addCleanup(self.connection.close)
    self.connection.execute("truncate auth.users, auth.sessions, auth.refresh_tokens cascade")
    self.connection.execute("delete from public.private_media_provider_policy")
    self.connection.execute("""
      insert into public.private_media_provider_policy (
        singleton, enabled, auth_version, auth_source_commit, timebox_seconds,
        inactivity_timeout_seconds, single_per_user, allow_low_aal_seconds,
        refresh_rotation_enabled, refresh_reuse_interval_seconds, refresh_allow_reuse,
        refresh_token_algorithm_version, refresh_token_upgrade_percentage, verified_at, verified_until
      ) values (true, true, 'v2.197.0', '4eee58f296d9698a1c2c0ae14d7a0b379c7622d3',
        0, 0, false, 0, true, 10, false, 2, 100, clock_timestamp() - interval '1 minute',
        clock_timestamp() + interval '1 hour')
    """)
    self.connection.execute("insert into auth.users(id) values (%s)", (USER,))
    self.connection.execute("insert into auth.sessions(id, user_id, created_at) values (%s, %s, clock_timestamp() - interval '1 hour')", (SESSION, USER))
    self.connection.execute("insert into auth.refresh_tokens(user_id, session_id) values (%s, %s)", (USER, SESSION))

  def live(self, user=USER, session=SESSION, role="service_role"):
    with self.psycopg.connect(DATABASE_URL, autocommit=True) as connection:
      connection.execute(self.psycopg.sql.SQL("set role {}").format(self.psycopg.sql.Identifier(role)))
      return connection.execute("select public.private_media_session_is_live(%s::uuid, %s::uuid)", (user, session)).fetchone()[0]

  def policy(self, **fields):
    for name, value in fields.items():
      self.connection.execute(self.psycopg.sql.SQL("update public.private_media_provider_policy set {} = %s").format(self.psycopg.sql.Identifier(name)), (value,))

  def live_since(self, cutoff, role="service_role"):
    with self.psycopg.connect(DATABASE_URL, autocommit=True) as connection:
      connection.execute(self.psycopg.sql.SQL("set role {}").format(self.psycopg.sql.Identifier(role)))
      return connection.execute("select public.private_media_session_is_live_since(%s::uuid,%s::uuid,%s::timestamptz)", (USER, SESSION, cutoff)).fetchone()[0]

  def test_cutoff_helper_requires_strictly_newer_live_session(self):
    created = self.connection.execute("select created_at from auth.sessions where id = %s", (SESSION,)).fetchone()[0]
    from datetime import timedelta
    self.assertIs(self.live_since(created - timedelta(microseconds=1)), True)
    self.assertIs(self.live_since(created), False)
    self.assertIs(self.live_since(created + timedelta(microseconds=1)), False)
    for invalid in (None, "infinity", "-infinity"):
      self.assertIs(self.live_since(invalid), False)
    self.policy(enabled=False)
    self.assertIs(self.live_since(created - timedelta(days=1)), False)

  def test_cutoff_helper_has_only_service_execute_and_fixed_definer_scope(self):
    for role in ("anon", "authenticated", "unrelated_caller"):
      with self.subTest(role=role), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.live_since("2020-01-01Z", role)
    row = self.connection.execute("select prosecdef,provolatile,proconfig from pg_catalog.pg_proc where oid = 'public.private_media_session_is_live_since(uuid,uuid,timestamptz)'::regprocedure").fetchone()
    self.assertEqual(row[:2], (True, "v"))
    self.assertIn('search_path=""', row[2])

  def test_cutoff_never_bypasses_deleted_session_or_family_revocation(self):
    self.assertIs(self.live_since("2020-01-01Z"), True)
    self.connection.execute("update auth.refresh_tokens set revoked = true")
    self.assertIs(self.live_since("2020-01-01Z"), False)
    self.connection.execute("delete from auth.sessions")
    self.assertIs(self.live_since("2020-01-01Z"), False)

  def test_valid_legacy_session_is_live_for_service_role(self):
    self.assertIs(self.live(), True)

  def test_new_default_policy_is_disabled_and_missing_binding_denies(self):
    self.connection.execute("delete from public.private_media_provider_policy")
    self.assertIs(self.live(), False)
    self.connection.execute("insert into public.private_media_provider_policy(singleton) values (true)")
    self.assertIs(self.live(), False)
    self.policy(enabled=True)
    self.assertIs(self.live(), False)

  def test_missing_null_nil_and_wrong_owner_identifiers_deny(self):
    for user, session in [(None, SESSION), (USER, None), (NIL, SESSION), (USER, NIL),
                          (OTHER_USER, SESSION), (USER, OTHER_SESSION)]:
      with self.subTest(user=user, session=session):
        self.assertIs(self.live(user, session), False)
    self.connection.execute("insert into auth.users(id) values (%s)", (OTHER_USER,))
    self.assertIs(self.live(OTHER_USER, SESSION), False)

  def test_user_deletion_and_soft_deletion_deny(self):
    self.connection.execute("update auth.users set deleted_at = clock_timestamp() where id = %s", (USER,))
    self.assertIs(self.live(), False)
    self.connection.execute("delete from auth.users where id = %s", (USER,))
    self.assertIs(self.live(), False)

  def test_active_ban_denies_and_elapsed_ban_allows(self):
    self.connection.execute("update auth.users set banned_until = clock_timestamp() + interval '1 hour'")
    self.assertIs(self.live(), False)
    self.connection.execute("update auth.users set banned_until = clock_timestamp() - interval '1 microsecond'")
    self.assertIs(self.live(), True)
    self.connection.execute("update auth.users set banned_until = 'infinity'")
    self.assertIs(self.live(), False)

  def test_not_after_future_allows_but_current_past_and_infinity_deny(self):
    self.connection.execute("update auth.sessions set not_after = clock_timestamp() + interval '1 hour'")
    self.assertIs(self.live(), True)
    self.connection.execute("update auth.sessions set not_after = clock_timestamp()")
    self.assertIs(self.live(), False)
    self.connection.execute("update auth.sessions set not_after = clock_timestamp() - interval '1 hour'")
    self.assertIs(self.live(), False)
    self.connection.execute("update auth.sessions set not_after = 'infinity'")
    self.assertIs(self.live(), False)

  def test_legacy_family_revocation_denies_without_deleting_session(self):
    self.connection.execute("update auth.refresh_tokens set revoked = true, updated_at = clock_timestamp()")
    self.assertIs(self.live(), False)
    self.assertEqual(self.connection.execute("select count(*) from auth.sessions").fetchone()[0], 1)

  def test_historical_revoked_legacy_row_does_not_deny_active_successor(self):
    self.connection.execute("update auth.refresh_tokens set revoked = true")
    self.connection.execute("insert into auth.refresh_tokens(user_id, session_id) values (%s, %s)", (USER, SESSION))
    self.assertIs(self.live(), True)

  def test_missing_or_mismatched_active_legacy_row_denies(self):
    self.connection.execute("update auth.refresh_tokens set user_id = %s", (OTHER_USER,))
    self.assertIs(self.live(), False)
    self.connection.execute("update auth.refresh_tokens set user_id = %s, instance_id = %s", (USER, OTHER_USER))
    self.assertIs(self.live(), False)
    self.connection.execute("delete from auth.refresh_tokens")
    self.assertIs(self.live(), False)

  def test_v2_counter_zero_with_no_legacy_row_is_supported(self):
    self.connection.execute("delete from auth.refresh_tokens")
    self.connection.execute("update auth.sessions set refresh_token_counter = 0, refresh_token_hmac_key = 'synthetic-key-not-real'")
    self.assertIs(self.live(), True)

  def test_upgraded_v2_session_with_only_revoked_legacy_rows_is_supported(self):
    self.connection.execute("update auth.refresh_tokens set revoked = true")
    self.connection.execute("update auth.sessions set refresh_token_counter = 8, refresh_token_hmac_key = 'synthetic-encrypted-envelope-not-real'")
    self.assertIs(self.live(), True)

  def test_v2_reuse_termination_denies_after_provider_session_deletion(self):
    self.connection.execute("update auth.sessions set refresh_token_counter = 8, refresh_token_hmac_key = 'synthetic-key-not-real'")
    self.assertIs(self.live(), True)
    self.connection.execute("delete from auth.sessions")
    self.assertIs(self.live(), False)

  def test_partial_empty_negative_and_exhausted_counter_states_deny(self):
    for counter, key in [(None, "synthetic"), (0, None), (-1, "synthetic"), (0, ""), (9223372036854775807, "synthetic")]:
      with self.subTest(counter=counter, key=key):
        self.connection.execute("update auth.sessions set refresh_token_counter = %s, refresh_token_hmac_key = %s", (counter, key))
        self.assertIs(self.live(), False)

  def test_oauth_unknown_aal_future_created_and_unknown_user_class_deny(self):
    statements = [
      ("update auth.sessions set oauth_client_id = %s", (OTHER_USER,)),
      ("update auth.sessions set oauth_client_id = null, scopes = 'openid'", ()),
      ("update auth.sessions set scopes = null, aal = 'aal3'", ()),
      ("update auth.sessions set aal = 'aal1', created_at = clock_timestamp() + interval '1 hour'", ()),
      ("update auth.sessions set created_at = '-infinity'", ()),
      ("update auth.sessions set created_at = clock_timestamp() - interval '1 hour'; update auth.users set is_anonymous = true", ()),
      ("update auth.users set is_anonymous = false, role = 'service_role'", ()),
      ("update auth.users set role = 'authenticated', aud = 'other'", ()),
      ("update auth.users set aud = 'authenticated', instance_id = %s", (OTHER_USER,)),
    ]
    for sql, args in statements:
      with self.subTest(sql=sql):
        self.connection.execute(sql, args)
        self.assertIs(self.live(), False)

  def test_unknown_or_unsupported_policy_and_version_deny(self):
    fields = {
      "auth_version": "v2.198.0", "auth_source_commit": "unknown", "timebox_seconds": 60,
      "inactivity_timeout_seconds": 60, "single_per_user": True, "allow_low_aal_seconds": 60,
      "refresh_rotation_enabled": False, "refresh_reuse_interval_seconds": 11,
      "refresh_allow_reuse": True, "refresh_token_algorithm_version": 3,
      "refresh_token_upgrade_percentage": 101,
    }
    for name, value in fields.items():
      old = self.connection.execute(self.psycopg.sql.SQL("select {} from public.private_media_provider_policy").format(self.psycopg.sql.Identifier(name))).fetchone()[0]
      for invalid in (value, None):
        with self.subTest(field=name, value=invalid):
          self.policy(**{name: invalid})
          self.assertIs(self.live(), False)
      self.policy(**{name: old})
    self.assertIs(self.live(), True)

  def test_all_known_algorithm_versions_and_rollout_percentages_are_bound(self):
    for algorithm in (0, 1, 2):
      for rollout in (0, 25, 100):
        with self.subTest(algorithm=algorithm, rollout=rollout):
          self.policy(refresh_token_algorithm_version=algorithm, refresh_token_upgrade_percentage=rollout)
          self.assertIs(self.live(), True)

  def test_expired_future_and_nonfinite_policy_evidence_denies(self):
    for change in ["verified_until = clock_timestamp()", "verified_at = clock_timestamp() + interval '2 hours'",
                   "verified_at = null", "verified_until = 'infinity'", "verified_at = '-infinity'"]:
      with self.subTest(change=change):
        self.connection.execute("update public.private_media_provider_policy set verified_at = clock_timestamp() - interval '1 minute', verified_until = clock_timestamp() + interval '1 hour'")
        self.connection.execute("update public.private_media_provider_policy set " + change)
        self.assertIs(self.live(), False)

  def test_only_service_role_has_caller_execute_and_no_caller_gets_auth_or_policy_access(self):
    for role in ("anon", "authenticated", "unrelated_caller"):
      with self.subTest(role=role), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.live(role=role)
    for role in ("anon", "authenticated", "service_role", "unrelated_caller"):
      for table in ("auth.users", "auth.sessions", "auth.refresh_tokens", "public.private_media_provider_policy"):
        with self.subTest(role=role, table=table), self.psycopg.connect(DATABASE_URL, autocommit=True) as connection:
          connection.execute(self.psycopg.sql.SQL("set role {}").format(self.psycopg.sql.Identifier(role)))
          with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
            connection.execute("select 1 from " + table)
      with self.subTest(role=role), self.psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute(self.psycopg.sql.SQL("set role {}").format(self.psycopg.sql.Identifier(role)))
        with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
          connection.execute("update public.private_media_provider_policy set enabled = true")

  def test_function_is_boolean_definer_volatile_with_empty_fixed_search_path(self):
    row = self.connection.execute("""select p.prosecdef, p.provolatile, p.proconfig,
      pg_catalog.pg_get_function_result(p.oid), pg_catalog.pg_get_userbyid(p.proowner)
      from pg_catalog.pg_proc p join pg_catalog.pg_namespace n on n.oid = p.pronamespace
      where n.nspname = 'public' and p.proname = 'private_media_session_is_live'""").fetchall()
    self.assertEqual(len(row), 1)
    self.assertEqual((row[0][0], row[0][1], row[0][3], row[0][4]), (True, "v", "boolean", "postgres"))
    self.assertIn('search_path=""', row[0][2])
    public_grants = self.connection.execute("""select count(*) from pg_catalog.pg_proc p,
      lateral pg_catalog.aclexplode(p.proacl) a
      where p.oid = 'public.private_media_session_is_live(uuid,uuid)'::regprocedure and a.grantee = 0""").fetchone()[0]
    self.assertEqual(public_grants, 0)

  def test_auth_schema_failure_denies_and_empty_search_path_rejects_shadowing(self):
    self.connection.execute("create temporary table users(id uuid)")
    self.connection.execute("set search_path = pg_temp, public, auth")
    self.assertIs(self.connection.execute("select public.private_media_session_is_live(%s::uuid,%s::uuid)", (USER, SESSION)).fetchone()[0], True)
    self.connection.execute("alter table auth.sessions rename to unavailable_sessions")
    try:
      self.assertIs(self.live(), False)
    finally:
      self.connection.execute("alter table auth.unavailable_sessions rename to sessions")
    self.assertIs(self.live(), True)


if __name__ == "__main__":
  unittest.main()
