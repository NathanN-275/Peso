# Render the fixed Marketing Site with Node

Accepted for candidate implementation on October 25, 2026; release acceptance
remains subject to the launch gates. Nathan selected removal of the affected
Astro dependency path and delegated the recommended implementation decisions.
Use a small build-time Node renderer for the five fixed routes and shared HTML
templates, retaining the existing font packages, local assets, build modes and
Expo composition. This removes the Astro/cache graph while avoiding another
framework dependency and preserves the current content/security boundaries.

Explicit template and asset validation, escaping, content hashes and regression
coverage replace the framework's build behavior. Local development requires a
rebuild and refresh; it has no automatic hot reload. The font-only clean install
and web audit do not clear root dependencies or establish Linux, hosted,
browser/accessibility or Public Web Beta acceptance.
