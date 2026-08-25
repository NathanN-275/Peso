import type { AnalysisActivityItem } from '../src/types/videoAnalysis';

export function shouldPollAnalysisActivity(
  items: AnalysisActivityItem[],
  surfaceActive: boolean
): boolean;
