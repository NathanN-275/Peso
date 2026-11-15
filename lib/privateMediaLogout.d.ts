import type { PrivateMediaGlobalIntent } from './privateMediaSession';
import type { PrivateMediaRevocationProgress } from './backendApi';
type LogoutReceipt = { scope: 'global'; completed_at: string; replayed: boolean; cookie_inventory_version?: 2 };
type ReceiptStorage = {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
};

export function createMediaLogoutFetch(options: {
  enabled: boolean;
  browserInventoryVersion?: 1 | 2;
  beginGlobalLogout?(token: string, backend: string, action: (intent?: PrivateMediaGlobalIntent, retainedProviderReceipt?: LogoutReceipt | null) => Promise<LogoutReceipt>): Promise<LogoutReceipt>;
  hasPendingGlobalIntent?(token: string, backend: string): Promise<boolean>;
  completeGlobalLogout?(token: string, backend: string): Promise<void>;
  authUrl: string;
  getBackendUrl(): string;
  storage: ReceiptStorage;
  revokeMedia(accessToken: string, backendUrl: string, options?: PrivateMediaRevocationProgress<'global'>): Promise<LogoutReceipt>;
  stopMedia(): Promise<void>;
  getActiveSessionKey?(): string | null;
  fetch: typeof fetch;
}): {
  fetch: typeof fetch;
  getConfirmedGlobalReceipt(accessToken: string, backendUrl: string): Promise<LogoutReceipt | null>;
  // App-only receipt or exact bound cookie continuation; neither acknowledges provider completion.
  hasPendingGlobalLogout(accessToken: string, backendUrl: string): Promise<boolean>;
  finishLocalSignOut(): Promise<boolean>;
  updateUser<T>(expectedSessionKey: string | null, action: () => Promise<T>): Promise<T>;
  getAuthMutationKey(): string | null;
  getLogoutIntentKey(): string | null | undefined;
  signOut<T>(expectedSessionKey: string | null, action: () => Promise<T>): Promise<T>;
  authStateChanged(event: string, accessToken?: string): void;
};

// Local UI/checkpoint identity only; this does not authenticate a JWT.
export function getPrivateMediaSessionKey(accessToken: string | undefined, issuer: string): string | null;
