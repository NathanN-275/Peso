import { chromium } from '@playwright/test';
const { assertStagingE2EEnvironment, assertStagingDeploymentIdentity } = require('../../scripts/e2e-environment');

export default async function globalSetup() {
  assertStagingE2EEnvironment(process.env);
  const browser = await chromium.launch({ headless: false });
  try {
    const context = await browser.newContext({ storageState: process.env.PESO_E2E_STORAGE_STATE });
    const response = await context.request.get(`${process.env.PESO_E2E_WEB_BASE_URL}/peso-release.json`,
      { maxRedirects: 0 });
    if (!response.ok()) throw new Error('Interactive Netlify visitor sign-in is required before E2E.');
    assertStagingDeploymentIdentity(await response.json(), process.env);
  } finally {
    await browser.close();
  }
  // This read verifies the administrative credential against the isolated project
  // before either spec can create a fixture. Never log the credential or response.
  const key = process.env.PESO_E2E_SUPABASE_SERVICE_ROLE_KEY!;
  const response = await fetch(`${process.env.PESO_E2E_SUPABASE_URL}/auth/v1/admin/users?page=1&per_page=1`, {
    headers: { apikey: key, Authorization: `Bearer ${key}` },
    redirect: 'error',
    signal: AbortSignal.timeout(20000),
  });
  await response.body?.cancel();
  if (!response.ok) throw new Error('Staging administrative credential verification failed.');
}
