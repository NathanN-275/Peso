# Host public marketing in a separate Netlify project

Accepted September 20, 2026. Publish the information-only site in a dedicated
`peso-marketing` project in the existing Free Netlify team, using the same
repository and protected `production` branch. Keep `peso-webapp`, its staging
branch, previews, and all historical app-containing deploys private: changing
visibility on the existing project would expose its production history.

The marketing package is `web`, its base is the repository root, and its own
`web/netlify.toml` runs only the marketing build and artifact verifier in every
context. It has no app rewrite, authentication setup, backend variables,
functions, or forms. Only the exact app project ID on the `main` branch-deploy
context can use the private-beta dispatcher. App production builds are skipped.

Production Render deployment remains manual until a separately reviewed beta
release. Move apex and www only after private hosted acceptance and passing
protected release checks. Obtain Nathan's action-time confirmation before
making marketing production public; keep previews private and immediately
restore Private on isolation failure. Never publicly roll back to app content.
No upgrades or authentication-origin changes are part of this launch.


Implementation checkpoint, September 21, 2026: marketing project
`19cbad85-dd2d-4d3b-a24a-242de78d30af` privately published deploy
`6ab17428436e50000838783f` at `d92dfea5334d338cf7af842f0d1b3672ca3d1cc9`.
App project `230da8eb-f00e-45d4-ba54-95f2e26f21c4` remains Private. Domain
assignment is still on the app project while Cloudflare sign-in and remaining
private response/network acceptance are pending. No rollback was needed; no
public exposure is authorized yet. See the [release evidence](../deployment/marketing-release-20260920.md)
for the measured usage, DNS/TLS baseline and unchanged Render identity.
