# Web MVP migration preparation

The Web MVP uses Render for the API and worker and Supabase for Auth, Postgres
and video Storage. Its migration preparation excludes the never-applied
`202608300001_azure_analysis_queue_scaler.sql`. That file only creates an Azure
scaler schema and a queue-depth reader; the other 51 migrations do not reference
those objects. Keep the file in the repository for separate environments.
The already-applied `202608270001_add_analysis_job_scaler_signal.sql` remains
part of observed hosted history and is not removed or replayed.

`config/web-mvp-migrations.json` freezes the original 52 migration filenames and
SHA-256 hashes from evidence base `98229d53aaf17571fe0b3583f7cd72fb2ec50b12`.
It selects 51 files, records the exact Azure exclusion, preserves the observed
21 hosted version/name pairs and lists the ordered 30 pending files. The evidence
base identifies this reviewed SQL catalog; it is not the eventual release SHA
or proof that hosted statements match these local bytes.

Run the local preparer with a read-only history snapshot and a new destination
outside the source checkout:

```sh
python3 scripts/prepare_web_mvp_migrations.py \
  --source-root /absolute/path/to/reviewed-checkout \
  --history /absolute/path/to/hosted-history.json \
  --destination /absolute/path/to/new-mvp-migration-workspace
```

The snapshot format is the November 5 connector readback format. Required fields
are `observedAtUtc` in UTC `YYYY-MM-DDTHH:MM:SSZ` form, `project.id` and
`project.ref` both equal to `jfgiydtrskpqxyorvvbc`, and `hostedMigrations` containing
exactly the 21 reviewed ordered objects with only `version` and `name` keys.
Additional readback metadata is ignored and is not copied to the receipt. The
preparer neither fetches nor refreshes history. A previously captured snapshot
can prepare files, but cannot establish current hosted state or freshness.

Preparation validates the complete catalog, hashes and history before creating
anything. Missing, modified or unknown migration entries, symlinks, changed
names or versions, an applied Azure exclusion and an existing destination fail
closed. It creates only the selected SQL files and `preparation-receipt.json`,
then verifies copied bytes. The reviewed source contains no `supabase/config.toml`,
so the current receipt has a null config hash. A future source config must have
an explicit manifest hash before it can be copied. No configuration is invented.
No `.temp` project link, credentials, SQL execution, CLI invocation or migration
history repair occurs. An interrupted or failed write can leave an incomplete
owned destination; preparation never overwrites or automatically deletes it.

The receipt binds manifest, input snapshot and source-catalog hashes, selected
files, the exclusion and pending order. Its provider mutation, live-history,
dry-run, restore-rehearsal and application claims remain false. A successful
preparation receipt is not deployment approval.

## Production cutover preflight

Use the separately approved window, exact release checkout and **PesoDatabase**
(`jfgiydtrskpqxyorvvbc`). The [November 8 Hosted Restore Rehearsal](pesodatabase-hosted-recovery-rehearsal-20261108.md)
and [November 9 application rehearsal](pesodatabase-migration-rehearsal-20261109.md)
cover their recorded snapshot and SQL selection. Verify that this evidence
covers Auth, Storage, RLS, queue and budget requirements for the candidate, and
rerun any required checks whose inputs or coverage changed.

1. Record the approved freeze start and expiry and verify the actual production
   writer state. Include clients, direct Storage upload capabilities, Auth and
   Data API writers, API and worker services, accepted jobs, exports, cleanup
   and scheduled jobs. Drain accepted work and recheck in-flight Storage writes.
   Stop if any writer can still change the snapshot or the freeze expires.
2. While frozen, take a fresh private logical export of roles, application
   schema/data, custom managed-schema definitions, and migration history/schema.
   Verify recovery coverage for Auth data and custom Auth/Storage policies,
   triggers and grants using the rehearsed export approach. Inventory all
   buckets and object metadata. Export every inventoried object's bytes separately
   and verify its length and checksum, or record an independently checked empty
   inventory. Record project-bound settings needed for recovery privately.
   Recheck the freeze and inventory after export. Verify the full archive and
   checksum manifest from a fresh read of the protected off-machine copy. Keep
   data, connection details and object keys out of Git. [Supabase backup coverage](https://supabase.com/docs/guides/platform/backups)

   Use the rehearsed `.tar.gz` layout with `snapshot.json`,
   `source-catalog.private.json`, six SQL exports under `sql/` and
   `sql/SHA256SUMS`. Create `SHA256SUMS` from inside `sql/` using the six dump
   basenames. Retain the frozen Storage inventory separately and place a
   byte-identical copy at the archive root as `storage-inventory.json`. Use
   `projectRef` for the production project and `objects` for the complete list.
   For each inventoried object record `bucket`, `key`, `archiveFile`, `sizeBytes`
   and lowercase SHA-256 as `sha256`. The unique `archiveFile` path must use
   `storage/` followed by eight digits and `.bin`, such as `storage/00000001.bin`. Use `"objects": []` for an independently verified empty inventory.
   Preserve genuine zero-byte objects with their exact length and digest.
   Pack the reviewed files at the archive root, with directory entries optional,
   and exclude symlinks, AppleDouble metadata, and unrelated files. With the
   macOS system `tar`, pass `--no-mac-metadata`.

   From the reviewed source checkout, compare the private original with a fresh
   download from the protected off-machine destination using Python 3.11 or later.

   ```sh
   python3 scripts/check_pesodatabase_backup_copy.py \
     --original /path/to/private/original.tar.gz \
     --downloaded /path/to/private/downloaded.tar.gz \
     --inventory /path/to/private/frozen-storage-inventory.json
   ```

   This check reads the archives without extracting them. Retain the aggregate
   hashes and counts with independent writer-freeze, project identity, inventory
   coverage, access protection, and download provenance evidence. Stop before
   migration if any part of the recovery point is unverified.
3. Read exact current production history and run the preparer above in a new
   private workspace. Require 21 matching applied migrations, 51 selected
   files and 30 pending, excluding only the legacy Azure scaler migration.
   Pin the release SHA, preparation receipt and workspace config checksum.
   Use the rehearsed Supabase CLI `2.98.2` with binary SHA-256
   `bb68511c278d65563bdffb760c32d19fa5ce6b26396dcac946f1f82705d2b566`.
   Initialize the workspace with reviewed migration configuration, no Vault
   values and no role or seed file. Verify the linked ref and actual connection
   host, database, port and role for PesoDatabase independently. Clear inherited
   project, workdir and connection overrides, including `SUPABASE_PROJECT_ID`. Use
   the existing authorized production password through private
   `SUPABASE_DB_PASSWORD` for both CLI reads. If it is unavailable, stop before
   invoking either linked command. The pinned CLI can create a temporary role
   and remove network bans when it falls back to automatic login. Keep
   credentials out of output and use `verify-full` TLS with the approved CA
   certificate in `PGSSLROOTCERT`. [Pinned CLI connection source](https://raw.githubusercontent.com/supabase/cli/v2.98.2/internal/utils/flags/db_url.go)
4. In that workspace, capture `supabase migration list --linked --agent no`
   with the same credential and TLS settings and confirm local/remote versions
   against the preparation receipt. Run the preview from the same directory.
   Set both paths below to absolute private paths and use the verified CLI on
   `PATH`. Require the exact ordered pending file list.

   ```sh
   (
     umask 077
     set -C
     set +x
     if [ -z "${SUPABASE_DB_PASSWORD:-}" ] || [ ! -r "${PGSSLROOTCERT:-}" ]; then
       printf '%s\n' 'Load the approved production credential and CA privately.' >&2
       exit 1
     fi
     export SUPABASE_DB_PASSWORD PGSSLROOTCERT
     cd "$PESO_MIGRATION_WORKSPACE" &&
       PGSSLMODE=verify-full NO_COLOR=1 SUPABASE_TELEMETRY_DISABLED=1 \
         supabase db push --linked --dry-run --agent no \
         > "$PESO_MIGRATION_DRY_RUN_LOG" 2>&1
   ) && python3 scripts/check_web_mvp_migration_preview.py \
         --workspace "$PESO_MIGRATION_WORKSPACE" \
         --dry-run-log "$PESO_MIGRATION_DRY_RUN_LOG"
   ```

   Run the verifier from the reviewed source checkout. Keep the raw CLI log
   private and record the sanitized result with the cutover evidence. The
   verifier matches local files and recorded CLI output. Independently verify
   target, time, command status, freeze and backup provenance. [Supabase CLI dry run](https://supabase.com/docs/reference/cli/supabase-db-push)
5. Obtain Nathan's separate production apply approval for that exact evidence.
   Immediately recheck the freeze, target, history, config, reviewed migration
   bytes and dry run. Apply only the reviewed linked chain, with seed, role,
   include-all and Vault changes excluded. Keep the freeze through readback.
   Verify all 51 version/name pairs, preserved data and Storage metadata,
   buckets and policies, RPCs, RLS, grants, and the approved Data API behavior.
   Verify effective anonymous, owner, non-owner and service access against the
   approved state using authorized fixtures where applicable. Preserve disabled
   controls until separately approved Auth, media or service activation.

The chain can partially commit. On ambiguous or failed application, keep the
freeze within its approved bounds, retain evidence and read actual history and
data before deciding on a reviewed forward repair or separately approved
recovery. Do not replay blindly, repair history to hide the Azure exclusion or
restore over production as a test. Catalog or history drift requires renewed
review and checks. Use the [historical seven-file packet](pesodatabase-precutover-packet.md)
only for its recorded September scope.
