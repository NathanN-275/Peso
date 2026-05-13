import Constants from 'expo-constants';
import { Platform } from 'react-native';

export type BackendTarget =
  | 'auto'
  | 'ios-simulator'
  | 'android-emulator'
  | 'physical-device'
  | 'production';

const DEFAULT_BACKEND_PORT = '8000';

export type BackendUrlSource =
  | 'EXPO_PUBLIC_BACKEND_URL'
  | 'EXPO_PUBLIC_PRODUCTION_BACKEND_URL'
  | 'EXPO_PUBLIC_WEB_BACKEND_HOST'
  | 'android-emulator fallback'
  | 'ios-simulator fallback'
  | 'EXPO_PUBLIC_DEV_MACHINE_HOST'
  | 'Expo host fallback'
  | 'fallback localhost';

function normalizeBackendApiUrl(value?: string | null) {
  return value?.trim().replace(/\/+$/, '') ?? '';
}

function getExpoHostName() {
  const hostUri = Constants.expoConfig?.hostUri?.trim();

  if (!hostUri) {
    return null;
  }

  try {
    const resolvedHostUri = hostUri.includes('://') ? hostUri : `http://${hostUri}`;
    return new URL(resolvedHostUri).hostname;
  } catch {
    return null;
  }
}

function isLoopbackHost(hostname: string | null) {
  return hostname === 'localhost' || hostname === '127.0.0.1';
}

function buildLocalUrl(hostname: string) {
  const port = process.env.EXPO_PUBLIC_BACKEND_PORT || DEFAULT_BACKEND_PORT;
  return `http://${hostname}:${port}`;
}

export function getBackendTarget(): BackendTarget {
  return (process.env.EXPO_PUBLIC_BACKEND_TARGET as BackendTarget | undefined) ?? 'auto';
}

export function resolveBackendApiConfig() {
  const explicitUrl = normalizeBackendApiUrl(process.env.EXPO_PUBLIC_BACKEND_URL);
  if (explicitUrl) {
    return {
      url: explicitUrl,
      source: 'EXPO_PUBLIC_BACKEND_URL' as BackendUrlSource,
    };
  }

  const target = getBackendTarget();
  const productionUrl = normalizeBackendApiUrl(process.env.EXPO_PUBLIC_PRODUCTION_BACKEND_URL);
  const devMachineHost = process.env.EXPO_PUBLIC_DEV_MACHINE_HOST?.trim();
  const webBackendHost = process.env.EXPO_PUBLIC_WEB_BACKEND_HOST?.trim();

  if (target === 'production') {
    return {
      url: productionUrl,
      source: 'EXPO_PUBLIC_PRODUCTION_BACKEND_URL' as BackendUrlSource,
    };
  }

  if (Platform.OS === 'web') {
    if (webBackendHost) {
      return {
        url: buildLocalUrl(webBackendHost),
        source: 'EXPO_PUBLIC_WEB_BACKEND_HOST' as BackendUrlSource,
      };
    }

    return {
      url: buildLocalUrl('localhost'),
      source: 'fallback localhost' as BackendUrlSource,
    };
  }

  if (target === 'android-emulator') {
    return {
      url: buildLocalUrl('10.0.2.2'),
      source: 'android-emulator fallback' as BackendUrlSource,
    };
  }

  if (target === 'ios-simulator') {
    return {
      url: buildLocalUrl('localhost'),
      source: 'ios-simulator fallback' as BackendUrlSource,
    };
  }

  if (target === 'physical-device' && devMachineHost) {
    return {
      url: buildLocalUrl(devMachineHost),
      source: 'EXPO_PUBLIC_DEV_MACHINE_HOST' as BackendUrlSource,
    };
  }

  if (Platform.OS === 'android') {
    return {
      url: buildLocalUrl('10.0.2.2'),
      source: 'android-emulator fallback' as BackendUrlSource,
    };
  }

  const expoHostName = getExpoHostName();

  if (expoHostName && !isLoopbackHost(expoHostName)) {
    return {
      url: buildLocalUrl(expoHostName),
      source: 'Expo host fallback' as BackendUrlSource,
    };
  }

  if (devMachineHost) {
    return {
      url: buildLocalUrl(devMachineHost),
      source: 'EXPO_PUBLIC_DEV_MACHINE_HOST' as BackendUrlSource,
    };
  }

  return {
    url: buildLocalUrl('localhost'),
    source: 'fallback localhost' as BackendUrlSource,
  };
}

export function getBackendApiUrl() {
  return resolveBackendApiConfig().url;
}

export function getBackendConnectionDiagnostics() {
  const resolved = resolveBackendApiConfig();

  return {
    url: resolved.url,
    source: resolved.source,
    target: getBackendTarget(),
    platform: Platform.OS,
    expoHost: getExpoHostName(),
    explicitUrl: normalizeBackendApiUrl(process.env.EXPO_PUBLIC_BACKEND_URL) || null,
    webBackendHost: process.env.EXPO_PUBLIC_WEB_BACKEND_HOST?.trim() || null,
    devMachineHost: process.env.EXPO_PUBLIC_DEV_MACHINE_HOST?.trim() || null,
    productionUrl: normalizeBackendApiUrl(process.env.EXPO_PUBLIC_PRODUCTION_BACKEND_URL) || null,
  };
}
