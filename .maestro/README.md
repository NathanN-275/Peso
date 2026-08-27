# Peso Maestro release flows

Use an installed Expo development/preview build, not Expo Go. The current iOS
release gate requires Xcode 26.4 or newer, a booted simulator or connected
device, the Maestro CLI, and the staging environment configured in the build.

Provide these values to Maestro with `-e NAME=value` or its environment manager:

- `PESO_E2E_EMAIL` and `PESO_E2E_PASSWORD` for a confirmed staging user.
- `PESO_E2E_USERNAME`, `PESO_E2E_SIGNUP_EMAIL`, and
  `PESO_E2E_SIGNUP_PASSWORD` for an isolated signup user that the staging
  fixture cleanup removes.
- `PESO_E2E_RESET_LINK` and `PESO_E2E_NEW_PASSWORD` for the generated native
  recovery-link flow.

Run `npm run maestro:auth` for login, persisted-session restore, and logout.
Run `npm run maestro:release` for authenticate → upload → analyze → review →
save → history. The release flow seeds the simulator gallery from
`assets/demo/peso-pose-overlay.mp4`.

`challenge-failure.yaml` requires a separate preview build whose staging
Supabase Auth and client use Cloudflare's matching always-fail test keys. Do not
run it against production or mix an always-fail site key with an always-pass
secret. Malformed, cross-action, and untrusted bridge messages are covered by
the shared contract tests without exposing a test backdoor in the hosted page.

Android is intentionally not a release gate until an SDK/emulator and package
identifier are configured. Appium, Espresso, and Detox are not installed;
Maestro is the Expo black-box strategy for this beta.
