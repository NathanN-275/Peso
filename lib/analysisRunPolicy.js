function createAnalysisRun(currentGeneration) {
  return {
    generation: currentGeneration + 1,
    controller: new AbortController(),
  };
}

function isAnalysisRunCurrent(activeGeneration, run) {
  return activeGeneration === run.generation && !run.controller.signal.aborted;
}

function cancelAnalysisRun(activeGeneration, run) {
  run.controller.abort();
  return Math.max(activeGeneration, run.generation) + 1;
}

module.exports = {
  cancelAnalysisRun,
  createAnalysisRun,
  isAnalysisRunCurrent,
};
