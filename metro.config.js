const { getDefaultConfig } = require('expo/metro-config');
const { withNativeWind } = require('nativewind/metro');
const {
  createDevBackendProxyMiddleware,
  resolveDevBackendProxyOrigin,
} = require('./scripts/dev-backend-proxy');

const config = withNativeWind(getDefaultConfig(__dirname), { input: './global.css' });
const enhanceMiddleware = config.server.enhanceMiddleware;

config.server.enhanceMiddleware = (middleware, metroServer) => {
  const enhancedMiddleware = enhanceMiddleware
    ? enhanceMiddleware(middleware, metroServer)
    : middleware;

  return createDevBackendProxyMiddleware(enhancedMiddleware, {
    backendOrigin: resolveDevBackendProxyOrigin(process.env),
  });
};

module.exports = config;
