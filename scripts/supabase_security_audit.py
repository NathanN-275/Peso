#!/usr/bin/env python3
from __future__ import annotations

import re
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"


def _normalized_sql(*, preserve_case: bool = False) -> str:
  parts = []
  for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
    parts.append(f"\n-- {path.name}\n{path.read_text(encoding='utf-8')}")
  source = "\n".join(parts)
  return source if preserve_case else source.lower()


def _policy_blocks(sql: str) -> list[str]:
  return re.findall(r"create\s+policy\s+.*?;", sql, flags=re.DOTALL | re.IGNORECASE)


def _avatar_storage_denial_policy(block: str) -> bool:
  # These policies only subtract avatar access from existing owner policies.
  for operation, predicate in {
    "select": r"using\s*\({bucket}\)",
    "insert": r"with\s+check\s*\({bucket}\)",
    "update": r"using\s*\({bucket}\)\s+with\s+check\s*\({bucket}\)",
    "delete": r"using\s*\({bucket}\)",
  }.items():
    bucket = r"\s*bucket_id\s*<>\s*'(?-i:profile-avatars)'\s*"
    shape = (rf"create\s+policy\s+avatar_backend_{operation}_only\s+on\s+storage\.objects\s+"
      rf"as\s+restrictive\s+for\s+{operation}\s+to\s+authenticated\s+"
      + predicate.format(bucket=bucket) + r"\s*;")
    if re.fullmatch(shape, block, flags=re.IGNORECASE):
      return True
  return False


def _public_tables(sql: str) -> set[str]:
  return set(re.findall(r"create\s+table\s+(?:if\s+not\s+exists\s+)?public\.([a-z0-9_]+)", sql))


# These two boolean-only Auth readers were reviewed with real PostgreSQL ACL,
# owner/session, disabled-policy and failure-denial tests. Changed SQL needs review.
PROVIDER_MIGRATION = "20261026173152_private_media_provider_session_decision.sql"
PROVIDER_MIGRATION_SHA256 = "fd7e09a635b9e1e4c5cff76f85036077b7bfbfd4cc49e77577e8927bc6152840"
PROVIDER_FUNCTIONS = {
  "public.private_media_session_is_live": "uuid, uuid",
  "public.private_media_session_is_live_since": "uuid, uuid, timestamptz",
}


def _provider_function_errors(sql: str, headers: list[re.Match]) -> list[str]:
  errors = []
  migration = MIGRATIONS_DIR / PROVIDER_MIGRATION
  if not migration.exists() or hashlib.sha256(migration.read_bytes()).hexdigest() != PROVIDER_MIGRATION_SHA256:
    errors.append("Private media provider-session migration differs from its reviewed source.")
  identifiers = re.sub(r'"([a-z_][a-z0-9_]*)"', r'\1', sql)
  if re.search(r'grant\s+[^;]*\bon\s+all\s+(?:functions|routines|procedures)\s+in\s+schema\b', identifiers):
    errors.append('Broad schema function grants require explicit per-function review.')
  for name, signature in PROVIDER_FUNCTIONS.items():
    declarations = [h for h in headers if f"{h.group(1)}.{h.group(2)}" == name]
    if len(declarations) != 1:
      errors.append(f"{name} must have exactly one reviewed definition.")
    # Do not let another migration widen either reviewed function's direct ACL,
    # ownership or configuration while retaining the original source file.
    # Inspect the entire command so leading whitespace, quoted identifiers,
    # overloads and multi-target ACL syntax cannot hide a provider reader.
    statements = re.findall(r"(?:grant|revoke|alter)\s+[^;]*;", sql)
    normalized = []
    for statement in statements:
      statement = re.sub(r'"([a-z_][a-z0-9_]*)"', r'\1', statement)
      if not re.search(r"\b" + re.escape(name.split('.')[-1]) + r"\b", statement):
        continue
      statement = re.sub(r"\s+", " ", statement).strip()
      statement = re.sub(r"\s*([().,;])\s*", r"\1", statement)
      normalized.append(statement)
    canonical = re.sub(r"\s+", "", signature)
    expected = [
      f"alter function {name}({canonical})owner to postgres;",
      f"revoke all on function {name}({canonical})from public,anon,authenticated;",
      f"grant execute on function {name}({canonical})to service_role;",
    ]
    if sorted(normalized) != sorted(expected):
      errors.append(f"{name} has missing or changed service-only privileges, ownership or configuration.")
  return errors


PROFILE_OWNER_MIGRATION = "20261029210252_owner_profile_storage_admission.sql"
PROFILE_OWNER_MIGRATION_SHA256 = "217a626a5772eda76490fab1c324eee128c1c834094ebbaa958252150f86542e"
PROFILE_OWNER_FUNCTIONS = {
    "peso_private.initialize_private_media_owner": "",
    "peso_private.owned_media_write_is_live": "uuid",
}


def _profile_owner_function_errors(sql: str, headers: list[re.Match]) -> list[str]:
  errors = []
  migration = MIGRATIONS_DIR / PROFILE_OWNER_MIGRATION
  if not migration.exists() or hashlib.sha256(migration.read_bytes()).hexdigest() != PROFILE_OWNER_MIGRATION_SHA256:
    errors.append("Profile owner migration differs from its reviewed source.")
  for name, signature in PROFILE_OWNER_FUNCTIONS.items():
    if len([h for h in headers if f"{h.group(1)}.{h.group(2)}" == name]) != 1:
      errors.append(f"{name} must have exactly one reviewed definition.")
    statements = re.findall(r"(?:grant|revoke|alter|drop)\s+[^;]*;", sql)
    normalized = []
    for statement in statements:
      statement = re.sub(r'"([a-z_][a-z0-9_]*)"', r'\1', statement)
      if not re.search(r"\b" + re.escape(name.split('.')[-1]) + r"\b", statement):
        continue
      statement = re.sub(r"\s+", " ", statement).strip()
      normalized.append(re.sub(r"\s*([().,;])\s*", r"\1", statement))
    expected = [f"alter function {name}({signature})owner to postgres;",
      f"revoke all on function {name}({signature})from public,anon,authenticated,service_role,supabase_auth_admin;"]
    if name.endswith('owned_media_write_is_live'):
      expected.append(f"grant execute on function {name}({signature})to authenticated;")
    if sorted(normalized) != sorted(expected):
      errors.append(f"{name} has missing or changed owner-decision privileges, ownership or configuration.")
  return errors


def audit_supabase_security() -> list[str]:
  sql = _normalized_sql()
  errors: list[str] = []

  for table in sorted(_public_tables(sql)):
    if not re.search(rf"alter\s+table\s+public\.{re.escape(table)}\s+enable\s+row\s+level\s+security", sql):
      errors.append(f"public.{table} is created without an enable row level security migration.")

  function_headers = list(re.finditer(
    r'create\s+(?:or\s+replace\s+)?function\s+"?([a-z0-9_]+)"?\s*\.\s*"?([a-z0-9_]+)"?\s*\([^)]*\)',
    sql,
  ))
  security_definer_functions: set[str] = set()
  for index, header in enumerate(function_headers):
    next_start = function_headers[index + 1].start() if index + 1 < len(function_headers) else len(sql)
    function_block = sql[header.start():next_start]
    if re.search(r"security\s+definer", function_block):
      security_definer_functions.add(f"{header.group(1)}.{header.group(2)}")
  allowed_security_definer_functions = {
    "azure_scaler.analysis_queue_depth",
    "public.pending_video_analysis_job_count",
    *PROVIDER_FUNCTIONS,
    *PROFILE_OWNER_FUNCTIONS,
  }
  errors.extend(_provider_function_errors(sql, function_headers))
  errors.extend(_profile_owner_function_errors(sql, function_headers))
  unexpected_security_definer_functions = security_definer_functions - allowed_security_definer_functions
  if unexpected_security_definer_functions:
    errors.append(
      "Unexpected SECURITY DEFINER functions appear in migrations: "
      + ", ".join(sorted(unexpected_security_definer_functions))
    )

  if "azure_scaler.analysis_queue_depth" in security_definer_functions:
    scaler_function = re.search(
      r"create\s+or\s+replace\s+function\s+azure_scaler\.analysis_queue_depth\(\).*?\$\$;",
      sql,
      flags=re.DOTALL,
    )
    scaler_block = scaler_function.group(0) if scaler_function else ""
    if "set search_path = ''" not in scaler_block:
      errors.append("azure_scaler.analysis_queue_depth() does not use an empty fixed search_path.")
    if not re.search(
      r"revoke\s+all\s+privileges\s+on\s+function\s+azure_scaler\.analysis_queue_depth\(\)\s+"
      r"from\s+public\s*,\s*anon\s*,\s*authenticated\s*,\s*service_role",
      sql,
    ):
      errors.append("azure_scaler.analysis_queue_depth() is not revoked from every application role.")

  if "public.pending_video_analysis_job_count" in security_definer_functions:
    staging_scaler_checks = (
      r"create\s+or\s+replace\s+function\s+public\.pending_video_analysis_job_count\(\)",
      r"returns\s+integer",
      r"set\s+search_path\s*=\s*pg_catalog",
      r"revoke\s+execute\s+on\s+function\s+public\.pending_video_analysis_job_count\(\)\s+"
      r"from\s+public\s*,\s*anon\s*,\s*authenticated",
      r"grant\s+execute\s+on\s+function\s+public\.pending_video_analysis_job_count\(\)\s+"
      r"to\s+analysis_job_scaler",
    )
    if any(re.search(pattern, sql) is None for pattern in staging_scaler_checks):
      errors.append(
        "public.pending_video_analysis_job_count() is missing a reviewed SECURITY DEFINER safeguard."
      )

  if not (
    "to_regprocedure('public.rls_auto_enable()')" in sql
    and re.search(
      r"revoke\s+all\s+privileges\s+on\s+function\s+public\.rls_auto_enable\(\)\s+from\s+public\s*,\s*anon\s*,\s*authenticated",
      sql,
    )
  ):
    errors.append("public.rls_auto_enable() is not conditionally revoked from client roles.")

  if not re.search(
    r"alter\s+function\s+public\.set_updated_at\(\)\s+set\s+search_path",
    sql,
  ):
    errors.append("public.set_updated_at() does not have a fixed search_path migration.")

  for table in ("analysis_results", "profiles", "videos"):
    if not re.search(
      rf"revoke\s+all\s+privileges\s+on\s+table\s+public\.{table}\s+from\s+public\s*,\s*anon",
      sql,
    ):
      errors.append(f"public.{table} is not revoked from unauthenticated roles.")

  for match in re.finditer(r"create\s+(?:or\s+replace\s+)?view\s+public\.([a-z0-9_]+).*?;", sql, flags=re.DOTALL):
    block = match.group(0)
    if "security_invoker" not in block:
      errors.append(f"public.{match.group(1)} view does not explicitly opt into security_invoker.")

  for raw_block in _policy_blocks(_normalized_sql(preserve_case=True)):
    block = raw_block.lower()
    avatar_denial = _avatar_storage_denial_policy(raw_block)
    if re.match(r'create\s+policy\s+"?avatar_backend_(select|insert|update|delete)_only"?\s', block) and not avatar_denial:
      errors.append("Avatar backend Storage policies must keep their exact restrictive denial shape.")
    if "to authenticated" not in block:
      continue

    has_using = re.search(r"\busing\s*\(", block) is not None
    has_with_check = re.search(r"with\s+check\s*\(", block) is not None
    if "for update" in block and (not has_using or not has_with_check):
      errors.append(f"UPDATE policy is missing USING or WITH CHECK: {block.splitlines()[0]}")

    if "on public." in block and "auth.uid()" not in block:
      errors.append(f"Authenticated public-table policy does not reference auth.uid(): {block.splitlines()[0]}")

    if "on storage.objects" in block:
      has_bucket_check = "bucket_id" in block
      has_folder_owner_check = "storage.foldername" in block and "auth.uid()" in block
      if not avatar_denial and (not has_bucket_check or not has_folder_owner_check):
        errors.append(f"Storage policy lacks bucket/folder ownership checks: {block.splitlines()[0]}")

  if not re.search(r"revoke\s+insert\s*,\s*update\s*,\s*delete\s+on\s+public\.videos\s+from\s+authenticated", sql):
    errors.append("public.videos does not revoke direct authenticated insert/update/delete privileges.")

  if re.search(r"grant\s+(?:all|insert|update|delete|insert\s*,\s*update|insert\s*,\s*update\s*,\s*delete).*on\s+public\.videos\s+to\s+authenticated", sql):
    errors.append("public.videos grants direct authenticated write privileges.")

  video_upload_policies = list(re.finditer(
    r'create\s+policy\s+"users can upload own private videos"\s+on\s+storage\.objects.*?;',
    sql,
    flags=re.DOTALL,
  ))
  if not video_upload_policies or "storage.extension(name)" not in video_upload_policies[-1].group(0):
    errors.append("videos storage upload policy does not restrict object extensions.")

  for table in ("upload_reservations", "upload_admission_control"):
    if not re.search(rf"revoke\s+all\s+on\s+table\s+public\.{table}\s+from\s+public\s*,\s*anon\s*,\s*authenticated", sql):
      errors.append(f"public.{table} is not restricted to backend access.")
  for function in (
    "reserve_video_upload", "mark_video_upload_received", "verify_video_upload",
    "reject_video_upload", "expire_video_upload_reservations", "disable_video_upload_admission",
  ):
    if not re.search(rf"revoke\s+execute\s+on\s+function\s+public\.{function}\([^)]*\)\s+from\s+public\s*,\s*anon\s*,\s*authenticated", sql):
      errors.append(f"public.{function} is callable by client roles.")

  return errors


def main() -> int:
  errors = audit_supabase_security()

  if errors:
    print("Supabase security audit failed:")
    for error in errors:
      print(f"- {error}")
    return 1

  print("Supabase security audit passed.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
