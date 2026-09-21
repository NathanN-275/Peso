import type { AnalysisActivityItem } from '../src/types/videoAnalysis';

export function failureCopy(activity: AnalysisActivityItem | null | undefined): string;
export function canRetryAnalysis(activity: AnalysisActivityItem | null | undefined): boolean;
