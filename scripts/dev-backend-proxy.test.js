const assert = require('node:assert/strict');
const { PassThrough } = require('node:stream');
const test = require('node:test');

const {
  createDevBackendProxyMiddleware,
  resolveDevBackendProxyOrigin,
} = require('./dev-backend-proxy');

test('dev backend proxy targets the configured local backend port', () => {
  assert.equal(
    resolveDevBackendProxyOrigin({ EXPO_PUBLIC_BACKEND_PORT: '9000' }),
    'http://127.0.0.1:9000'
  );
});

test('dev backend proxy forwards API paths to the local FastAPI origin', () => {
  let forwardedRequest = null;
  let nextCalled = false;
  const request = new PassThrough();
  request.url = '/__peso_api/videos/video-id/save?source=web';
  request.method = 'POST';
  request.headers = {
    host: 'localhost:8081',
    authorization: 'Bearer test-token',
    'content-type': 'application/json',
  };
  const response = new PassThrough();
  const middleware = createDevBackendProxyMiddleware(
    () => {
      nextCalled = true;
    },
    {
      backendOrigin: 'http://127.0.0.1:8000',
      request: (url, options) => {
        forwardedRequest = { url: url.toString(), options };
        return new PassThrough();
      },
    }
  );

  middleware(request, response);
  request.end('{"performed_reps":null}');

  assert.equal(nextCalled, false);
  assert.equal(forwardedRequest.url, 'http://127.0.0.1:8000/videos/video-id/save?source=web');
  assert.equal(forwardedRequest.options.method, 'POST');
  assert.equal(forwardedRequest.options.headers.host, '127.0.0.1:8000');
  assert.equal(forwardedRequest.options.headers.authorization, 'Bearer test-token');
});

test('dev backend proxy leaves non-API Metro requests unchanged', () => {
  let nextCalled = false;
  const request = new PassThrough();
  request.url = '/index.bundle?platform=web';
  request.method = 'GET';
  request.headers = { host: 'localhost:8081' };
  const response = new PassThrough();
  const middleware = createDevBackendProxyMiddleware(
    () => {
      nextCalled = true;
    },
    {
      backendOrigin: 'http://127.0.0.1:8000',
      request: () => {
        throw new Error('Non-API requests must not be proxied.');
      },
    }
  );

  middleware(request, response);

  assert.equal(nextCalled, true);
});
