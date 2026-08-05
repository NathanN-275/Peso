import { defineConfig } from 'astro/config';

export default defineConfig({
  output: 'static',
  site: process.env.DEPLOY_PRIME_URL || process.env.URL,
  build: {
    assets: 'marketing-assets',
  },
  vite: {
    build: {
      cssMinify: 'lightningcss',
    },
  },
});
