import { createClient, type User } from '@supabase/supabase-js';
import { expect, test } from '@playwright/test';

const account = {
  email: `peso-recording-${Date.now()}@example.com`,
  password: `Peso-Recording-${Date.now()}-Aa1!`,
};
const admin = createClient(
  process.env.PESO_E2E_SUPABASE_URL ?? 'https://staging-required.supabase.co',
  process.env.PESO_E2E_SUPABASE_SERVICE_ROLE_KEY ?? 'staging-service-role-required',
  { auth: { autoRefreshToken: false, persistSession: false } }
);
let recordingUser: User | null = null;

test.beforeAll(async () => {
  const { data, error } = await admin.auth.admin.createUser({
    email: account.email,
    password: account.password,
    email_confirm: true,
    user_metadata: { purpose: 'peso-recording-e2e' },
  });
  if (error) throw error;
  recordingUser = data.user;
});

test.afterAll(async () => {
  if (!recordingUser) return;
  const { error } = await admin.auth.admin.deleteUser(recordingUser.id);
  if (error && !/not found/i.test(error.message)) throw error;
});

test('fake camera recording can be trimmed and handed to the upload review', async ({ page }) => {
  await page.goto('/app/login');
  await page.getByRole('textbox', { name: 'Email' }).fill(account.email);
  await page.getByLabel('Password').fill(account.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/app\/?$/);

  await page.goto('/app/setup');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByRole('heading', { name: 'Choose your video' })).toBeVisible();
  await page.getByRole('button', { name: 'Record Video' }).click();
  await expect(page.getByRole('button', { name: 'Start Recording' })).toBeEnabled();

  await page.getByRole('button', { name: 'Start Recording' }).click();
  await page.waitForTimeout(1_500);
  await page.getByRole('button', { name: 'Stop Recording' }).click();
  await expect(page.getByRole('button', { name: 'Use Recording' })).toBeVisible();

  const trimTrack = page.getByLabel('Trim recording');
  const box = await trimTrack.boundingBox();
  if (!box) throw new Error('The recording trim track was not rendered.');
  await page.mouse.click(box.x + box.width * 0.7, box.y + box.height / 2);

  await page.getByRole('button', { name: 'Use Recording' }).click();
  await expect(page.getByText('Review Recording', { exact: true })).toBeVisible();
  await expect(page.getByText(/peso-recording-.*\.(mp4|webm)/i)).toBeVisible();
});
