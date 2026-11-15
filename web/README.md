# Static marketing pages

`build.mjs` renders the five fixed HTML templates in `src/pages/`, composes the
shared layout/header/footer, and emits local content-hashed assets beneath
`marketing-assets/`. The only package inputs are the existing @fontsource
Archivo Black and Inter 5.3.0 font resources. Font license text is emitted with
the assets. The renderer has no remote asset fetch or third-party code import.

## Candidate status

The integrated lockfile contains only the root and the two reviewed font
packages, matching the manifest. October 25 candidate checks passed a fresh
scripts-disabled web install, complete zero-finding web audit, all 40 planned
renderer/adapted regressions, and the real guarded marketing build/artifact
verifier. The renderer emits five routes; marketing mode removes authentication
assets and verifies the four information pages with forced app/auth redirects.
The root dependency audit, candidate Linux/container security, real production
binding, combined release artifact and hosted/browser acceptance remain separate
launch requirements. This local marketing artifact is not an accepted public
Web Beta release.

## Entry points

- `npm run web:build:marketing` runs the root wrapper's patch verifier and web
  audit, generates pages, removes auth assets and verifies the four-page public
  artifact and redirects.
- `npm run web:build` retains the private-beta path and appends the existing
  Expo `/app` export after marketing generation.
- `npm run web:marketing` builds the guarded marketing artifact and starts the
  existing loopback preview server on port 4173 (`PORT` overrides it). Rebuild
  and refresh after editing; this command does not provide automatic hot reload.
- `npm --prefix web run check` prepares the fixed output map in memory. It
  validates required local inputs, reviewed font versions/resources, template
  markers, deployment URL and build mode. It writes no output and does not
  replace audit, browser, accessibility or full build acceptance.

`PESO_WEB_BUILD` accepts `marketing` or `private-beta`, defaulting to marketing
for direct renderer use. The shared beta-entry module retains mode-specific
labels and links. Canonical/social URLs use `DEPLOY_PRIME_URL`, then `URL`, and
are omitted when neither is set. Only the public challenge page reads
`EXPO_PUBLIC_TURNSTILE_SITE_KEY`; its attribute is escaped. No other environment
values are embedded. The root wrapper remains the supported build entry point
for release checks and failed-output cleanup.

The renderer accepts trusted repository HTML and explicit substitutions. It
does not interpret JavaScript in templates. Asset/template paths reject symlinks;
fixed output paths remain beneath `dist/`. HTML text/attribute substitutions
are escaped, and immutable asset filenames use full SHA256 content hashes.

Page content, CSS, demo behavior, public media, Netlify headers/routing,
application budget checks and production visibility requirements retain their
existing contracts. Browser/accessibility acceptance belongs to Gates 11/12.
