from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import unittest
from urllib.parse import urlparse
from uuid import uuid4


DATABASE_URL = os.getenv('US_SIGNUP_HOOK_TEST_DATABASE_URL', '')
ROOT = Path(__file__).resolve().parents[2]
SUCCESSOR = ROOT / 'supabase/migrations/20261030201615_auth_signup_hook_schema_access.sql'


@unittest.skipUnless(DATABASE_URL, 'Dedicated localhost US signup hook database is not configured.')
class UsSignupHookPostgresTest(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    parsed = urlparse(DATABASE_URL)
    if parsed.hostname not in {'localhost', '127.0.0.1'} or parsed.path != '/peso_us_signup_hook_test':
      raise RuntimeError('Hook tests require the dedicated localhost peso_us_signup_hook_test database.')
    import psycopg
    cls.psycopg = psycopg
    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
      connection.execute((ROOT / 'backend/tests/fixtures/us_signup_hook_database.sql').read_text())
      for name in ('20260922003008_us_ip_beta_admission.sql', '20261029020225_us_ip_expiry_wall_clock.sql'):
        connection.execute((ROOT / 'supabase/migrations' / name).read_text())

  def setUp(self):
    self.connection = self.psycopg.connect(DATABASE_URL, autocommit=True)
    self.addCleanup(self.connection.close)
    self.connection.execute('revoke usage on schema public from supabase_auth_admin')
    self.connection.execute('truncate public.us_beta_ip_ranges')
    # Documentation-only addresses represent classified ranges, never production data.
    for network in ('192.0.2.0/24', '2001:db8:1::/48'):
      self.connection.execute("insert into public.us_beta_ip_ranges values (%s,'fixture-only',clock_timestamp()+interval '1 hour')", (network,))

  def migrate(self):
    self.connection.execute(SUCCESSOR.read_text())

  def query(self, statement, values=(), *, role=None):
    with self.psycopg.connect(DATABASE_URL) as connection:
      connection.execute("set local statement_timeout='2s'")
      if role:
        connection.execute(self.psycopg.sql.SQL('set local role {}').format(self.psycopg.sql.Identifier(role)))
      return connection.execute(statement, values).fetchall()

  def event(self, address):
    return {'metadata': {'name': 'before-user-created', 'uuid': str(uuid4()),
                         'time': datetime.now(timezone.utc).isoformat(), 'ip_address': address},
            'user': {'id': str(uuid4()), 'aud': 'authenticated', 'role': '', 'email': 'fixture@example.invalid',
                     'phone': '', 'identities': [], 'is_anonymous': False,
                     'created_at': '0001-01-01T00:00:00Z', 'updated_at': '0001-01-01T00:00:00Z',
                     'app_metadata': {'provider': 'email', 'providers': ['email']},
                     'user_metadata': {'country': 'US', 'ip_address': '192.0.2.1'}}}

  def hook(self, event, *, role='supabase_auth_admin'):
    return self.query('select public.hook_us_ip_before_user_created(%s::jsonb)', (json.dumps(event),), role=role)[0][0]

  def test_additive_migration_repairs_missing_schema_usage_before_hook_invocation(self):
    self.assertEqual(self.query("select has_schema_privilege('supabase_auth_admin','public','usage'), has_function_privilege('supabase_auth_admin','public.hook_us_ip_before_user_created(jsonb)','execute')"), [(False, True)])
    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege) as failure:
      self.hook(self.event('192.0.2.1'))
    self.assertIn('permission denied for schema public', str(failure.exception))
    self.migrate()
    self.assertEqual(self.hook(self.event('192.0.2.1')), {})
    self.assertEqual(self.hook(self.event('198.51.100.1'))['error']['http_code'], 403)

  def test_documented_auth_event_allows_fresh_ipv4_and_ipv6_without_existing_user(self):
    self.migrate()
    self.assertEqual(self.query("select to_regclass('auth.users')"), [(None,)])
    for address in ('192.0.2.1', '2001:db8:1::1'):
      with self.subTest(address=address):
        self.assertEqual(self.hook(self.event(address)), {})

  def test_successor_preserves_missing_malformed_foreign_and_expired_ip_denial(self):
    self.migrate()
    for address in ('198.51.100.1', '2001:db8:2::1', None, '', 'invalid'):
      with self.subTest(address=address):
        self.assertEqual(self.hook(self.event(address))['error']['http_code'], 403)
    for event in ({}, {'metadata': None}, {'metadata': {'name': 'different', 'ip_address': '192.0.2.1'}}):
      self.assertEqual(self.hook(event)['error']['http_code'], 403)
    self.connection.execute("update public.us_beta_ip_ranges set valid_until=clock_timestamp()-interval '1 second'")
    self.assertEqual(self.hook(self.event('192.0.2.1'))['error']['http_code'], 403)

  def test_only_schema_resolution_changes_and_client_roles_gain_no_access(self):
    def privileges(role):
      return self.query("select has_schema_privilege(%s,'public','usage'), has_schema_privilege(%s,'public','create'), has_table_privilege(%s,'public.us_beta_ip_ranges','select'), has_function_privilege(%s,'public.hook_us_ip_before_user_created(jsonb)','execute')", (role, role, role, role))[0]
    before = {role: privileges(role) for role in ('anon', 'authenticated', 'service_role')}
    self.migrate()
    self.assertEqual(privileges('supabase_auth_admin'), (True, False, True, True))
    for role, expected in before.items():
      self.assertEqual(privileges(role), expected)
      self.assertFalse(expected[3])
      with self.subTest(role=role), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.hook(self.event('192.0.2.1'), role=role)
    for role in ('anon', 'authenticated'):
      with self.subTest(role=role), self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
        self.query('select * from public.us_beta_ip_ranges', role=role)

  def test_schema_grant_replay_is_idempotent_and_keeps_hook_invoker_only(self):
    self.migrate()
    self.migrate()
    self.assertEqual(self.hook(self.event('192.0.2.1')), {})
    self.assertEqual(self.query("select prosecdef from pg_proc where oid='public.hook_us_ip_before_user_created(jsonb)'::regprocedure"), [(False,)])
    self.assertEqual(self.query("select has_schema_privilege('supabase_auth_admin','public','create')"), [(False,)])


if __name__ == '__main__':
  unittest.main()
