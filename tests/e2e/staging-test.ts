import { test as base } from '@playwright/test';

const { STUDENT_SUPABASE_URL } = require('../../scripts/student-environment');

export const test = base.extend({
  context: async ({ context }, use) => {
    await context.route(/\/auth\/v1\//, (route) => {
      const origin = new URL(route.request().url()).origin;
      return origin === STUDENT_SUPABASE_URL ? route.continue() : route.abort('blockedbyclient');
    });
    await use(context);
  },
});
