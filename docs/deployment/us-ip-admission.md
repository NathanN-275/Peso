# US-IP beta admission

Production signup enforcement is pending. The staging Auth hook is configured,
with signup disabled pending managed testing. IP location does not establish
residency or age. VPNs, proxies and IP
database errors affect classification.

## Controls

`20260922003008_us_ip_beta_admission.sql` creates an RLS-protected table of US
CIDR ranges with a source version and expiry. Only current ranges are accepted.
Successor `20261029020225_us_ip_expiry_wall_clock.sql` requires a finite expiry
strictly after the current database wall clock. The lookup is VOLATILE, uses
qualified objects and an empty search path, and remains SECURITY INVOKER. A
transaction begun before expiry cannot extend admission using its old `now()`;
positive/negative infinity and unknown addresses deny. Existing indefinite rows
will deny after this migration and must be replaced by reviewed finite data.
Lookup success before expiry does not revoke an already accepted operation.
See PostgreSQL's [clock semantics](https://www.postgresql.org/docs/17/functions-datetime.html#FUNCTIONS-DATETIME-CURRENT)
and [volatility rules](https://www.postgresql.org/docs/17/xfunc-volatility.html).

Successor `20261030201615_auth_signup_hook_schema_access.sql` grants only schema
USAGE on `public` to `supabase_auth_admin`, making hook resolution independent of
Studio's setup grants after restore. It grants no schema CREATE, table mutation
or new function access and does not broaden browser roles. A dedicated PostgreSQL
fixture starts without inherited or direct Auth schema USAGE, demonstrates the
predecessor hook invocation failure, then verifies allowed/denied signup and ACLs
with the successor. PesoDatabase's October 30 read-only privilege check already
showed this schema permission; this is a self-contained migration/restore
prerequisite, not evidence of a current hosted permission failure.

The table has no browser-role access. The `is_us_beta_ip` function is callable
by the service role and Supabase Auth; only Supabase Auth may invoke the signup
hook. The hook checks Auth's authoritative `metadata.ip_address`, never
user-supplied profile metadata. Missing, malformed or expired data denies signup.
See Supabase's [before-user-created hook documentation](https://supabase.com/docs/guides/auth/auth-hooks/before-user-created-hook).

The November 11 scope decision applies the check at signup. Signed-in users may
upload while abroad. Authentication, ownership, reservation limits and budget
controls continue to govern uploads. See [ADR 0021](../adr/0021-scope-us-ip-signup-and-replace-render-pair.md).

## Required before activation

1. Use Nathan's selected PesoDatabase (`jfgiydtrskpqxyorvvbc`). Rehearse and review
   the migration and restore procedure before any hosted production application.
2. The prepared loader selects DB-IP Country Lite, with documented reduced
   coverage/accuracy and CC BY 4.0 attribution requirements. Follow the
   [source and refresh procedure](us-ip-dataset-refresh.md), add visible DB-IP
   attribution to all web pages using admission results, and verify alert delivery
   before activating the gated daily job. The November release is loaded and
   verified on staging. Production data and the scheduled refresh are pending.
   Test fixture CIDRs remain
   documentation-only and must never be loaded as production data.
3. The current [Auth Hooks overview](https://supabase.com/docs/guides/auth/auth-hooks)
   lists Before User Created on Free and Pro. Confirm the selected project's UI,
   configure the SQL hook only after rehearsal, and test direct Auth API signup
   from approved US and non-US test clients, including spoofed forwarding headers.
   The documented JSONB event uses `metadata.name=before-user-created` and
   `metadata.ip_address`; success is `{}`, rejection uses `error.http_code` and
   `error.message`. The staging dashboard and SQL configuration have been verified. Managed
   invocation and gateway IP authenticity still require a controlled test.
   Postgres hooks have a documented two-second timeout; rehearse with actual
   dataset cardinality and deployed roles.
4. Verify reservation-only upload, RLS, and two-user isolation on the private
   candidate. Test a signed-in upload from abroad using the normal upload flow.

## Local evidence and recovery

Disposable PostgreSQL tests cover hook denial, expiry,
metadata spoofing and role grants. They also exercise fresh/expired/indefinite
IPv4/IPv6 ranges, null/unknown addresses, finite expiry inside the same live
transaction through both internal roles and the real signup hook, and the
lookup's volatility/empty search path/non-definer/denied browser grants. All
addresses are documentation-only synthetic fixtures. Hosted signup enforcement and geographic accuracy require separate evidence.

If data expires or the hook becomes unavailable, stop new admission and restore
the reviewed dataset/configuration. Keep accepted jobs draining. Do not disable
geographic controls to reopen a publicly accessible beta without a separately
reviewed change.
