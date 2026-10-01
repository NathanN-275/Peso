# Storage policy recovery: local rehearsal, September 28, 2026 UTC

Local PostgreSQL access checks passed using synthetic data. Hosted recovery is
still unverified; keep `managed_schema_customizations_verified=false` in the
pre-cutover observations until the separate hosted test passes.

## Restore artifact

`supabase/recovery/restore_pre_cutover_storage_policies.sql` contains the eight
`CREATE POLICY` statements from the verified September 23 private managed-schema
export. A direct comparison of those statements produced no differences. There
are four authenticated policies (SELECT/INSERT/UPDATE/DELETE) each for `videos`
and `profile-avatars`. User-ID folders determine ownership; `owner_id` metadata
does not grant access. Video INSERT and UPDATE additionally restrict extensions
to lowercase `mp4`, `mov`, `m4v`, or `webm`.

This is **pre-cutover recovery SQL**, outside the migration directory. It does
not replace managed schemas, change grants, disable RLS, drop existing policies,
or affect migration history. It requires RLS already enabled and no existing
`storage.objects` policies, then creates all eight in one transaction. Missing
acknowledgement, disabled RLS, existing policies, or any SQL error aborts the
restore. It deliberately refuses reruns rather than overwriting unknown state.

The session acknowledgement is an operator guard, not project authentication:
verify the isolated target's actual identity before setting it. Never run this
file on PesoDatabase or staging as a test. Never restore these pre-cutover direct
upload/update/delete policies after `supabase/security-cutover.sql` has removed
them: doing so would reopen client writes.

## Reproduce the local checks

With the existing `postgres:17` image available locally:

```sh
python3 scripts/rehearse_storage_policy_recovery.py
```

The runner creates its own uniquely identified Docker container with no network,
published ports, host mounts, or real credentials. PostgreSQL data lives in
temporary memory-backed storage. It accepts no hosted database URL or backup
file. All commands use `docker exec` against the returned container ID; cleanup
removes only that container and its synthetic data in a `finally` block.

The fixture implements only the necessary object columns and the three helper
functions from the schema export (`auth.uid`, `storage.foldername`, and
`storage.extension`). Real Postgres roles/RLS enforce access; owner and other-user
identities are synthetic session claims. The restored policies run as
`authenticated`/`anon`, not the administrative table owner.

The checks cover explicit acknowledgement; enabled RLS; empty-policy precondition;
transaction rollback after a mid-restore failure; eight authenticated policies;
owner read/insert/update/delete in both buckets; non-owner, missing-subject, and
anonymous denial; rejected moves to another owner's path or another bucket;
allowed video extensions; executable/uppercase extension rejection; root-path
rejection; spoofed ownership metadata; private export-bucket denial; and the
expected service-role bypass. The local container and synthetic data are removed
after the run, including on test failure.

## Remaining hosted gate

The local fixture does not include the platform's full Storage schema, triggers,
bucket MIME/size enforcement, JWT validation, PostgREST, or object bytes. It does
not establish hosted database privileges or successful Storage API access.

In a separately approved disposable hosted project, restore the backup and this
reviewed policy subset, compare policy definitions/roles/RLS with the source, and
test actual owner/non-owner Storage API access using private synthetic objects.
Verify bucket privacy and MIME/size limits as well. Keep public launch, paid
Render resumption, production migration and rebinding outside that test. Do not
reuse the completed September 24 staging-pause approval for a new pause.
