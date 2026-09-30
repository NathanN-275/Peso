# Public Web Beta Deployment Plan

Approved by Nathan in this chat on September 30, 2026. This replaces the older
plan's dependency on an unavailable source PDF. Target: the combined homepage
and authenticated `/app`, US-only signup/upload admission, and side-view squats.

## Execution contract

Complete one gate per chunk. Stop after every gate and report: **TL;DR: what
changed; why; verification; next blocker.** Do not advance after a failed gate.
Keep credentials and backup contents outside Git. Record only sanitized
evidence and exact release identifiers. Preserve existing data and projects.
Commit messages include summary, what changed, why, affected systems, and tests.

## Gates

1. **Freeze candidate:** reconcile working changes and PR #47, select a source
   SHA, run policy/type/backend tests, local builds with explicit non-production
   fixtures and migration audits. Production-build acceptance remains mandatory
   in Gate 11, as Nathan confirmed on September 30.
2. **Container security:** scan the exact candidate and run offline runtime and
   dependency checks. Change dependencies only for current failures; September
   28 PR checks passed and supersede the historical failing scan.
3. **Credential history:** finish rotation, provider verification and GitHub
   history-purge work; verify secret scans.
4. **Staging authentication:** isolated test users, redirects, email, Turnstile,
   browser and required native authentication tests.
5. **Hosted recovery:** approved disposable target, logical restore, custom
   Storage policies, real owner/non-owner access and object-byte verification.
6. **Fresh recovery point:** verified writer freeze, private export, checksums,
   Storage inventory/bytes and verified protected off-machine copy.
7. **Production migrations:** review current dry run, apply reviewed chain,
   verify history, RPCs, RLS, grants and Data API behavior.
8. **US admission:** authoritative geography source and refresh, Auth hook,
   verified incoming proxy trust, IPv4/IPv6 and spoof/expiry failure tests.
9. **Guardrails:** retention/cleanup, budget alerts and intake stop, delivery,
   accepted-job draining, quotas and monitoring acceptance.
10. **Render cutover:** reviewed existing IDs and matching production credentials,
    manual deployment, separately approved paid resumption, API readiness then
    worker acceptance and two longest-clip measurements.
11. **Private Web App:** combined Netlify project, verified binding and production
    configuration, release build/budget, preview and historical URL privacy.
12. **End-to-end acceptance:** two owners; upload through analysis, save, export,
    deletion, recovery and mobile compatibility; isolation and expired sessions.
13. **Protected release:** one main-to-production PR, required checks on the
    release SHA, recorded frontend/backend/migration/model identifiers.
14. **Public launch:** final costs, identities and rollback evidence; Nathan's
    action-time confirmation; public smoke tests and first-cycle monitoring.

## Source checkpoint and production acceptance

`PESO_RELEASE_ENV=public-beta` requires the private candidate binding that Gate
11 creates. Nathan approved separating Gate 1 source verification from Gate 11
hosted release-build acceptance on September 30. Gate 1 uses a local fixture
build with dotenv loading disabled; that output must never be deployed. Gate 11
must run production release validation and build/budget checks with the real
verified binding. Never bypass the validator or invent provider evidence.

A source SHA can identify a tested checkpoint; subsequent implementation gates
create new SHAs that require fresh applicable checks before release. Gate 1
cannot freeze the final release bytes before those changes exist.

## Completion

All mandatory PRR gates pass, no blocking security finding remains, production
bindings agree, US admission fails closed, two-user acceptance and recovery pass,
and Nathan authorizes public exposure. Local checks alone do not prove this.
