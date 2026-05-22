import { VideoAnalysisResult } from '../types/videoAnalysis';
import {
  normalizeCoachingFeedback,
  normalizeResultFlags,
  normalizeVideoQuality,
} from './videoReview';

export function formatFallbackUnavailableReason(value: string | null | undefined) {
  if (!value) {
    return 'n/a';
  }

  if (value === 'fallback_disabled') {
    return 'Fallback disabled';
  }

  if (value === 'fallback_dependency_missing') {
    return 'Fallback dependency missing';
  }

  if (value === 'fallback_no_pose_detected') {
    return 'Fallback found no pose';
  }

  return value.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function buildAnalysisResultViewModel(result: VideoAnalysisResult) {
  const summaryFlags = normalizeResultFlags(result);
  const coachingFeedback = normalizeCoachingFeedback(result);
  const videoQuality = normalizeVideoQuality(result);
  const cameraView = result.cameraView ?? result.view;
  const selectedPoseSide = result.diagnostics?.pose_validation?.selected_side
    ?? result.diagnostics?.selected_side
    ?? null;
  const analysisStale = result.analysis_stale ?? result.diagnostics?.analysis_stale ?? false;
  const analysisIncomplete = result.analysis_incomplete ?? result.diagnostics?.analysis_incomplete ?? false;
  const depthSummaryDebug = result.diagnostics?.depth_summary_debug;
  const finalInsufficientDepthReps =
    depthSummaryDebug?.insufficient_depth_reps
    ?? result.reps
      .filter((rep) => (rep.depthStatus ?? rep.depth_status) === 'insufficient_depth')
      .map((rep) => rep.repIndex ?? rep.rep_index);
  const finalHitDepthReps =
    depthSummaryDebug?.hit_depth_reps
    ?? result.reps
      .filter((rep) => (rep.depthStatus ?? rep.depth_status) === 'hit_depth')
      .map((rep) => rep.repIndex ?? rep.rep_index);
  const finalUncertainDepthReps =
    depthSummaryDebug?.uncertain_depth_reps
    ?? result.reps
      .filter((rep) => (rep.depthStatus ?? rep.depth_status) === 'uncertain_depth')
      .map((rep) => rep.repIndex ?? rep.rep_index);
  const summaryDepthMismatch =
    summaryFlags.includes('Insufficient depth') && finalInsufficientDepthReps.length === 0;
  const sanitizedSummaryFlags = summaryDepthMismatch
    ? summaryFlags.filter((flag) => flag !== 'Insufficient depth')
    : summaryFlags;
  const displaySummaryFlags = analysisIncomplete ? ['Analysis needs re-run'] : sanitizedSummaryFlags;
  const depthHitCount = finalHitDepthReps.length;
  const repCount = result.rep_count || result.reps.length;
  const depthHitLabel =
    repCount > 0
      ? `Depth hit: ${depthHitCount > 0 ? 'yes' : 'no'} (${depthHitCount}/${repCount} reps)`
      : 'Depth hit: n/a (0 reps)';
  const poseBackend = result.pose_backend ?? result.diagnostics?.pose_backend;
  const fallbackModel = result.fallback_model ?? result.diagnostics?.fallback_model;
  const fallbackRecommended = result.fallback_recommended ?? result.diagnostics?.fallback_recommended ?? false;
  const fallbackAttempted = result.fallback_attempted ?? result.diagnostics?.fallback_attempted ?? false;
  const fallbackTriggered = result.fallback_triggered ?? result.diagnostics?.fallback_triggered ?? false;
  const fallbackReason = result.fallback_reason ?? result.diagnostics?.fallback_reason;
  const fallbackUnavailableReason =
    result.fallback_unavailable_reason ?? result.diagnostics?.fallback_unavailable_reason;
  const landmarkModel = result.landmark_model ?? result.diagnostics?.landmark_model;

  return {
    analysisIncomplete,
    analysisStale,
    cameraView,
    coachingFeedback,
    depthHitLabel,
    depthSummaryDebug,
    displaySummaryFlags,
    fallbackAttempted,
    fallbackModel,
    fallbackReason,
    fallbackRecommended,
    fallbackTriggered,
    fallbackUnavailableReason,
    finalHitDepthReps,
    finalInsufficientDepthReps,
    finalUncertainDepthReps,
    landmarkModel,
    poseBackend,
    selectedPoseSide,
    summaryDepthMismatch,
    videoQuality,
  };
}
