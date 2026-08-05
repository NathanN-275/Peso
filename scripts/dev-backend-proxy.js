const http = require('node:http');
const { DEV_BACKEND_PROXY_PATH } = require('../lib/backendDevProxyPolicy');

function resolveDevBackendProxyOrigin(env = process.env) {
  const backendPort = env.BACKEND_PORT || env.EXPO_PUBLIC_BACKEND_PORT || '8000';
  return `http://127.0.0.1:${backendPort}`;
}

function createDevBackendProxyMiddleware(
  next,
  {
    backendOrigin = resolveDevBackendProxyOrigin(),
    request = http.request,
  } = {}
) {
  const targetOrigin = new URL(backendOrigin);

  return (incomingRequest, response, nextCallback) => {
    const incomingUrl = new URL(incomingRequest.url || '/', 'http://metro.local');
    const isProxyRequest =
      incomingUrl.pathname === DEV_BACKEND_PROXY_PATH
      || incomingUrl.pathname.startsWith(`${DEV_BACKEND_PROXY_PATH}/`);

    if (!isProxyRequest) {
      return next(incomingRequest, response, nextCallback);
    }

    const targetUrl = new URL(targetOrigin);
    targetUrl.pathname = incomingUrl.pathname.slice(DEV_BACKEND_PROXY_PATH.length) || '/';
    targetUrl.search = incomingUrl.search;
    const headers = {
      ...incomingRequest.headers,
      host: targetUrl.host,
    };
    const proxyRequest = request(
      targetUrl,
      {
        method: incomingRequest.method,
        headers,
      },
      (proxyResponse) => {
        response.writeHead(proxyResponse.statusCode || 502, proxyResponse.headers);
        proxyResponse.pipe(response);
      }
    );

    proxyRequest.on('error', (error) => {
      if (response.headersSent) {
        response.destroy(error);
        return;
      }

      response.writeHead(502, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({
        detail: `Local backend proxy could not reach ${targetOrigin.origin}. Start FastAPI and try again.`,
      }));
    });
    incomingRequest.on('aborted', () => proxyRequest.destroy());
    incomingRequest.pipe(proxyRequest);
    return undefined;
  };
}

module.exports = {
  createDevBackendProxyMiddleware,
  resolveDevBackendProxyOrigin,
};
