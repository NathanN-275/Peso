# Gate 1: source checkpoint — September 30, 2026

**Result: local source checks PASS. Production release acceptance remains open.**
Nathan approved verifying source in Gate 1 and retaining the real production
release build in Gate 11. This checkpoint does not approve deployment or launch.

## Source reconciliation

Branch: `feat/combined-public-beta`; draft [PR #47](https://github.com/NathanN-275/Peso/pull/47)
targets `main`. GitHub was reachable with network permission; the earlier
sandbox connection failure was not evidence of invalid authentication.

At inspection, remote PR head was `61a669ad2948b260159b91808ce7d5f4ffca4431`;
local source was `d05a0d1603e65a5af68ea5432083c1ba94b12f4f`, three commits ahead.
Those commits contain the local Storage-policy rehearsal and recovery evidence.
Nathan authorized reconciling the six working documentation changes with the
current approved plan while preserving the recovery note. This evidence commit
is the Gate 1 checkpoint; obtain its immutable SHA from Git after committing.
Later implementation changes must receive applicable checks on their new SHA.

## Verification

No application, test, dependency or migration code changed after these checks:

| Check | Result |
| --- | --- |
| Policy tests | 222 passed in the preceding Gate 1 attempt |
| App and dashboard typechecks | Passed in the preceding Gate 1 attempt |
| Dashboard build | Passed in the preceding Gate 1 attempt |
| Backend pytest | 510 passed, 19 skipped, 70 subtests passed in the preceding attempt |
| Static migration/RLS audit | Passed in the preceding Gate 1 attempt |
| Dashboard tests | 17 passed, 4 files |
| Pre-cutover checker tests | 26 passed |
| Local combined web build | Passed with explicit fixture settings and EXPO_NO_DOTENV=1 |
| Web budget | 520,865 gzip JS bytes / 614,400 limit; 58,224 WOFF2 bytes / 204,800 limit |
| Git whitespace check | Passed |

The local web build used `example.supabase.co`, `example.com`, `api.example.com`,
a dummy publishable key and Cloudflare's public test site key. No production
validation or hosted behavior is claimed. Never publish this fixture output;
Gate 11 must rebuild with the verified production binding and real settings.

## Remaining gates

The combined release binding remains pending. The public-beta validator correctly
requires its verified site, API, source and service identities. The earlier
release-build attempt failed before compilation because required shell values
were missing; release-env.js does not automatically load the root dotenv file.
Existing local dotenv entries are not proof of production release configuration.

PR #47's September 28 container-security, frontend/backend security, database
security, secret scan, marketing build, and Render validation checks passed on
the old remote head. These supersede historical failing-container evidence but
do not certify this new checkpoint or a deployed runtime. Fresh PR checks after
sync must be evaluated before release. Backend skips and the static SQL audit
do not prove hosted migration or two-user access acceptance.

Next: Gate 2 must verify current container evidence for the candidate. No
credential rotation, provider reconfiguration, hosted migration, service
resumption, or public launch was performed in Gate 1.
