#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "supabase" / "migrations"


def _normalized_sql() -> str:
  parts = []
  for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
    parts.append(f"\n-- {path.name}\n{path.read_text(encoding='utf-8')}")
  return "\n".join(parts).lower()


def _policy_blocks(sql: str) -> list[str]:
  return re.findall(r"create\s+policy\s+.*?;", sql, flags=re.DOTALL)


def _public_tables(sql: str) -> set[str]:
  return set(re.findall(r"create\s+table\s+(?:if\s+not\s+exists\s+)?public\.([a-z0-9_]+)", sql))


def audit_supabase_security() -> list[str]:
  sql = _normalized_sql()
  errors: list[str] = []

  for table in sorted(_public_tables(sql)):
    if not re.search(rf"alter\s+table\s+public\.{re.escape(table)}\s+enable\s+row\s+level\s+security", sql):
      errors.append(f"public.{table} is created without an enable row level security migration.")

  function_headers = list(re.finditer(
    r"create\s+(?:or\s+replace\s+)?function\s+([a-z0-9_]+)\.([a-z0-9_]+)\([^)]*\)",
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
  }
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

  for block in _policy_blocks(sql):
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
      if not has_bucket_check or not has_folder_owner_check:
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
