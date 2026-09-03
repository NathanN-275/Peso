import type { AnalysisActivityItem } from '../src/types/videoAnalysis';

export function mergeAnalysisActivity(
  serverItems: AnalysisActivityItem[],
  optimisticItems: AnalysisActivityItem[],
  nowMs?: number
): AnalysisActivityItem[];

export function shouldPollAnalysisActivity(
  items: AnalysisActivityItem[],
  surfaceActive: boolean
): boolean;
