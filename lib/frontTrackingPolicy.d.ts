import type { VideoPoseFrame } from '../src/types/videoAnalysis';

export const FRONT_TRAIL_WINDOW_SECONDS: number;
export const MAX_FRONT_TRAIL_SAMPLE_GAP_SECONDS: number;

export function shouldShowFrontMotionTrails(input: {
  cameraView?: string;
  exercise?: string | null;
}): boolean;

export function frontTrailWindowFrames(
  frames: VideoPoseFrame[] | undefined,
  currentTime: number,
  windowSeconds?: number
): VideoPoseFrame[];

export function shouldConnectFrontTrailSamples(
  previousTime: number,
  currentTime: number
): boolean;
