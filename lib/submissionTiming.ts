type SubmissionPhase = 'transfer' | 'verification' | 'quality_check' | 'queue_submission';

export async function measureSubmissionPhase<T>(phase: SubmissionPhase, work: () => Promise<T>): Promise<T> {
  const started = performance.now();
  try {
    return await work();
  } finally {
    // No filenames, URLs, credentials or media contents belong in metrics.
    console.info('[video-phase]', { phase, duration_ms: Math.round(performance.now() - started) });
  }
}
