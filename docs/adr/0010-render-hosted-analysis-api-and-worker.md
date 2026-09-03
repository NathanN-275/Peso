# ADR 0010: Host the beta analysis API and worker on Render

## Status

Accepted for the current hosted backend; Azure Student is a non-production
replacement candidate under ADR 0012

## Decision

Keep the Render workspace on Hobby and deploy two paid services from the same
Docker image: a Starter FastAPI web service and a continuously running analysis
worker. The API uses `/health/ready`, which validates the durable queue schema,
as its Render health check. Netlify continues to serve the marketing site and
authenticated Web App; Supabase continues to provide authentication, database
records, and private video storage.

The Blueprint keeps the existing `Peso-backend` service name so its public URL
and the configured Netlify backend target remain stable.

The worker begins on Standard unless a staging benchmark with representative
side-view squat videos measures peak resident memory below 400 MB. If it stays
below that limit with repeatable processing times, production may use Starter.
The analysis profile remains `legacy` for the beta and can be rolled back
without changing client code.

## Consequences

- The Render Hobby workspace itself remains free; compute is billed per service.
- Expected hosting is $32/month with a Standard worker, or $14/month after a
  qualifying Starter benchmark.
- Database migrations must land before deploying the API or worker because
  readiness intentionally fails when the queue schema is stale.
- Render holds all backend secrets. Netlify receives only public Supabase values,
  the public Turnstile site key, and `EXPO_PUBLIC_PRODUCTION_BACKEND_URL`.
- Production CORS lists only the exact Netlify production and approved preview
  origins. Authenticated API responses are never cached.
- Render remains authoritative while the Azure Student environment is tested.
  Any paid Azure production cutover requires separate approval and a new ADR.
