import { SavedVideo, VideoAnalysisResult } from '../types/videoAnalysis';

export function formatTitleLabel(value: string) {
  return value
    .replace(/[_-]/g, ' ')
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatExerciseLabel(exerciseType: string) {
  return formatTitleLabel(exerciseType);
}

export function formatViewLabel(viewType: string) {
  return formatTitleLabel(viewType);
}

export function formatSavedDate(value?: string | null) {
  if (!value) {
    return 'Saved recently';
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return 'Saved recently';
  }

  return `Saved ${date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })}`;
}

export function getSavedVideoSummary(video: SavedVideo) {
  const analysis = video.analysis;
  const result = analysis?.result_json;
  if (result?.analysis_stale || result?.diagnostics?.analysis_stale) {
    return 'Analysis needs re-run';
  }

  return (
    result?.summary_flags?.[0] ??
    result?.summaryFlags?.[0] ??
    analysis?.summary?.[0] ??
    result?.coach_feedback?.[0] ??
    result?.coachingFeedback?.[0] ??
    analysis?.coaching_feedback?.[0] ??
    'Analysis saved'
  );
}

export function buildSavedVideoAnalysisResult(video: SavedVideo): VideoAnalysisResult {
  const result = video.analysis?.result_json;
  const summaryFlags = result?.summary_flags ?? result?.summaryFlags ?? video.analysis?.summary ?? [];
  const coachingFeedback =
    result?.coach_feedback ?? result?.coachingFeedback ?? video.analysis?.coaching_feedback ?? [];
  const reps = result?.reps ?? video.analysis?.rep_data ?? [];
  const exercise = result?.exercise ?? formatExerciseLabel(video.exercise_type);
  const view = result?.view ?? formatViewLabel(video.view_type);

  return {
    ...result,
    video_id: result?.video_id ?? video.id,
    exercise,
    view,
    cameraView: result?.cameraView ?? view,
    rep_count: result?.rep_count ?? reps.length,
    reps,
    summary_flags: summaryFlags,
    summaryFlags: result?.summaryFlags ?? summaryFlags,
    coach_feedback: coachingFeedback,
    coachingFeedback: result?.coachingFeedback ?? coachingFeedback,
    poseFrames: result?.poseFrames ?? [],
    videoWidth: result?.videoWidth ?? null,
    videoHeight: result?.videoHeight ?? null,
    model_version: result?.model_version ?? video.analysis?.model_version,
    analysis_model_version:
      result?.analysis_model_version ?? result?.diagnostics?.analysis_model_version ?? video.analysis?.model_version,
    expected_model_version: result?.expected_model_version ?? result?.diagnostics?.expected_model_version,
    analysis_stale: result?.analysis_stale ?? result?.diagnostics?.analysis_stale ?? false,
    pose_backend: result?.pose_backend ?? result?.diagnostics?.pose_backend,
    fallback_triggered: result?.fallback_triggered ?? result?.diagnostics?.fallback_triggered,
    fallback_reason: result?.fallback_reason ?? result?.diagnostics?.fallback_reason,
    vitpose_frame_count: result?.vitpose_frame_count ?? result?.diagnostics?.vitpose_frame_count,
    landmark_model: result?.landmark_model ?? result?.diagnostics?.landmark_model,
  };
}
