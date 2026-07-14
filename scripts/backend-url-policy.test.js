const assert = require('node:assert/strict');
const test = require('node:test');

const {
  getProductionBackendUrlError,
  isLocalOrPrivateHostname,
} = require('../lib/backendUrlPolicy');

test('production backend URL policy accepts HTTPS public hosts', () => {
  assert.equal(getProductionBackendUrlError('https://api.example.com'), null);
});

test('production backend URL policy rejects plaintext HTTP', () => {
  assert.match(getProductionBackendUrlError('http://api.example.com'), /https/i);
});

test('production backend URL policy rejects localhost and private hosts', () => {
  for (const value of [
    'https://localhost:8000',
    'https://127.0.0.1:8000',
    'https://10.0.0.5:8000',
    'https://172.16.0.5:8000',
    'https://192.168.1.5:8000',
    'https://backend.local:8000',
  ]) {
    assert.match(getProductionBackendUrlError(value), /private-network|localhost/i);
  }
});

test('local/private hostname helper identifies unsafe production targets', () => {
  assert.equal(isLocalOrPrivateHostname('api.example.com'), false);
  assert.equal(isLocalOrPrivateHostname('localhost'), true);
  assert.equal(isLocalOrPrivateHostname('192.168.1.50'), true);
  assert.equal(isLocalOrPrivateHostname('[::1]'), true);
});
