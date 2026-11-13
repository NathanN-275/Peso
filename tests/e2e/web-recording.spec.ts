import { createClient } from '@supabase/supabase-js';
import { expect } from '@playwright/test';
import { test } from './staging-test';

const { assertStagingE2EEnvironment, recordStagingFixture } = require('../../scripts/e2e-environment');
const webBaseUrl = process.env.PESO_E2E_WEB_BASE_URL;
const account = {
  email: `peso-recording-${crypto.randomUUID()}@example.com`,
  password: `Peso-Recording-${crypto.randomUUID()}-Aa1!`,
};
const admin = createClient(
  process.env.PESO_E2E_SUPABASE_URL ?? 'https://staging-required.supabase.co',
  process.env.PESO_E2E_SUPABASE_SERVICE_ROLE_KEY ?? 'staging-service-role-required',
  { auth: { autoRefreshToken: false, persistSession: false } }
);
test.beforeAll(async () => {
  assertStagingE2EEnvironment(process.env);
  const recordCreated = recordStagingFixture(process.env.PESO_E2E_RECEIPT_DIR, 'recording', account.email);
  const { data, error } = await admin.auth.admin.createUser({
    email: account.email,
    password: account.password,
    email_confirm: true,
    user_metadata: { purpose: 'peso-recording-e2e' },
  });
  if (error) throw error;
  recordCreated(data.user.id);
});

test('fake camera recording can be trimmed and handed to the upload review', async ({ page }) => {
  await page.goto('/app/login');
  await expect(page).toHaveURL(`${webBaseUrl}/app/login`);
  await page.getByRole('textbox', { name: 'Email' }).fill(account.email);
  await page.getByLabel('Password').fill(account.password);
  await page.getByRole('button', { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/app\/?$/);

  await page.goto('/app/setup');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByRole('heading', { name: 'Choose your video' })).toBeVisible();
  const recordVideo = page.getByRole('button', { name: 'Record Video', exact: true });
  const startRecording = page.getByRole('button', { name: 'Start Recording', exact: true });
  await recordVideo.click();
  await expect(startRecording).toBeEnabled();
  await page.getByRole('button', { name: 'Edit Setup', exact: true }).press('Space');
  await expect(page).toHaveURL(`${webBaseUrl}/app/setup`);
  await page.getByRole('button', { name: 'Continue' }).click();
  await recordVideo.click();
  await expect(startRecording).toBeEnabled();

  await startRecording.click();
  await page.waitForTimeout(1_500);
  await page.getByRole('button', { name: 'Stop Recording' }).click();
  await expect(page.getByRole('button', { name: 'Use Recording' })).toBeVisible();

  const trimTrack = page.getByLabel('Trim recording');
  const box = await trimTrack.boundingBox();
  if (!box) throw new Error('The recording trim track was not rendered.');
  await page.mouse.click(box.x + box.width * 0.7, box.y + box.height / 2);

  await page.getByRole('button', { name: 'Use Recording' }).press('Space');
  await expect(page.getByText('Review Recording', { exact: true })).toBeVisible();
  const recording = page.getByText(/peso-recording-.*\.(mp4|webm)/i);
  await expect(recording).toBeVisible();

  await page.getByRole('button', { name: /^Edit (?:Video )?Setup$/ }).click();
  await page.getByTestId('setup-angle').click();
  await page.getByTestId('setup-angle-front').click();
  const continueSetup = page.getByTestId('setup-continue');
  await expect(continueSetup).toBeDisabled();
  await expect(page.getByText('The web beta currently supports Side-view Squat only.')).toBeVisible();

  await page.getByTestId('setup-angle').click();
  await page.getByTestId('setup-angle-side').click();
  await continueSetup.click();
  await expect(recording).toBeVisible();
});
