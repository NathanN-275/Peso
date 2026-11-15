# IP-country source recommendation for Peso public beta

Researched 2026-10-29 using official sources only. Nathan requested a no-new-cost IPv4/IPv6 source for fail-closed US-only admission. The research subtask made no account or hosted changes. The parent subsequently downloaded the public October CSV and validated it in a disposable local fixture; see [the refresh procedure](us-ip-dataset-refresh.md).

## Recommendation and limits

**Recommend DB-IP IP to Country Lite for a best-effort beta country gate**, provided Peso implements attribution and accepts misclassification risk. It offers public monthly downloads without introducing a credential-management dependency. This recommendation is an engineering judgment, not a measured accuracy comparison. If “US-only” means assurance of a person's physical location, neither candidate establishes that: IP geolocation can locate a VPN/proxy server rather than its user, and accuracy varies with network type. Denying unknown results cannot prevent a wrongly assigned `US` result or a US VPN exit from being admitted. [MaxMind limitations](https://support.maxmind.com/knowledge-base/articles/maxmind-geolocation-accuracy)

## DB-IP Lite: evidence and integration implications

- **License and attribution:** CC BY 4.0; DB-IP explicitly requires a DB-IP.com backlink on web pages that *display or use* its results. Admission uses the result, so the conservative interpretation is visible attribution on both admitted and denied pages, including any separate admission screen. Suggested label: `IP Geolocation by DB-IP`. [Official download/terms page](https://db-ip.com/db/download/ip-to-country-lite)
- Also retain source and license notices, link the license, and indicate transformations such as retaining only US ranges. CC BY permits commercial adaptation and redistribution subject to its terms. A source-data notice can say “Country admission data derived from DB-IP IP to Country Lite; transformed to US ranges.” [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **Coverage/quality:** Lite deliberately has fewer records and reduced coverage/accuracy. The download page's “81” accuracy index is an internal index, **not an 81% accuracy guarantee**. Its current table identifies the release as October 1, 2026. [Official download page](https://db-ip.com/db/download/ip-to-country-lite)
- **Cadence:** monthly, usually the first of the month; updates replace the full CSV rather than applying deltas. Lite does not undergo the same QA process as paid data. The FAQ provides no guaranteed release deadline. [DB-IP FAQ](https://db-ip.com/faq.php)
- **CSV:** UTF-8, RFC 4180, three fields: `ip_start`, `ip_end`, ISO 3166-1 alpha-2 `country`. Its documented import schema distinguishes IPv4 and IPv6 and stores 16-byte endpoints. Preserve both families; an IPv4-only transform would deny IPv6 visitors or create a bypass if lookup failures were allowed. [CSV specification](https://db-ip.com/db/format/ip-to-country-lite/csv.html)
- **MMDB:** compatible with MaxMind DB format v2 readers; country decision field is `country.iso_code`. [MMDB schema](https://db-ip.com/db/format/ip-to-country-lite/mmdb.html)

The live official page's links were inspected without following downloads:

- [October 2026 CSV gzip](https://download.db-ip.com/free/dbip-country-lite-2026-10.csv.gz)
- [October 2026 MMDB gzip](https://download.db-ip.com/free/dbip-country-lite-2026-10.mmdb.gz)

Treat the `YYYY-MM` filename as a release identifier; do not infer freshness from filesystem mtime or re-download time. Pin a source release, fetch time, and locally computed SHA-256 in the generated artifact's manifest. The download page advertises MD5/SHA1, which should not be presented as a modern authenticity guarantee.

## Freshness and fail-closed policy

**Suggested policy, not a vendor promise:** reject a DB-IP artifact older than **35 days from its source release date**, reject future/invalid dates, and refresh promptly after monthly publication. Thirty-five days accommodates a 31-day month plus a short update window; failure to publish or ingest an update must eventually stop admission. For the inspected `2026-10-01` release, a strict `age < 35 days` policy expires at `2026-11-05T00:00:00Z` when the manifest normalizes the release date to UTC midnight. This deliberately chosen convention is not a vendor-supplied timestamp. A stricter cutoff is possible at the expense of more downtime.

Enforce expiry during requests as well as startup, so an already running server cannot outlive the bound. Missing/corrupt/expired data, invalid or nonpublic addresses, unsupported families, and no country match must deny. Only an unambiguous `US` result from fresh, validated data should admit. Record this as an upper bound on artifact age, **not** an upper bound on location-error duration or a guarantee that assignments were correct on publication.

## MaxMind GeoLite Country alternative

- Free downloadable MMDB and CSV; account signup and a generated license key are required for authenticated acquisition. GeoLite downloads are limited to 30/day. IPv4 and IPv6 country lookup are supported. [GeoLite integration](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data/), [database documentation](https://dev.maxmind.com/geoip/docs/databases/)
- Country updates currently publish Tuesdays and Fridays, as complete replacements. More frequent publication reduces potential source age; it does not prove greater accuracy for Peso's users. [Update schedule](https://support.maxmind.com/knowledge-base/articles/download-and-update-maxmind-databases)
- The February 12, 2026 EULA requires attribution, incorporates CC BY-SA 4.0 plus other policies, disclaims accuracy guarantees, requires prompt updates, and requires stopping use and destroying old versions within 30 days after an updated release. Derived data, packaged artifacts, rollback copies, and retention policy need attention; freezing a downloaded release indefinitely is unsuitable. There are also restrictions concerning disclosures and prohibited FCRA uses. [Current GeoLite EULA](https://www.maxmind.com/en/geolite/eula)
- Its public positioning recommends paid GeoIP when geoblocking accuracy is critical. Do not repeat paid-product accuracy claims as a GeoLite guarantee. [Official GeoLite comparison](https://www.maxmind.com/en/geolite-free-ip-geolocation-data)

GeoLite Country is credible if Nathan prefers twice-weekly updates and is willing to own signup, secret storage, attribution, EULA obligations, and old-data destruction. It is not a drop-in credential-free acquisition path. Review its exact use and redistribution terms before selecting it; this research note is not legal advice.
