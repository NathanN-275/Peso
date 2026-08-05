const WEB_SURFACE_NATIVE_PREVIEW = 'native-preview';
const WEB_SURFACE_WEB_APP = 'web-app';
const LOCAL_WEB_ROUTER_BASE = '/';
const PRODUCTION_WEB_ROUTER_BASE = '/app';

function resolveWebSurface(env = {}) {
  return env.EXPO_PUBLIC_WEB_SURFACE === WEB_SURFACE_WEB_APP
    ? WEB_SURFACE_WEB_APP
    : WEB_SURFACE_NATIVE_PREVIEW;
}

function resolveWebRouterBase(env = {}) {
  if (env.EXPO_PUBLIC_WEB_ROUTER_BASE === LOCAL_WEB_ROUTER_BASE) {
    return LOCAL_WEB_ROUTER_BASE;
  }

  if (env.EXPO_PUBLIC_WEB_ROUTER_BASE === PRODUCTION_WEB_ROUTER_BASE) {
    return PRODUCTION_WEB_ROUTER_BASE;
  }

  return env.NODE_ENV === 'production'
    ? PRODUCTION_WEB_ROUTER_BASE
    : LOCAL_WEB_ROUTER_BASE;
}

module.exports = {
  LOCAL_WEB_ROUTER_BASE,
  PRODUCTION_WEB_ROUTER_BASE,
  WEB_SURFACE_NATIVE_PREVIEW,
  WEB_SURFACE_WEB_APP,
  resolveWebRouterBase,
  resolveWebSurface,
};
