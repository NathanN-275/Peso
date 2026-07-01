export type AnalysisRun = {
  generation: number;
  controller: AbortController;
};

export function createAnalysisRun(currentGeneration: number): AnalysisRun;
export function isAnalysisRunCurrent(activeGeneration: number, run: AnalysisRun): boolean;
export function cancelAnalysisRun(activeGeneration: number, run: AnalysisRun): number;
