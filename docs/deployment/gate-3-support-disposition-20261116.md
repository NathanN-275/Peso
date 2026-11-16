# Gate 3: GitHub Support disposition — November 16, 2026

## Evidence and conclusion

Nathan supplied the October 8, 2026, 23:42 UTC response from GitHub Support
for ticket #4813900 in this chat on November 16. The private ticket was not
independently accessed. Support recommends revocation/rotation as the primary
remedy and says history removal is generally unnecessary once access is
revoked. It does not confirm that any GitHub object or cached view was removed.

The public [GitHub guidance](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
was independently checked November 16: revocation/rotation may sufficiently
mitigate an exposed credential, and Support assists with removal where that
mitigation is insufficient. This is consistent with the supplied response.

The September 13 [provider verification](production-security-verification.md#gitguardian-remediation-follow-up--2026-09-13)
records deletion of the exposed, unused New Relic license key without creating
a replacement, provider confirmation and an account key count decrease of one.
That existing revocation evidence and the supplied Support disposition resolve
the history-removal subitem for that key. No purge or fresh New Relic provider
inspection is claimed. Existing historical copies may remain, and revocation
is the access-control remedy. No branch recreation, force push, rewrite or
scanner exception is needed for this disposition.

## Remaining Gate 3 work

Gate 3 remains open for remaining credential disposition and provider/consumer
verification. Retired Student/Azure credentials need an inventory and verified
retirement or rotation where still used; do not revive Azure infrastructure to
satisfy historical test wording. Current Render/Supabase and operational
credentials still need their applicable purpose, scope and binding checks.

PR #52's earlier code checkpoint passed GitGuardian and repository secret scans;
that does not prove credential revocation. Recheck scanners on the final source.
This disposition applies to the documented New Relic credential only. New
exposures or data whose risk cannot be mitigated by revocation need their own
remediation review. No credentials or provider settings changed in this update.
