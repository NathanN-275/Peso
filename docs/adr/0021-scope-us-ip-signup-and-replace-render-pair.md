# Restrict signup by US IP and deploy a fresh Render pair

**Accepted by Nathan on November 11, 2026.**

For the Public Web Beta, require a US IP at signup and allow signed-in users
to upload while abroad. Apply the country check through the Supabase Auth hook.
This keeps signup focused on the US launch audience and removes the dependency
on Render forwarding headers for upload eligibility.

Deploy the reviewed build to a fresh production Render API and analysis worker
bound to PesoDatabase. Use a separate fresh staging API and worker with
`peso-staging` credentials during approved test windows. Separate pairs avoid
credential rebinding at cutover and support later staging tests. Retain the
old pair suspended. Both old services previously started their staging builds
on resume, so new service IDs avoid that startup path.

Start each pair with one Starter API and one `1c-2g` worker. Matching sizes
let staging exercise the longest accepted clips on the planned production
worker size. Confirm current pricing and obtain approval before provisioning
or starting paid compute.

This decision updates geographic admission and Render service selection in
[ADR 0018](0018-public-web-beta-release-scope.md) and the
[Public Web Beta Deployment Plan](../deployment/public-beta-launch-plan.md).
