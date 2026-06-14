export type VideoInsertRetryMode =
  | 'tracking_unavailable'
  | 'retry_without_storage_metadata'
  | 'fail';

export function getVideoInsertRetryMode(
  message: string,
  hasTrackingSetup: boolean
): VideoInsertRetryMode;

export function omitLegacyStorageMetadata<T extends Record<string, unknown>>(
  payload: T
): Omit<T, 'original_size_bytes' | 'uploaded_size_bytes' | 'was_compressed' | 'storage_state'>;
