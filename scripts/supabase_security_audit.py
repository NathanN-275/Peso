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

  if re.search(r"security\s+definer", sql):
    errors.append("SECURITY DEFINER appears in migrations; manually verify it is not exposed or privilege-bypassing.")

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
