# ADR 0005: Separate the static marketing site from the web app

## Status

Accepted

## Decision

Astro owns the statically generated public routes `/`, `/privacy`, and `/terms`.
The Expo web bundle owns `/app` and all `/app/*` client routes through React
Router with `/app` as its basename. The existing `App.tsx` remains the native
entry point; `App.web.tsx` is selected only by Metro's web resolver.

The combined build writes Astro output to `dist` and the Expo single-page export
to `dist/app`. Netlify serves real files first and rewrites only unknown
`/app/*` requests to `/app/index.html`.

## Context

Marketing pages need small, indexable HTML documents and stable legal URLs.
The product needs a richer signed-in client with browser-specific navigation
and media behavior. Combining those concerns in one runtime would make public
page performance, deployments, and native regression safety harder to reason
about.

## Consequences

- Marketing and product routes have independent source trees and bundles.
- Shared brand values are copied from the canonical platform-neutral tokens and
  protected by a native token regression test.
- A marketing build can never import authenticated application state.
- Direct navigation to a Web App route depends on the scoped Netlify rewrite.
- The `/app` base URL is part of Expo export configuration and must be verified
  in every production build.
