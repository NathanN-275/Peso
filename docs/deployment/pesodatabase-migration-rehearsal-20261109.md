# Isolated Web MVP migration rehearsal — November 9, 2026

**Result: the separately approved 30-migration chain applied successfully to recovery project `peso-recovery-20261106` (`uhivjkfpfqtpicyjtmie`). Read-only history, original-data, schema and permission checks passed. Production was not migrated.**

Nathan approved the exact byte-pinned packet with “Yes—apply the 30 migrations to recovery only.” The existing target remains Free, in `us-east-1`, organization `ireiverxhceuwvshqkjz`. Signup, manual linking, anonymous sign-ins and Data API were disabled before execution and independently rechecked disabled afterward. No new synthetic accounts, client API activation, service resumption, paid-plan change, project pause or public exposure was included.

## Applied inputs and execution

- Source checkpoint: `b141cf205152f9c1142d60fba2e0ba2aac01d363`. The source manifest still names production; a separate explicit execution binding names only this recovery target. The source checkout/configuration and immutable backup were preserved.
- All 51 selected SQL files matched their SHA-256 pins. Only the reviewed Azure scaler migration, `202608300001_azure_analysis_queue_scaler.sql`, was excluded from the 52-file catalog.
- Supabase CLI 2.98.2, binary SHA-256 `bb68511c278d65563bdffb760c32d19fa5ce6b26396dcac946f1f82705d2b566`, used the dedicated linked recovery workspace and reviewed temporary configuration. No seed, custom-role, include-all, reset, migration repair or config-push action was used. Credentials stayed outside arguments and Git.
- Fresh preflight verified all 33 original rows, original counts/buckets/policies/history, and the exact 21 applied versions ending `202608270001`. A fresh linked dry run matched exactly the approved 30 pending files.
- The actual CLI application ran from `2026-11-09T22:51:35.714910Z` to `22:51:37.932814Z` and exited zero. The chain was not one atomic transaction; no application error or partial-chain retry occurred.

The [CLI documentation](https://supabase.com/docs/reference/cli/supabase-db-push) describes dry-run versus actual application. Pinned CLI source review established the dry-run path; database startup read-only enforcement is not claimed for that CLI connection.

## Verification

Read-only verification at `2026-11-09T22:51:53.163865Z` found exactly 51 expected migration versions/names, ending `20261103022851`. Every original value in the 33 protected rows remained unchanged, including the original Auth account/session/refresh records and the original 21 history records. Profile comparison used its original columns because the reviewed migration adds a generated `profile_revision`; that new nonzero revision and the one-owner backfill were independently verified.

All original public-table counts and three bucket definitions remain unchanged. New control rows are the expected upload-admission singleton, disabled provider-policy singleton and one private owner. Other new ledgers and geography are empty. Current Storage objects remain zero.

Permission and catalog checks found:

- All 20 public tables have RLS enabled. `anon` has no table privileges. Only `analysis_results`, `profiles` and `videos` have authenticated table access. The provider-policy table remains inaccessible to the service role as specified by the migration.
- Client-callable functions match the expected trigger/helper set. The sole anonymous-callable function, the pre-existing invoker trigger `set_updated_at()`, is unchanged from the preflight catalog. New private helper ownership, schema usage, fixed search paths and ACLs were captured; its owner-initialization trigger is installed on Auth users.
- Existing eight `NOT VALID` path/owner constraints are unchanged from the preflight snapshot; they were not silently validated or removed. Full trigger, policy, column, constraint and function readbacks are private evidence.
- Empty geography rejects IPv4, IPv6 and the direct before-user-created hook decision. This verifies the database decision with no loaded ranges; it does not activate an Auth hook, load geography, attest proxy trust or prove provider signup behavior. The private-media provider policy remains disabled.
- The application schema readback includes `peso_private`: 275,604 bytes, SHA-256 `ea42ef016c02892c3059bb4860205d9620b75efb55fcb85c56bdd5146ad32c6c`. No private row values or credentials are committed here.
- Post-migration dashboard reloads show signup/manual linking/anonymous sign-ins and Data API disabled. Production readback at `2026-11-09T22:53:04.359492Z` still has 21 migrations ending `202608270001`; complete history-content MD5 remains `2fbfb3b920d557a8bcde7e1027e6eb8b`.

## Retained diagnostics and advisor observations

The first preflight stopped before connecting because its direct-host template guard did not match the CLI-selected, dashboard-verified session pooler. The corrected preflight requires the exact recovery pooler host, port and username; this was not a target-identity bypass.

The first schema-capture attempt stopped because the local Docker engine was off. After it started, the older temporary CLI credential was rejected. An ordinary fresh CLI login immediately before the schema-only read succeeded. A local post-capture assertion then expected `CREATE TABLE` without the CLI's `IF NOT EXISTS` spelling; the successfully captured bytes were independently verified and the assertion corrected without rerunning the database read. All failed receipts and reader versions remain retained. None caused a migration retry or password reset.

Security advisors report 16 [RLS-enabled tables without client policies](https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy), consistent with the verified service-only grants; three source-granted tables' [authenticated GraphQL-schema visibility](https://supabase.com/docs/guides/database/database-linter?lint=0027_pg_graphql_authenticated_table_exposed); and existing [disabled leaked-password protection](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection). No ERROR-level security advisor entry was returned. This is not a clean-security or public-endpoint acceptance claim.

Performance observations are one [unindexed foreign key](https://supabase.com/docs/guides/database/database-linter?lint=0001_unindexed_foreign_keys), two [Auth RLS initialization-plan warnings](https://supabase.com/docs/guides/database/database-linter?lint=0003_auth_rls_initplan) and 29 [unused indexes](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index). No index, policy or feature was changed in response to these notices.

## Remaining release boundary

This accepts application of the selected chain to this isolated clone and the checks described above. Candidate real API/Auth/Storage behavior, geography/provider-policy activation and the release's browser/end-to-end requirements remain separate work. The earlier restore/byte-recovery result applies to its pre-migration snapshot state; it is not automatically acceptance of changed candidate behavior.

Recovery remains active and isolated; HootRoute remains paused. Retention/capacity changes require their own authorization. The November 6 freeze is expired. Production application requires fresh writer-freeze/export/protected-copy evidence, its own exact approval and subsequent production verification. No merge, deployment or launch follows implicitly from this result. The [single live gate tracker](public-beta-acceleration-plan-20261105.md) retains the complete launch objective.

Evidence root: the chat's private visualization directory, `recovery-migration-rehearsal-20261109/`. Its `approved-application-20261109-v2/` contains the application start/result, immutable pre/post catalog and original-row verification, permission/read-only contract receipts, schema capture, advisors, production-history readback and consolidated `rehearsal-verification.json`. Isolation screenshots are in the rehearsal root. Original stopped attempts remain alongside it. Raw SQL, private identities and temporary connection plans stay outside Git.
