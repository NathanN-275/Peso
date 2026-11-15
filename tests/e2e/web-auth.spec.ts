import { expect, type Page } from '@playwright/test';
import { createClient } from '@supabase/supabase-js';
import { test } from './staging-test';

const {
  assertStagingE2EEnvironment, assertStagingVerificationLink, recordStagingFixture,
} = require('../../scripts/e2e-environment');

const webBaseUrl = process.env.PESO_E2E_WEB_BASE_URL ?? 'https://staging-required.invalid';
const signupEmail = process.env.PESO_E2E_SIGNUP_EMAIL ?? 'staging-signup-required@example.com';
const signupPassword = process.env.PESO_E2E_SIGNUP_PASSWORD ?? 'staging-password-required';
const admin = createClient(
  process.env.PESO_E2E_SUPABASE_URL ?? 'https://staging-required.supabase.co',
  process.env.PESO_E2E_SUPABASE_SERVICE_ROLE_KEY ?? 'staging-service-role-required',
  { auth: { autoRefreshToken: false, persistSession: false } }
);

const loginAccount = {
  email: `peso-e2e-${crypto.randomUUID()}@example.com`,
  password: `Peso-E2E-${crypto.randomUUID()}-Aa1!`,
};
let loginUserId: string;

async function findUser(email: string) {
  for (let page = 1; page <= 10; page += 1) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 1000 });
    if (error) throw error;
    const user = data.users.find((candidate) => candidate.email?.toLowerCase() === email.toLowerCase());
    if (user || data.users.length < 1000) return user ?? null;
  }
  throw new Error(`Could not finish searching staging users for ${email}.`);
}

async function completeChallengeAndSubmit(page: Page, buttonName: RegExp) {
  const button = page.getByRole('button', { name: buttonName });
  await expect(button).toBeEnabled({ timeout: 30_000 });
  await button.click();
}

async function signIn(page: Page, email = loginAccount.email, password = loginAccount.password) {
  await page.goto('/app/login');
  await expect(page).toHaveURL(`${webBaseUrl}/app/login`);
  await page.getByRole('textbox', { name: 'Email' }).fill(email);
  await page.getByLabel('Password').fill(password);
  await completeChallengeAndSubmit(page, /sign in/i);
}

test.beforeAll(async () => {
  assertStagingE2EEnvironment(process.env);
  const recordCreated = recordStagingFixture(process.env.PESO_E2E_RECEIPT_DIR, 'login', loginAccount.email);
  const { data, error } = await admin.auth.admin.createUser({
    email: loginAccount.email,
    password: loginAccount.password,
    email_confirm: true,
    user_metadata: { purpose: 'peso-release-e2e' },
  });
  if (error) throw error;
  loginUserId = data.user.id;
  recordCreated(loginUserId);
});

test('invalid credentials are distinct from connectivity and CAPTCHA errors', async ({ page }) => {
  await signIn(page, loginAccount.email, `${loginAccount.password}-wrong`);
  await expect(page.getByText('Incorrect email or password. Please try again.')).toBeVisible();
  await expect(page).toHaveURL(/\/app\/login/);
});

test('login restores the session after reload and logout clears it', async ({ page }) => {
  await signIn(page);
  await expect(page).toHaveURL(/\/app\/?$/);
  await expect(page.getByRole('heading', { name: 'Ready for your next set?' })).toBeVisible();

  await page.reload();
  await expect(page).toHaveURL(/\/app\/?$/);

  await page.goto('/app/settings');
  await page.getByRole('button', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/app\/login/);
});

test('signup, generated confirmation link, and login use one Peso account', async ({ page }) => {
  if (await findUser(signupEmail)) {
    throw new Error('The signup fixture email already belongs to an account. Supply an unused test address.');
  }
  await page.goto('/app/signup');
  await expect(page).toHaveURL(`${webBaseUrl}/app/signup`);
  await page.getByRole('textbox', { name: 'Email' }).fill(signupEmail);
  await page.getByLabel('Password').fill(signupPassword);
  await expect(page.getByRole('checkbox', { name: /reside in the United States/i })).toHaveCount(0);
  const terms = page.getByRole('checkbox', { name: /beta Terms/i });
  await expect(terms).not.toBeChecked();
  await terms.press('Space');
  await expect(terms).toBeChecked();
  const recordCreated = recordStagingFixture(process.env.PESO_E2E_RECEIPT_DIR, 'signup', signupEmail);
  await completeChallengeAndSubmit(page, /create account/i);
  await expect(page.getByRole('heading', { name: 'Verify your email' })).toBeVisible();

  const signupUser = await findUser(signupEmail);
  if (!signupUser) throw new Error('Staging signup fixture was not found.');
  recordCreated(signupUser.id);
  const { data, error } = await admin.auth.admin.generateLink({
    type: 'signup',
    email: signupEmail,
    password: signupPassword,
    options: { redirectTo: `${webBaseUrl}/app/login` },
  });
  if (error) throw error;
  expect(data.user.id).toBe(signupUser.id);
  assertStagingVerificationLink(data.properties.action_link, '/app/login');

  await page.goto(data.properties.action_link);
  await page.waitForURL((url) => url.origin === webBaseUrl && ['/app', '/app/', '/app/login'].includes(url.pathname), {
    timeout: 30_000,
  });
  if (new URL(page.url()).pathname === '/app/login') {
    await signIn(page, signupEmail, signupPassword);
  }
  await expect(page).toHaveURL(/\/app\/?$/);
});

test('reset request suppresses account enumeration', async ({ page }) => {
  await page.goto('/app/reset');
  await expect(page).toHaveURL(`${webBaseUrl}/app/reset`);
  await page.getByRole('textbox', { name: 'Email' }).fill(`missing-${Date.now()}@example.com`);
  await completeChallengeAndSubmit(page, /send reset link/i);
  await expect(
    page.getByText('If an account exists for this email, check your inbox for a secure reset link.')
  ).toBeVisible();
});

test('generated recovery link updates the password', async ({ page }) => {
  const nextPassword = `${loginAccount.password}-next`;
  const { data, error } = await admin.auth.admin.generateLink({
    type: 'recovery',
    email: loginAccount.email,
    options: { redirectTo: `${webBaseUrl}/app/reset` },
  });
  if (error) throw error;
  expect(data.user.id).toBe(loginUserId);
  assertStagingVerificationLink(data.properties.action_link, '/app/reset');

  await page.goto(data.properties.action_link);
  await expect(page).toHaveURL((url) => url.origin === webBaseUrl && url.pathname === '/app/reset');
  await expect(page.getByRole('heading', { name: 'Choose a new password' })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByLabel('New password').fill(nextPassword);
  await page.getByLabel('Confirm password').fill(nextPassword);
  await page.getByRole('button', { name: 'Update password' }).click();
  await expect(page.getByText('Password updated. Your Peso Account is ready to use.')).toBeVisible();
});
