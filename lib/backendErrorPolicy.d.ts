export function getBackendErrorMessage(errorText: string, status: number): string;
export type VideoSubmissionFailurePhase = 'upload' | 'quality_preflight' | 'queue_analysis';
export function getVideoSubmissionFailureMessage(
  phase: VideoSubmissionFailurePhase,
  message: string
): string;
