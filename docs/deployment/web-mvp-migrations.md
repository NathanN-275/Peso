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

Before application, independently verify the actual target and current hosted
history, require a linked dry run to show exactly the selected pending files,
and rehearse the chain against an approved restored target with the required
Auth, Storage, RLS, queue and budget checks. Preserve the writer freeze, verified
recovery point and action-time confirmation for destructive application. Never
mark the Azure migration applied or create replacement history to hide its
exclusion. Any catalog or hosted-history change requires a reviewed manifest
update and renewed applicable checks.

The older `check_pesodatabase_precutover.py` retains its historical 28-file gate.
Its tests now build that explicit old fixture and verify that later migrations
block it. Those historical passing cases do not accept the current MVP chain.
