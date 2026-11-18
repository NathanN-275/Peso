const assert = require('node:assert/strict');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { chromium, webkit, expect } = require('@playwright/test');

// Use an Expo web export with the fixture values described in
// docs/implementation/web-ui-analysis-flow-20261115.md, media disabled and a fixture Turnstile key.
const root = path.resolve(process.env.PESO_UI_EXPORT || '/tmp/peso-ui-fixture');
const origin = 'http://localhost:4173';
const authOrigin = process.env.PESO_UI_AUTH_ORIGIN || 'https://fixture.supabase.co';
const email = 'fixture@example.test';
const newPassword = 'fixture-new-password';
const user = { id: '11111111-1111-4111-8111-111111111111', email, app_metadata: {}, user_metadata: {} };
const encode = value => Buffer.from(JSON.stringify(value)).toString('base64url');
const accessToken = `${encode({ alg: 'HS256' })}.${encode({ sub: user.id, iss: `${authOrigin}/auth/v1`, session_id: '22222222-2222-4222-8222-222222222222' })}.fixture`;
const session = { access_token: accessToken, refresh_token: 'fixture-refresh', expires_in: 3600, token_type: 'bearer', user };

function serveExport(route) {
  const url = new URL(route.request().url());
  if (url.origin !== origin) return route.abort();
  if (url.pathname.startsWith('/app/_expo/')) {
    return route.fulfill({ path: path.join(root, url.pathname.slice('/app/'.length)) });
  }
  if (route.request().isNavigationRequest()) return route.fulfill({ path: path.join(root, 'index.html') });
  return route.abort();
}

async function run(engine, failFirstLogout) {
  const browser = await engine.launch(engine === chromium ? { executablePath: process.env.PESO_CHROMIUM } : {});
  try {
    const page = await browser.newPage({ serviceWorkers: 'block' });
    let challenge, exchangeCount = 0, passwordUpdateCount = 0, logoutCount = 0, loginCount = 0;
    await page.addInitScript(() => {
      window.turnstile = {
        render(_container, options) { queueMicrotask(() => options.callback('fixture-captcha')); return 'fixture'; },
        remove() {},
      };
    });
    await page.context().route('**/*', async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin === authOrigin) {
        if (url.pathname === '/auth/v1/recover' && request.method() === 'POST') {
          const body = request.postDataJSON();
          assert.equal(body.email, email);
          assert.equal(url.searchParams.get('redirect_to'), `${origin}/app/reset`);
          assert.equal(body.code_challenge_method, 's256');
          challenge = body.code_challenge;
          return route.fulfill({ json: {} });
        }
        if (url.pathname === '/auth/v1/token' && url.searchParams.get('grant_type') === 'pkce') {
          exchangeCount += 1;
          const body = request.postDataJSON();
          assert.equal(body.auth_code, 'fixture-recovery-code');
          assert.equal(createHash('sha256').update(body.code_verifier).digest('base64url'), challenge);
          return route.fulfill({ json: session });
        }
        if (url.pathname === '/auth/v1/user' && request.method() === 'PUT') {
          passwordUpdateCount += 1;
          assert.equal(request.postDataJSON().password, newPassword);
          assert.equal(request.headers().authorization, `Bearer ${accessToken}`);
          return route.fulfill({ json: user });
        }
        if (url.pathname === '/auth/v1/logout' && request.method() === 'POST') {
          logoutCount += 1;
          if (failFirstLogout && logoutCount === 1) {
            return route.fulfill({ status: 422, json: { msg: 'Synthetic logout failure' } });
          }
          return route.fulfill({ status: 204 });
        }
        if (url.pathname === '/auth/v1/token' && url.searchParams.get('grant_type') === 'password') {
          loginCount += 1;
          const credentials = request.postDataJSON();
          assert.equal(credentials.email, email);
          assert.equal(credentials.password, newPassword);
          assert.equal(passwordUpdateCount, 1);
          assert.ok(logoutCount > 0);
          return route.fulfill({ json: session });
        }
      }
      return serveExport(route);
    });

    await page.goto(`${origin}/app/reset`);
    await page.getByRole('textbox', { name: 'Email' }).fill(email);
    await page.getByRole('button', { name: 'Send reset link' }).click();
    await expect(page.getByText(/If an account exists for this email/)).toBeVisible();
    await page.goto(`${origin}/app/reset?code=fixture-recovery-code`);
    await expect.poll(() => exchangeCount).toBe(1);
    await expect(page.getByRole('heading', { name: 'Choose a new password' })).toBeVisible({ timeout: 5000 });
    await expect(page).toHaveURL(`${origin}/app/reset`);
    await page.getByLabel('New password', { exact: true }).fill(newPassword);
    await page.getByLabel('Confirm password', { exact: true }).fill(newPassword);
    await page.getByRole('button', { name: 'Update password' }).click();
    if (failFirstLogout) {
      await expect(page.getByRole('alert')).toHaveText(/Password updated.*sign out/);
      await expect(page.getByRole('button', { name: 'Update password' })).toHaveCount(0);
      await page.getByRole('button', { name: 'Continue to sign in' }).click();
    }
    await expect(page).toHaveURL(`${origin}/app/login`, { timeout: 5000 });
    await expect(page.getByRole('heading', { name: 'Sign in to Peso' })).toBeVisible();
    await expect(page.getByRole('status')).toHaveText('Password updated. Sign in with your new password.');
    await expect(page.getByRole('textbox', { name: 'Email' })).toHaveValue(email);
    const loginPassword = page.getByLabel('Password', { exact: true });
    await expect(loginPassword).toHaveValue('');
    await loginPassword.fill(newPassword);
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page).toHaveURL(/\/app\/?$/);
    assert.equal(exchangeCount, 1);
    assert.equal(passwordUpdateCount, 1);
    assert.equal(logoutCount, failFirstLogout ? 2 : 1);
    assert.equal(loginCount, 1);
    console.log(`${engine.name()}: reset, ${failFirstLogout ? 'logout retry' : 'logout'}, and new-password login passed`);
  } finally {
    await browser.close();
  }
}

(async () => {
  await run(chromium, false);
  if (!process.env.PESO_CHROMIUM_ONLY) {
    await run(chromium, true);
    await run(webkit, false);
    await run(webkit, true);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
