import Constants from 'expo-constants';
import { Platform } from 'react-native';

export type BackendTarget =
  | 'auto'
  | 'ios-simulator'
  | 'android-emulator'
  | 'physical-device'
  | 'production';

const DEFAULT_BACKEND_PORT = '8000';

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

function buildLocalUrl(hostname: string) {
  const port = process.env.EXPO_PUBLIC_BACKEND_PORT || DEFAULT_BACKEND_PORT;
  return `http://${hostname}:${port}`;
}

export function getBackendTarget(): BackendTarget {
  return (process.env.EXPO_PUBLIC_BACKEND_TARGET as BackendTarget | undefined) ?? 'auto';
}

export function getBackendApiUrl() {
  const explicitUrl = normalizeBackendApiUrl(process.env.EXPO_PUBLIC_BACKEND_URL);

  const target = getBackendTarget();
  const productionUrl = normalizeBackendApiUrl(process.env.EXPO_PUBLIC_PRODUCTION_BACKEND_URL);
  const devMachineHost = process.env.EXPO_PUBLIC_DEV_MACHINE_HOST?.trim();
  const webBackendHost = process.env.EXPO_PUBLIC_WEB_BACKEND_HOST?.trim();

  if (target === 'production') {
    return explicitUrl || productionUrl;
  }

  if (Platform.OS === 'web') {
    return buildLocalUrl(webBackendHost || 'localhost');
  }

  if (explicitUrl) {
    return explicitUrl;
  }

  if (target === 'android-emulator') {
    return buildLocalUrl('10.0.2.2');
  }

  if (target === 'ios-simulator') {
    return buildLocalUrl('localhost');
  }

  if (target === 'physical-device' && devMachineHost) {
    return buildLocalUrl(devMachineHost);
  }

  if (Platform.OS === 'android') {
    return buildLocalUrl('10.0.2.2');
  }

  const expoHostName = getExpoHostName();

  if (expoHostName && expoHostName !== 'localhost' && expoHostName !== '127.0.0.1') {
    return buildLocalUrl(expoHostName);
  }

  return buildLocalUrl('localhost');
}

export function getBackendConnectionDiagnostics() {
  return {
    url: getBackendApiUrl(),
    target: getBackendTarget(),
    platform: Platform.OS,
    expoHost: getExpoHostName(),
    explicitUrl: normalizeBackendApiUrl(process.env.EXPO_PUBLIC_BACKEND_URL) || null,
    webBackendHost: process.env.EXPO_PUBLIC_WEB_BACKEND_HOST?.trim() || null,
    devMachineHost: process.env.EXPO_PUBLIC_DEV_MACHINE_HOST?.trim() || null,
    productionUrl: normalizeBackendApiUrl(process.env.EXPO_PUBLIC_PRODUCTION_BACKEND_URL) || null,
  };
}
