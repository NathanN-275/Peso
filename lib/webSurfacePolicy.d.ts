export type WebSurface = 'native-preview' | 'web-app';
export type WebRouterBase = '/' | '/app';

export const WEB_SURFACE_NATIVE_PREVIEW: 'native-preview';
export const WEB_SURFACE_WEB_APP: 'web-app';
export const LOCAL_WEB_ROUTER_BASE: '/';
export const PRODUCTION_WEB_ROUTER_BASE: '/app';

export function resolveWebSurface(env?: Record<string, string | undefined>): WebSurface;
export function resolveWebRouterBase(env?: Record<string, string | undefined>): WebRouterBase;
