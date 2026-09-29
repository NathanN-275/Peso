# Private candidate — chunk 1 recovery evidence

September 29, 2026 UTC (September 28 in Nathan's timezone).
**Result: BLOCKED. Local policy rehearsal passes; complete recovery gate does not.**
No hosted changes, migrations, Render resumption, or guardrail activation occurred.

## Verified evidence

- `python3 scripts/rehearse_storage_policy_recovery.py`: **61 assertions passed**.
  All eight authenticated Storage policies restore. Owner CRUD, other-user/anon
  denial, path and extension restrictions, and service-role bypass pass.
- Missing helper failure partway through policy creation rolls back to zero
  policies. A refused rerun leaves all eight policy definitions unchanged.
  The test container and synthetic data were removed successfully.
- Docker initially was unavailable. After startup, one fixture-load attempt
  failed and the next passed. The original generic error did not preserve its
  SQL cause. The runner now reports synthetic SQL diagnostics and waits for TCP
  readiness, excluding the image's socket-only initialization server. The final
  run has no recovery mismatch; the exact first fixture error is unconfirmed.
- The restore artifact's eight `CREATE POLICY` statements exactly match the
  September 23 private managed-schema export. No policy change was necessary.
- All six September 23 SQL files still match their SHA-256 manifest and have
  mode `0600`; the containing directory is `0700`. Backup location:
  `/Users/nathan/Downloads/peso-private-backups/2026-09-23-pesodatabase-pre-migration`.
- Its `storage.objects` COPY section has zero rows. This verifies only the
  historical empty inventory, not today's Storage state or API byte recovery.
- Pre-cutover checker regression suite: **26 tests passed**. `git diff --check`
  passed. These tests are not current provider evidence.
- At `2026-09-29T01:31:53Z`, verified the ZIP Nathan reported downloading
  after uploading the private backup folder to Proton Drive. It contains exactly
  the six expected SQL files and `SHA256SUMS`; every file is byte-for-byte
  identical to the original, and all six SHA-256 checks pass. Verification read
  the ZIP directly without extracting or displaying private data. Remote origin
  is based on Nathan's upload/download report, not independent account inspection;
  account sharing and recovery settings were not inspected. This verifies the
  second copy of the historical backup only.

## SHA-256 evidence

| Artifact | SHA-256 |
| --- | --- |
| Private `SHA256SUMS` | `abae8d0e618df8b07d21a49cb90563693223d519bd542f7a9e8becc26dea3e57` |
| Proton downloaded ZIP | `06b089e4e9dca40bb273f9510e6ab7b1c3dd9c53a604e23a46a25c596d2851f0` |
| `roles.sql` | `0f63b83fd24aaa9450c44a8e4bca19afaa2c303594f4886c9be396e4bec3158b` |
| `schema.sql` | `cc23548d35ef96531620428cec2cf54808d70602c47a58df16c1f1b82873299c` |
| `auth_storage_schema.sql` | `13fc409ef4c0af726d6245df961979bf5f15c201c2e044138ca0862a8c2e08b5` |
| `data.sql` | `7e15080f0ed2d908086e95ba5d12064fa3e88fd33cc35248325d83c53762c935` |
| `history_schema.sql` | `18b99fbbb3ec9fbb964bb255a56171329acd99b6977ece2addd89fdf5aa5105b` |
| `history_data.sql` | `51f6212de0d605fd2dc3328c455a17827a40a62f1dd74b6ce2dfcbed41eb55f2` |
| Recovery SQL | `30bccff481434a9427963afa979c22c40589be39e830c14aa18c7bcd5790c3e1` |
| Synthetic fixture | `3705a64d122ddcf7a4c17819db72acaae45c4d2c4b0c9406d5a794effdb13e38` |
| Rehearsal runner | `2e137c7e0bf9922f3ba45b7b225758eb073f953fe625f2fd021f92dc9ceb7cc8` |
| Restored policy catalog JSON | `3bfdb81204916071fb7f6aa552329f1ae9cf6a129c429bb880481f93bba17445` |

Catalog digest is computed from the runner's ordered `pg_policies` JSON text;
it is distinct from the SQL-file digest. Local image ID:
`sha256:67f41722b7a8cbdb868a44a4995c846eddfdc2973bccb291ce937dce88ad5675`.

## Restore and rollback steps

1. Verify the six private files with `shasum -a 256 -c SHA256SUMS`. Verify the
   second copy independently before relying on it. Stop on any mismatch.
2. For synthetic local policy verification, run the rehearsal command above.
   It creates its own networkless database, injects a restore failure, verifies
   transactional rollback, restores successfully, and removes its own container.
3. For real database recovery, obtain the separate isolated hosted target
   approval and verify its identity. Follow the [hosted restore recipe](pesodatabase-hosted-recovery-rehearsal-20260924.md):
   retain managed schemas; use a private roles copy omitting only the known
   forbidden platform setting; restore roles, application schema, history
   schema, data and history data with TLS, a single transaction and
   `ON_ERROR_STOP=1`. Any error aborts that transaction. Preserve source dumps.
4. Restore reviewed custom managed-schema definitions separately. The policy
   SQL requires enabled RLS, no existing object policies and explicit isolated
   target acknowledgement. Do not apply it after security cutover, because it
   restores direct client writes. Validate definitions and actual owner/non-owner
   Auth/Storage access before any separately approved service rebind.
5. For nonempty Storage, restore separately backed-up bytes, compare inventory,
   lengths and checksums, then read back through the API. SQL metadata alone
   cannot restore bytes. Keep failed-state evidence and stop on discrepancies.
6. A partially applied seven-migration chain is not one atomic transaction.
   Keep services suspended, inspect actual history, and prepare reviewed forward
   repair or isolated recovery. Never run this recovery SQL against production
   as an automatic down migration or restore over an existing project as a test.

This follows [Supabase's separate managed-schema recovery guidance](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore).

## Open blockers before chunk 2

- A new September 29 snapshot is prepared as described below. Its Proton
  upload/download verification and hosted restore remain pending. Full writer
  freeze is not independently proven; retain `freeze_verified=false` and take
  a fresh cutover-window snapshot under the [freeze procedure](pesodatabase-precutover-packet.md)
  before migration. The checker freshness limit is 60 minutes.
- Nathan confirmed the Proton folder is private, recovery information is saved,
  and Peso apps will remain closed with no uploads, signups or database edits
  during recovery. Historical second-copy integrity passed; new-copy integrity
  is still pending.
- Hosted custom Storage-policy recovery and real Storage API access remain
  unverified. No isolated hosted target is currently approved. Keep
  `managed_schema_customizations_verified=false`.

Do not advance to cutover approval on the strength of this local result.

## Follow-up: new recovery snapshot and reviewable hosted test

The final export ran `2026-09-29T01:39:04Z`–`01:39:28Z`, after Nathan's
quiet-window confirmation. It is in the private directory
`/Users/nathan/Downloads/peso-private-backups/2026-09-29-recovery-013904`.
An earlier `013553` export is retained privately but is not the selected packet.
All six final SQL checksums and `0600` permissions pass. All eight policy
statements exactly match the reviewed recovery SQL. Source observations before
(`01:38:07Z`) and after (`01:39:50Z`) export both show zero videos, active jobs,
and Storage objects. All three buckets are private; limits and MIME settings
are saved in `storage-inventory.json`. No object bytes were copied because the
inventory is empty. This does not prove absence of in-flight/orphaned bytes.

Both Render service dashboards showed suspended at verification, with deployed
commit `4325798f4a4bd7a8f8d55587c5520a5cf9c014d3`. GitHub repository API access
succeeded; workflow and repository-variable listings contain neither the budget
workflow nor its enable variable. Initial direct reads returned unavailable
because these entries are absent. No `pg_cron`/`pg_net` extensions or custom
Auth/Storage triggers calling functions outside managed schemas were found.
These observations support a quiet window but are not an exhaustive writer audit.

Upload artifact: `2026-09-29-recovery-013904.zip` in the private backup root.
It contains SQL, manifests, snapshot metadata, inventory and recovery notes;
diagnostic logs are excluded. ZIP CRC and byte-for-byte read-back passed.

| Digest | SHA-256 |
| --- | --- |
| SQL manifest | `da6d96392fb99ed7425b4f2782ba47267652b65d195080870b258ec8dc71df5b` |
| Packet manifest | `aecc905adab9b37ffa7da28472ffd5567987c9fb67c6fc9541094162c76404f3` |
| Upload ZIP | `2357105a5c00b164fc3344d609450e5087aa34bdeecae6d7a7eb03f5f465756e` |

### Proposed hosted operation — awaiting approval

Target organization: **NathanN-275's Org** (`ireiverxhceuwvshqkjz`), currently
Free. Both source and staging are healthy. [Free-plan limits](https://supabase.com/docs/guides/platform/billing-on-supabase)
allow two active projects and exclude paused projects. Confirm organization and
provider cost before creation; stop if the proposed operation requires payment.

1. Temporarily pause **peso-staging** (`iseqgaewjpjcxrndibep`). This interrupts
   staging Auth/Database/Storage until resumed. Never pause PesoDatabase.
2. Create **peso-recovery-20260929** in **us-east-1**, in the organization above,
   only if confirmed free. Record and verify its new ref before any restore.
3. Restore the selected private backup using the transactional recipe above,
   retaining platform-managed schemas. Restore the reviewed custom policies;
   compare definitions, roles, RLS, bucket privacy/limits, rows and history.
   Exercise a failed policy transaction and confirm rollback before successful
   policy restoration. Stop on any unexplained mismatch.
4. In the new target only, create two synthetic test accounts (no email sends),
   use authenticated Storage API calls to test owner CRUD, other-user and anon
   denial, MIME/size enforcement and byte read-back checksums. Verify Auth and
   API access without printing tokens, row contents or private files.
5. Whether the test passes or fails, pause the disposable target and resume
   staging; verify staging returns healthy. Keep the paused test project for
   investigation. Permanent deletion requires its own decision.

Approval covers only this isolated recovery operation. Production migrations,
Render configuration/resumption, budget activation and public launch remain
outside its scope. No proposed hosted mutation has occurred.
