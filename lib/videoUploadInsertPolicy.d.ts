export type VideoInsertRetryMode =
  | 'tracking_unavailable'
  | 'retry_without_storage_metadata'
  | 'fail';

export function getVideoInsertRetryMode(
  message: string,
  hasTrackingSetup: boolean
): VideoInsertRetryMode;
