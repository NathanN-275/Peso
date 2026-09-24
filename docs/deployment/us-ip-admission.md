# US-IP beta admission

Prepared locally; hosted enforcement is not active. This implements geographic
network admission, not residency or age verification. VPNs, proxies and IP
database errors affect classification.

## Controls

`20260922003008_us_ip_beta_admission.sql` creates an RLS-protected table of US
CIDR ranges with a source version and expiry. Only current ranges are accepted.
The table has no browser-role access. The `is_us_beta_ip` function is callable
by the service role and Supabase Auth; only Supabase Auth may invoke the signup
hook. The hook checks Auth's authoritative `metadata.ip_address`, never
user-supplied profile metadata. Missing, malformed or expired data denies signup.
See Supabase's [before-user-created hook documentation](https://supabase.com/docs/guides/auth/auth-hooks/before-user-created-hook).

When `US_IP_BETA_ENABLED=true`, the API checks new reservation and legacy video
creation requests. It resolves the transport peer, trusting forwarding headers
only across explicitly configured `TRUSTED_PROXY_CIDRS`, from right to left.
Duplicate, missing or malformed trusted chains fail closed. An untrusted caller
cannot override its address through `X-Forwarded-For` or `CF-IPCountry`.
The Docker entrypoint disables Uvicorn proxy rewriting so this code receives the
original transport peer. Do not override this with a provider start command
that rewrites the peer first.

Accepted reservation completion and analysis continue; history, deletion and
saved content are unaffected by a later location change. The feature defaults
off until its operational dependencies are ready.

## Required before activation

1. Use Nathan's selected PesoDatabase (`jfgiydtrskpqxyorvvbc`). Rehearse and review
   the migration and restore procedure before any hosted production application.
2. Select a licensed authoritative IPv4/IPv6 geography source, record its version,
   coverage and freshness policy, and implement a validated atomic refresh.
   Alert before expiry; missing data must not silently relax enforcement. No real
   geography dataset or refresh pipeline has been installed. Test fixture CIDRs
   are documentation-only addresses and must never be loaded as production data.
3. Verify hook availability on the actual Supabase plan, configure the SQL hook,
   and test direct Auth API signup from approved US and non-US test clients.
4. Obtain the provider's actual incoming proxy trust contract. Outbound IP ranges
   are not incoming proxy ranges. Capture transport/header evidence with synthetic
   requests and verify the final start command before setting trusted CIDRs.
   Never trust `0.0.0.0/0`, `::/0` or an unverified client-provided country header.
5. Complete reservation-only storage admission cutover so direct client storage
   writes cannot bypass admission. Verify RLS and real two-user isolation.
6. Enable API enforcement only on the private candidate with fresh data and the
   Auth hook. Test IPv4, IPv6, proxy spoofing, direct signup, denied new uploads,
   accepted upload completion and clear user messages before launch review.

## Local evidence and recovery

Unit tests cover address resolution, header spoofing, fail-closed lookup and
route protection. Disposable PostgreSQL tests cover hook denial, expiry,
metadata spoofing and role grants. These tests do not establish actual Render
forwarding behavior, geographic accuracy or hosted signup enforcement.

If data expires or the hook becomes unavailable, stop new admission and restore
the reviewed dataset/configuration. Keep accepted jobs draining. Do not disable
geographic controls to reopen a publicly accessible beta without a separately
reviewed change. No hosted migration, hook or proxy setting has been changed.
