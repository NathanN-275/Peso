# Intake stop and manual recovery

Implementation prepared; production activation and monitoring are not verified.
Nathan approved PesoDatabase (`jfgiydtrskpqxyorvvbc`), a $50 monthly budget,
a $50 projected monthly spend intake stop, and actual monthly spend notifications
at $15, $25, $35 and $50 on September 22, 2026. No public launch, paid service
resumption or capacity increase is authorized by these preferences.

## Measurements and behavior

An authorized monitor can POST to `/internal/budget-admission/evaluate` with
`X-Budget-Token` taken from its secret store, never a URL or browser bundle.
The token is the backend's `BUDGET_SHUTDOWN_TOKEN`. JSON body:

```json
{
  "observed_at": "2026-09-22T00:00:00Z",
  "actual_monthly_usd": "15.00",
  "projected_monthly_usd": "35.00",
  "storage_used_bytes": 123456
}
```

The timestamp above is illustrative; a real measurement must be at most five
minutes old and cannot be more than 30 seconds in the future. Negative,
non-finite, timezone-free and malformed measurements are rejected. Collect the
projected **total** monthly spend from provider billing/forecast data, including
compute, storage, transfer, email, monitoring, backups and applicable taxes.
Do not infer a forecast from suspended-service month-to-date billing. If any
provider value is missing or stale, report monitoring failure rather than
substituting zero. `storage_used_bytes` must be measured across the applicable
storage inventory, using complete paginated results.

`INTAKE_STOP_PROJECTED_MONTHLY_USD` must contain Nathan's reviewed integer dollar
threshold (1–50); blank configuration returns 503. The example environment leaves
it at Nathan's approved $50 value. Actual spend and projected spend are separate
required measurements. The response lists reached actual-spend milestones in
`actual_spend_milestones_usd` ($15, $25, $35, $50); this is **not** a notification
delivery receipt. A sample
at or above the selected stop, or at/above the configured storage block ratio
(currently 95% of configured storage quota), disables new admission durably.
The API logs `intake_stop` events without credentials.
Healthy samples never enable admission; `stop_triggered=false` is not evidence
that intake is currently open.

The existing `/internal/budget-admission/disable` remains the immediate manual
stop and can also receive verified resource-pressure alerts. It does not depend
on a spend measurement. OOM/disk-pressure integration still requires reviewed
provider alert wiring. Both endpoints require the budget token.

The database stop shares a transaction lock with upload admission. Once it
commits, new reservations fail with 503 without creating rows or upload URLs.
Already accepted reservations can finish upload/verification and queue their
analysis; existing jobs are not cancelled. Keep workers running while draining
accepted jobs. Never implement an intake stop by suspending the worker or
setting `UPLOAD_RESERVATIONS_ENABLED=false`, which may affect completion paths.

## Operator deployment checklist

1. Confirm the intended API/database identities, migration history and Nathan's
   chosen spend threshold. Apply the reviewed intake-reason migration only after
   the reservation migration and approved staging rehearsal.
2. Configure a non-browser budget token and the reviewed threshold. Do not print
   either credentials or complete authenticated request payloads in logs.
3. Wire a trusted monitor to actual monthly billing, current billing forecasts and measured storage,
   send samples within the five-minute freshness window, and alert the operator
   on missing measurements, non-2xx responses, stale samples and stop events.
   Verify provider billing delay; a recent timestamp cannot make stale billing
   current. Persist notification delivery per billing month and milestone, retry
   failures, and notify for every newly reached threshold if a sample crosses
   several at once. Reset milestone state only for a new billing month. Never
   mark delivery successful from this endpoint response alone. This repository
   does not yet supply that provider collector or notification delivery adapter.
4. In isolated staging, accept one test upload, trip the stop, confirm a new
   upload fails clearly, then finish the accepted upload through actual worker
   playback. Confirm no rejected-request reservation exists. This live test is
   still required; database tests alone do not prove storage/worker completion.
5. Record the tested collector identity, schedule, threshold, notification
   destination and exact release candidate in the release manifest.

## Manual resume

Read `enabled`, `disabled_reason` and `updated_at` from the singleton
`public.upload_admission_control` row. Resolve the pressure condition, review
current spending and accepted-job backlog, and obtain Nathan's approval if
resuming increases capacity or expected spend. Keep the workers running.

Under the same `peso:upload-capacity` transaction advisory lock, update the row
to `enabled=true`, `disabled_reason=null`, `updated_at=now()` **only if** its
`updated_at` still equals the exact stopped timestamp reviewed by the operator.
If no row is updated, a newer stop occurred; reassess rather than overwrite it.
Commit, inspect the row, and run one approved staging/production smoke upload
as appropriate. Do not automate this reset or repeatedly fight a stopping
monitor. Any subsequent pressure sample is allowed to stop intake again.

An intake stop is not a provider spending cap: accepted work, provisioned
compute, stored data, egress and billing delay can keep accruing charges. The
$50 target is not guaranteed by this switch.

## Verification recorded

- Eight measurement/configuration tests cover alert versus stop, exact boundaries, stale and
  future samples, invalid numbers, missing threshold, token rejection, persistent
  stop behavior and database failure propagation.
- Focused intake/reservation/cleanup suite: 55 passed, 21 subtests passed.
- Seventeen disposable PostgreSQL tests passed, including preserving accepted
  upload verification/queue admission, stop/admission locking, capacity limits,
  retention races and client-role access denial.
- Hosted activation, collector scheduling, billing accuracy, notification
  delivery and full accepted-job completion remain open release gates.
