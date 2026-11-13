from pathlib import Path
import importlib.util
import shutil
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('peso_security_audit', Path(__file__).with_name('supabase_security_audit.py'))
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class ProviderSessionAuditTest(unittest.TestCase):
  def setUp(self):
    self.directory = tempfile.TemporaryDirectory(prefix='peso-session-audit-')
    self.addCleanup(self.directory.cleanup)
    self.migrations = Path(self.directory.name) / 'migrations'
    shutil.copytree(AUDIT.MIGRATIONS_DIR, self.migrations)
    self.mock = patch.object(AUDIT, 'MIGRATIONS_DIR', self.migrations)
    self.mock.start()
    self.addCleanup(self.mock.stop)

  def errors(self):
    return AUDIT.audit_supabase_security()

  def append(self, sql):
    (self.migrations / '99999999999999_fixture.sql').write_text(sql)

  def test_reviewed_disabled_migration_passes_without_modification(self):
    self.assertEqual(self.errors(), [])

  def test_each_function_requires_unchanged_source(self):
    p = self.migrations / AUDIT.PROVIDER_MIGRATION
    original = p.read_text()
    mutations = [
      ("enabled boolean not null default false", "enabled boolean not null default true"),
      ("set search_path = ''", "set search_path = public"),
      ("returns boolean", "returns text"),
      ("owner to postgres", "owner to service_role"),
      ("from public, anon, authenticated", "from public, anon"),
      ("to service_role;", "to authenticated;"),
      ("exception when others then", "exception when no_data_found then"),
      ("where s.id = p_session_id and s.user_id = p_user_id;", "where s.id = p_session_id;"),
      ("and p.verified_until > v_now", "and true"),
    ]
    for before, after in mutations:
      with self.subTest(before=before):
        self.assertIn(before, original)
        p.write_text(original.replace(before, after, 1))
        self.assertTrue(any('reviewed source' in error for error in self.errors()))
    p.write_text(original)
    self.assertEqual(self.errors(), [])

  def test_missing_migration_denies(self):
    (self.migrations / AUDIT.PROVIDER_MIGRATION).unlink()
    self.assertTrue(any('reviewed source' in error for error in self.errors()))

  def test_later_redefinition_is_not_covered_by_original_fingerprint(self):
    for name, signature in AUDIT.PROVIDER_FUNCTIONS.items():
      with self.subTest(name=name):
        self.append(f"create or replace function {name}({signature}) returns boolean language sql security definer as $$ select true; $$;")
        self.assertTrue(any('exactly one reviewed definition' in error for error in self.errors()))

  def test_quoted_definition_cannot_bypass_duplicate_guard(self):
    self.append('create or replace function "public"."private_media_session_is_live" (uuid,uuid) returns boolean language sql security definer as $$ select true; $$;')
    self.assertTrue(any('exactly one reviewed definition' in error for error in self.errors()))

  def test_later_grants_owner_or_search_path_changes_deny(self):
    for name, signature in AUDIT.PROVIDER_FUNCTIONS.items():
      for sql in [
        f'grant execute on function {name}({signature}) to authenticated;',
        f'grant all on function {name}({signature}) to public;',
        f'grant execute on function {name}({signature}) to unrelated_caller;',
        f'alter function {name}({signature}) owner to service_role;',
        f'alter function {name}({signature}) set search_path=public;',
        f'revoke execute on function {name}({signature}) from service_role;',
      ]:
        with self.subTest(sql=sql):
          self.append(sql)
          self.assertTrue(any('changed service-only' in error for error in self.errors()))

  def test_acl_syntax_cannot_hide_a_provider_target(self):
    statements = [
      'grant execute on function public.private_media_session_is_live( uuid, uuid ) to authenticated;',
      'grant execute on function "public"."private_media_session_is_live"(uuid,uuid) to authenticated;',
      'grant execute on function public.set_updated_at(), public.private_media_session_is_live(uuid,uuid) to authenticated;',
      'grant execute on routine public.private_media_session_is_live(uuid,uuid) to authenticated;',
      'grant execute on function private_media_session_is_live(uuid,uuid) to authenticated;',
      'grant execute on function public.private_media_session_is_live(text,text) to authenticated;',
      'alter function "public"."private_media_session_is_live"( uuid, uuid ) security invoker;',
    ]
    for sql in statements:
      with self.subTest(sql=sql):
        self.append(sql)
        self.assertTrue(any('changed service-only' in error for error in self.errors()))

  def test_broad_schema_function_grants_cannot_widen_reviewed_readers(self):
    for kind in ('functions','routines','procedures'):
      for schema in ('public','"public"','azure_scaler, public','"azure_scaler", "public"'):
        with self.subTest(kind=kind,schema=schema):
          self.append(f'grant execute on all {kind} in schema {schema} to authenticated;')
          self.assertTrue(any('Broad schema' in error for error in self.errors()))

  def test_unrelated_privileged_function_remains_rejected(self):
    self.append("create function public.unreviewed_reader() returns boolean language sql security definer as $$ select true; $$;")
    self.assertTrue(any('Unexpected SECURITY DEFINER' in error for error in self.errors()))

  def test_existing_rls_and_client_write_checks_remain_enforced(self):
    for sql in [
      'create table public.unprotected_fixture (id uuid);',
      'grant insert, update, delete on public.videos to authenticated;',
      'create view public.unsafe_view as select 1;',
    ]:
      with self.subTest(sql=sql):
        self.append(sql)
        self.assertTrue(self.errors())


  def test_profile_owner_helpers_require_exact_reviewed_source(self):
    p=self.migrations/AUDIT.PROFILE_OWNER_MIGRATION
    original=p.read_text()
    for before,after in [("is distinct from auth.uid()","is not distinct from auth.uid()"),
        ("for update nowait","for update"),("set search_path=''","set search_path=public"),
        ("to authenticated;","to public;")]:
      with self.subTest(before=before):
        self.assertIn(before,original);p.write_text(original.replace(before,after,1))
        self.assertTrue(any('Profile owner migration differs' in e for e in self.errors()))
    p.write_text(original);self.assertEqual(self.errors(),[])

  def test_profile_owner_helpers_reject_later_access_and_definition_changes(self):
    for name,signature in AUDIT.PROFILE_OWNER_FUNCTIONS.items():
      for sql in [f'grant execute on function {name}({signature}) to public;',
          f'grant execute on function {name}({signature}) to service_role;',
          f'alter function {name}({signature}) set search_path=public;',
          f'alter function {name}({signature}) owner to authenticated;',
          f'drop function {name}({signature}) cascade;']:
        with self.subTest(sql=sql):
          self.append(sql)
          self.assertTrue(any('changed owner-decision' in e for e in self.errors()))
    self.append('create or replace function "peso_private"."owned_media_write_is_live"(uuid) returns boolean language sql security definer as $$ select true; $$;')
    self.assertTrue(any('exactly one reviewed definition' in e for e in self.errors()))


  def test_avatar_storage_denial_accepts_only_exact_restrictive_shapes(self):
    path=self.migrations/'20261030000756_avatar_write_attempts.sql'
    source=path.read_text()
    self.assertEqual(self.errors(),[])
    mutations=[
      ("as restrictive", "as permissive"),
      ("for insert to authenticated", "for select to authenticated"),
      ("for update to authenticated", "for delete to authenticated"),
      ("to authenticated with check(bucket_id<>'profile-avatars')", "to anon with check(bucket_id<>'profile-avatars')"),
      ("to authenticated using(bucket_id<>'profile-avatars')", "to authenticated,anon using(bucket_id<>'profile-avatars')"),
      ("with check(bucket_id<>'profile-avatars')", "with check(bucket_id<>'profile-avatars' or true)"),
      ("using(bucket_id<>'profile-avatars')", "using(bucket_id<>'profile-avatars' or true)"),
      ("bucket_id<>'profile-avatars'", "bucket_id<>'videos'"),
      ("bucket_id<>'profile-avatars'", "bucket_id<>'PROFILE-AVATARS'"),
      ("avatar_backend_insert_only", "unreviewed_avatar_insert"),
    ]
    for before,after in mutations:
      with self.subTest(before=before,after=after):
        self.assertIn(before,source);path.write_text(source.replace(before,after,1))
        self.assertTrue(any('Storage' in error for error in self.errors()))
    path.write_text(source);self.assertEqual(self.errors(),[])

  def test_arbitrary_storage_exclusions_and_permissive_avatar_denials_stay_rejected(self):
    for sql in [
      "create policy unrelated_exclusion on storage.objects as restrictive for delete to authenticated using(bucket_id<>'videos');",
      "create policy arbitrary_avatar_policy on storage.objects as permissive for insert to authenticated with check(bucket_id<>'profile-avatars');",
      "create policy avatar_backend_delete_only on storage.objects as restrictive for delete to authenticated using(bucket_id<>'profile-avatars' or auth.uid() is not null);",
    ]:
      with self.subTest(sql=sql):
        self.append(sql)
        self.assertTrue(any('Storage' in error for error in self.errors()))

  def test_avatar_policy_keywords_allow_case_and_spacing_but_bucket_literal_is_exact(self):
    valid="CREATE POLICY avatar_backend_update_only ON storage.objects AS RESTRICTIVE FOR UPDATE TO authenticated USING (bucket_id <> 'profile-avatars') WITH CHECK (bucket_id <> 'profile-avatars');"
    self.assertTrue(AUDIT._avatar_storage_denial_policy(valid))
    self.assertFalse(AUDIT._avatar_storage_denial_policy(valid.replace("'profile-avatars'","'PROFILE-AVATARS'")))


if __name__ == '__main__':
  unittest.main()


class AvatarReadPolicyAuditTest(unittest.TestCase):
  def test_only_exact_restrictive_select_shape_is_accepted(self):
    valid="create policy avatar_backend_select_only on storage.objects as restrictive for select to authenticated using(bucket_id<>'profile-avatars');"
    self.assertTrue(AUDIT._avatar_storage_denial_policy(valid))
    for before, after in [('as restrictive','as permissive'),('to authenticated','to anon'),
        ('to authenticated','to authenticated,anon'),("bucket_id<>'profile-avatars'","bucket_id<>'videos'"),
        ("bucket_id<>'profile-avatars'","bucket_id<>'PROFILE-AVATARS'"),
        ("bucket_id<>'profile-avatars'","bucket_id<>'profile-avatars' or true"),
        ('avatar_backend_select_only','unreviewed_avatar_select')]:
      with self.subTest(after=after):
        self.assertFalse(AUDIT._avatar_storage_denial_policy(valid.replace(before,after)))

  def test_changed_select_policy_is_rejected_by_full_audit(self):
    with tempfile.TemporaryDirectory(prefix='peso-avatar-read-audit-') as name:
      directory=Path(name)/'migrations';shutil.copytree(AUDIT.MIGRATIONS_DIR,directory)
      migration=next(directory.glob('*_avatar_reader_grants.sql'));source=migration.read_text()
      with patch.object(AUDIT,'MIGRATIONS_DIR',directory):
        self.assertEqual(AUDIT.audit_supabase_security(),[])
        for before,after in [('as restrictive\nfor select','as permissive\nfor select'),
            ("for select to authenticated using(bucket_id<>'profile-avatars')", "for select to authenticated using(bucket_id<>'profile-avatars' or true)"),
            ('for select to authenticated','for select to authenticated,anon')]:
          with self.subTest(after=after):
            self.assertIn(before,source);migration.write_text(source.replace(before,after,1))
            self.assertTrue(any('Storage' in error for error in AUDIT.audit_supabase_security()))
        migration.write_text(source)
        self.assertEqual(AUDIT.audit_supabase_security(),[])
