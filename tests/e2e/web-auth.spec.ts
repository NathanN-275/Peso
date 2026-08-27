import { expect, test, type Page } from '@playwright/test';
import { createClient, type User } from '@supabase/supabase-js';

const webBaseUrl = process.env.PESO_E2E_WEB_BASE_URL ?? 'https://staging-required.invalid';
const signupEmail = process.env.PESO_E2E_SIGNUP_EMAIL ?? 'staging-signup-required@example.com';
const signupPassword = process.env.PESO_E2E_SIGNUP_PASSWORD ?? 'staging-password-required';
const admin = createClient(
  process.env.PESO_E2E_SUPABASE_URL ?? 'https://staging-required.supabase.co',
  process.env.PESO_E2E_SUPABASE_SERVICE_ROLE_KEY ?? 'staging-service-role-required',
  { auth: { autoRefreshToken: false, persistSession: false } }
);

const loginAccount = {
  email: `peso-e2e-${Date.now()}@example.com`,
  password: `Peso-E2E-${Date.now()}-Aa1!`,
};
let loginUser: User | null = null;
let signupUser: User | null = null;

async function findUser(email: string) {
  for (let page = 1; page <= 10; page += 1) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 1000 });
    if (error) throw error;
    const user = data.users.find((candidate) => candidate.email?.toLowerCase() === email.toLowerCase());
    if (user || data.users.length < 1000) return user ?? null;
  }
  throw new Error(`Could not finish searching staging users for ${email}.`);
}

async function deleteUser(user: User | null) {
  if (!user) return;
  const { error } = await admin.auth.admin.deleteUser(user.id);
  if (error && !/not found/i.test(error.message)) throw error;
}

async function completeChallengeAndSubmit(page: Page, buttonName: RegExp) {
  const button = page.getByRole('button', { name: buttonName });
  await expect(button).toBeEnabled({ timeout: 30_000 });
  await button.click();
}

async function signIn(page: Page, email = loginAccount.email, password = loginAccount.password) {
  await page.goto('/app/login');
  await page.getByRole('textbox', { name: 'Email' }).fill(email);
  await page.getByLabel('Password').fill(password);
  await completeChallengeAndSubmit(page, /sign in/i);
}

test.beforeAll(async () => {
  await deleteUser(await findUser(signupEmail));
  const { data, error } = await admin.auth.admin.createUser({
    email: loginAccount.email,
    password: loginAccount.password,
    email_confirm: true,
    user_metadata: { purpose: 'peso-release-e2e' },
  });
  if (error) throw error;
  loginUser = data.user;
});

test.afterAll(async () => {
  await deleteUser(signupUser);
  await deleteUser(loginUser);
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
  await page.getByRole('link', { name: 'Sign out' }).click();
  await expect(page).toHaveURL(/\/app\/login/);
});

test('signup, generated confirmation link, and login use one Peso account', async ({ page }) => {
  await page.goto('/app/signup');
  await page.getByRole('textbox', { name: 'Email' }).fill(signupEmail);
  await page.getByLabel('Password').fill(signupPassword);
  await page.getByRole('checkbox', { name: /reside in the United States/i }).check();
  await page.getByRole('checkbox', { name: /beta Terms/i }).check();
  await completeChallengeAndSubmit(page, /create account/i);
  await expect(page.getByRole('heading', { name: 'Verify your email' })).toBeVisible();

  signupUser = await findUser(signupEmail);
  expect(signupUser).not.toBeNull();
  const { data, error } = await admin.auth.admin.generateLink({
    type: 'signup',
    email: signupEmail,
    password: signupPassword,
    options: { redirectTo: `${webBaseUrl}/app/login` },
  });
  if (error) throw error;

  await page.goto(data.properties.action_link);
  await page.waitForURL(/\/app\/(login)?(?:[?#].*)?$/, { timeout: 30_000 });
  if (/\/app\/login/.test(page.url())) {
    await signIn(page, signupEmail, signupPassword);
  }
  await expect(page).toHaveURL(/\/app\/?$/);
});

test('reset request suppresses account enumeration', async ({ page }) => {
  await page.goto('/app/reset');
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

  await page.goto(data.properties.action_link);
  await expect(page.getByRole('heading', { name: 'Choose a new password' })).toBeVisible({
    timeout: 30_000,
  });
  await page.getByLabel('New password').fill(nextPassword);
  await page.getByLabel('Confirm password').fill(nextPassword);
  await page.getByRole('button', { name: 'Update password' }).click();
  await expect(page.getByText('Password updated. Your Peso Account is ready to use.')).toBeVisible();
});
