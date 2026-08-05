const assert = require('node:assert/strict');
const test = require('node:test');

const {
  resolveWebRouterBase,
  resolveWebSurface,
} = require('../lib/webSurfacePolicy');

test('web surface defaults to the native preview', () => {
  assert.equal(resolveWebSurface({}), 'native-preview');
  assert.equal(
    resolveWebSurface({ EXPO_PUBLIC_WEB_SURFACE: 'native-preview' }),
    'native-preview'
  );
});

test('web app surface is selected explicitly', () => {
  assert.equal(resolveWebSurface({ EXPO_PUBLIC_WEB_SURFACE: 'web-app' }), 'web-app');
});

test('web router uses root locally and /app in production', () => {
  assert.equal(resolveWebRouterBase({ NODE_ENV: 'development' }), '/');
  assert.equal(resolveWebRouterBase({ NODE_ENV: 'production' }), '/app');
  assert.equal(resolveWebRouterBase({ EXPO_PUBLIC_WEB_ROUTER_BASE: '/' }), '/');
  assert.equal(resolveWebRouterBase({ EXPO_PUBLIC_WEB_ROUTER_BASE: '/app' }), '/app');
});
