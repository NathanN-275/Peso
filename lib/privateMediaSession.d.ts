import type { Session } from '@supabase/supabase-js';

export type PrivateMediaRevocationPage = {
  scope: 'local'; owner_id: string; session_id: string; completed_at: string;
  replayed: boolean; next_cursor: string | null; cookie_cleanup_complete: boolean; cookie_inventory_version?: 2;
};
export type PrivateMediaSessionSnapshot = {
  session: Session | null; event: string;
  status: 'initializing' | 'ready' | 'pending' | 'blocked';
  error: string | null; revision: number;
};
export type PrivateMediaGlobalReceipt = { scope: 'global'; completed_at: string; replayed: boolean; cookie_inventory_version?: 2 };
export type PrivateMediaGlobalIntent = { version: 2; mode: 'global'; inventory_version: 1 | 2; owner_id: string; session_id: string; backend: string };
type SessionStorage = {
  getItem(key: string): string | null | Promise<string | null>;
  setItem(key: string, value: string): void | Promise<void>;
  removeItem(key: string): void | Promise<void>;
  isServer?: boolean;
};
export function createPrivateMediaSessionController(options: {
  enabled: boolean; browserInventoryVersion?: 1 | 2; storage: SessionStorage; storageKey: string; authUrl: string;
  getBackendUrl(): string;
  getAuthMutationKey?(): string | null;
  getLogoutIntentKey?(): string | null | undefined;
  validateIncomingSession?(token: string, backend: string): Promise<{
    owner_id: string; session_id: string; accepted: true;
  }>;
  runExclusive<T>(action: () => Promise<T>): Promise<T>;
  stopMedia(): Promise<void>;
  onActiveKey(key: string | null): void;
  revokeSession(token: string, backend: string, options?: {
    progress?: PrivateMediaRevocationPage | null;
    onProgress?(page: PrivateMediaRevocationPage): Promise<void>;
  }): Promise<PrivateMediaRevocationPage>;
  getGlobalReceipt?(token: string, backend: string): Promise<PrivateMediaGlobalReceipt | null>;
}): {
  storage: SessionStorage;
  beginGlobalLogout(token: string, backend: string, action: (intent?: PrivateMediaGlobalIntent, retainedProviderReceipt?: PrivateMediaGlobalReceipt | null) => Promise<PrivateMediaGlobalReceipt>): Promise<PrivateMediaGlobalReceipt>;
  hasPendingGlobalIntent(token: string, backend: string): Promise<boolean>;
  completeGlobalLogout(token: string, backend: string): Promise<void>;
  authStateChanged(event: string, session: Session | null): void;
  initialize(): Promise<void>;
  getSnapshot(): PrivateMediaSessionSnapshot;
  getTransitionSessionKey(): Promise<string | null>;
  subscribe(fn: (snapshot: PrivateMediaSessionSnapshot) => void): () => void;
  waitForSession(session: Session | null): Promise<Session | null>;
  retry(): Promise<void>;
};
