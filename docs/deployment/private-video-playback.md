# Private video playback

Source preparation only. All private-media flags remain off. This does not enable
hosted media or complete the launch gates.

Remote analysis review and Saved Lift playback now use `useVideoPlayback`.
Native and web review routes fetch analysis metadata first and leave byte-session
issuance to the mounted reader. Failure to load a clip leaves the review metadata
and Save/Discard actions available. Upload review retains a device-local source;
private mode accepts only file/content/blob sources there, and a local source is
bound to the accepted session and media epoch at first observation.

When enabled, the issuer sends the captured account Bearer only to the configured
public HTTPS backend's fixed media-session POST. It validates the complete bounded
response, exact resource and asset URL map, canonical media credential and expiry.
Browser transport uses the verified session namespace, credentials include,
no-store and keepalive false; the response must contain all six existing video
assets and no JavaScript media credential. Native transport requests playback only,
uses the media-grant header for video bytes and explicitly disables Expo caching.
No query credential, provider URL, account-Bearer byte request or raw fallback is
supported. The old client playback-URL adapters reject calls in private mode.

Issuance has a 30-second header/body deadline independent of whether the transport
honors abort, an 8192-byte JSON bound and session/epoch/backend checks before and
after asynchronous work. Session release aborts pending issuers. Retained source
leases independently reject use after expiry or a context change. Local abort does
not prove physical cookie erasure or browser/network drain.

Each opened remote clip permits one automatic renewal, triggered by expiry or a
player error. Subsequent failure or expiry requires Retry playback. Issuance
failures immediately offer Retry; there is no background retry loop or persisted
credential cache. Native source replacements are serialized per player; release
waits for an in-flight replacement and its final clear before acknowledging. A
failed decoder clear blocks acknowledgement. Unmount retains the release callback
until an unfinished replacement and its queued clear have settled. Ordinary component cleanup remains
best effort because Expo owns final player disposal on unmount.

Both actual web video elements use crossOrigin use-credentials before a private
source is attached. The HTML Saved Lift player remounts for a new lease even when
the cookie URL is unchanged. Review's Expo player uses explicit serialized source
replacement for that same case. Renewal pauses playback and attempts to retain
its position without resetting review forms or overlays. Real player event timing,
seek restoration and cache behavior still need device/browser acceptance.

## Verification and limits

Deterministic tests execute the actual Peso issuer, React hook and player-lifecycle
modules with synthetic transport/player/React scheduling. They do not import or
probe an Auth SDK, contact providers, establish actual CORS/Secure/SameSite cookie
behavior, or establish native decoder/HTTP-cache absence. TypeScript and a local
synthetic combined build are separate checks. No installed dependency was changed.
The current Expo documentation is SDK58; the repository remains on installed
expo-video57.0.2, whose source and types were checked directly for headers,
useCaching, crossOrigin forwarding and explicit replacement behavior.

Primary references checked November 3, 2026:

- [Expo Video](https://docs.expo.dev/versions/latest/sdk/video/)
- [HTML media CORS setting](https://html.spec.whatwg.org/multipage/media.html#attr-media-crossorigin)

Thumbnail consumers now use the bounded memory reader described in
[private-video-thumbnails.md](private-video-thumbnails.md). Analyzed exports and
archive downloads still need their actual consumer/issuer migrations and bounded
download contract. Old server URL issuers
and historical capabilities still need retirement. Same-site custom application
and API origins, hosted SQL/provider policy, two-owner current-browser/native
acceptance, deletion/orphan/backup settlement and all other launch gates remain
required. The historical avatar normalizer failure remains unexplained.
