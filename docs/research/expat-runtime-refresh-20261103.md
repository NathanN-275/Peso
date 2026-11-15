# Expat runtime refresh — November 3, 2026

The exact browser-session candidate scan using the November3 Trivy database found
CVE-2026-113351 (MEDIUM) and CVE-2026-115506 (UNKNOWN) in Wolfi libexpat1 2.9.0-r0.
Both concern XML parser denial of service; this record does not claim the app
exposes an affected XML parser or demonstrate exploitability. They were absent
from the earlier scan database, so earlier zero reports remain historical evidence.

The [parser reset fix](https://github.com/libexpat/libexpat/pull/1431) and
[early amplification detection fix](https://github.com/libexpat/libexpat/pull/1433)
are merged upstream. [Expat2.10.0](https://github.com/libexpat/libexpat/releases/tag/R_2_10_0)
was released November2. The official [Wolfi APK index](https://packages.wolfi.dev/os/x86_64/APKINDEX.tar.gz)
lists libexpat1=2.10.0-r0 for x86_64, built from Wolfi source
f5ef816d1cb2bd0e165a402c4e8a4c4622464bf3. Pin that exact runtime package in the
existing signed apk install command. Keep the base digest, FFmpeg package pin,
Python tooling removal, resource limits and security thresholds unchanged.

The original full report, fixed package index entry, raw index hash and separate
image build/test/runtime/source-binding/scan results live in the persistent
browser-media-session-protocol-20261102 evidence workspace and its sealed packet.
A successful package install or version string alone does not prove the candidate
runtime or vulnerability gate. Final acceptance requires the exact rebuilt image
and complete matching scan and regression evidence. No HIGH exception, scanner
filter, advisory downgrade or reachability exemption is introduced.
