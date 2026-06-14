export type PinnedFrameChangeAction =
  | 'accept'
  | 'restore_pinned_frame'
  | 'reset_and_accept'
  | 'confirm_reset';

export const FRAME_CHANGE_EPSILON_SECONDS: number;

export function getPinnedFrameChangeAction(options: {
  pinCount: number;
  pinnedFrameTime: number | null;
  targetTime: number;
  suppressWarning: boolean;
}): PinnedFrameChangeAction;
