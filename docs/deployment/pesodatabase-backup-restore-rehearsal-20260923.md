# PesoDatabase backup and local restore rehearsal — September 23, 2026

**Result: the private logical backup restored successfully into a network-isolated
local Supabase Postgres 17 instance.** No hosted schema or service was changed.
The [migration-chain review](pesodatabase-migration-chain-review-20260923.md)
remains blocked for hosted application until the seven-file chain and cutover
are rehearsed and reviewed.

## Backup

The source was the linked **PesoDatabase** project
`jfgiydtrskpqxyorvvbc`, not staging. Supabase's Free Plan offers no managed
project backup. The CLI exported six SQL files to the private, non-repository
folder `/Users/nathan/Downloads/peso-private-backups/2026-09-23-pesodatabase-pre-migration`:

| File | Contents |
| --- | --- |
| `roles.sql` | Custom role and role settings |
| `schema.sql` | Application schema, functions, grants, and RLS |
| `auth_storage_schema.sql` | Current managed Auth and Storage schema needed to match the platform version in this local rehearsal |
| `data.sql` | Database rows, including the Auth user and Storage bucket metadata |
| `history_schema.sql`, `history_data.sql` | Supabase CLI migration history |

The directory is mode `0700`; each SQL file and `SHA256SUMS` is mode `0600`.
`shasum -a 256 -c SHA256SUMS` passed for all six exports. These files contain
private account data and must remain outside Git, chat, PRs, and shared logs.
There were no `storage.objects` rows at export time, so there were no object
bytes to copy. A later pre-cutover check must repeat that inventory and copy
any objects separately. This is one local copy, not an off-device disaster
recovery backup.

## Restore rehearsal and checks

The CLI's disposable local Supabase database ran on Postgres 17.6. Docker
network attachment was removed before loading private data; its published
port was unreachable, while `docker exec` still allowed local administration.
The standard local Auth schema was older than PesoDatabase: a first
transactional data import rejected a missing Auth column and rolled back.
After replacing **only the disposable target's** Auth and Storage schemas
with `auth_storage_schema.sql`, all backup files restored successfully. The
role file required the local `supabase_admin` superuser rather than the local
`postgres` role. Data was imported in one transaction with
`session_replication_role = replica`, following
[Supabase's CLI restore guidance](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore).

Read-only comparisons of source and restored target matched:

| Check | Source and restored result |
| --- | --- |
| Auth users; profiles; videos; analysis jobs | `1; 1; 0; 0` |
| Storage buckets; objects | `3; 0`; all buckets private |
| Migration history | 21 entries, latest `202608270001` |
| Public table ownership/RLS flags | Same digest; all five public tables have RLS |
| Public and Storage policy definitions | Same 14-policy digest under the same `search_path` |
| Role access to restored profile | Unaffiliated `authenticated`: 0 rows; `service_role`: 1 row |

The local restore is evidence that these exports are internally usable; it
does not prove a managed Supabase project can be restored automatically, that
project settings or credentials are backed up, or that storage bytes would be
recovered if objects are created later. Restore procedures for a hosted
replacement still need a separate rehearsal before treating this copy as a
complete disaster recovery plan. The disposable local database and its data
volume were removed after verification.

**Next release gate:** rehearse the exact seven pending migrations and
compatible API/worker cutover against an isolated copy, then recheck the live
backup, queue, and Storage inventory immediately before any hosted change.
Keep Render suspended and the hourly budget workflow disabled until their
separate private tests pass.
