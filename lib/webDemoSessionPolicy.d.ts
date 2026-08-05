export type DemoAnalysisPhase = 'idle' | 'queued' | 'analyzing' | 'ready';

export type DemoAnalysisState = {
  phase: DemoAnalysisPhase;
  percentage: number;
  startTime: number | null;
};

export const QUEUED_DURATION_MS: number;
export const ANALYZING_DURATION_MS: number;
export const TOTAL_ANALYSIS_DURATION_MS: number;

export function createIdleDemoAnalysis(): DemoAnalysisState;
export function startDemoAnalysis(startTime: number): DemoAnalysisState;
export function progressDemoAnalysis(startTime: number, now: number): DemoAnalysisState;
export function cancelDemoAnalysis(): DemoAnalysisState;
