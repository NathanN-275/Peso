import type { TrackingAssistance } from './trackingSetup';

export type VideoAnalysisStatus = 'uploaded' | 'queued' | 'processing' | 'completed' | 'failed';

export type SaveState = 'pending' | 'saved';
export type StorageState = 'available' | 'pruned';

export type DepthStatus = 'hit_depth' | 'insufficient_depth' | 'uncertain_depth';

export type VideoAnalysisRep = {
  rep_index: number;
  repIndex?: number;
  startTime?: number;
  endTime?: number;
  duration?: number;
  repSpeed?: number;
  avgVelocity?: number;
  peakVelocity?: number;
  depthScore?: number;
  depthConfidence?: number;
  depthStatus?: DepthStatus;
  depthFrameIndex?: number;
  depthTimestampMs?: number;
  bottomIndex?: number;
  bottomTimestampMs?: number;
  selectedSide?: string;
  selectedModel?: string;
  selectedSource?: string;
  depthReason?: string;
  torsoAngleChangeDeg?: number;
  depth_score: number;
  depth_confidence?: number;
  depth_status?: DepthStatus;
  depth_frame_index?: number;
  depth_timestamp_ms?: number;
  bottom_index?: number;
  bottom_timestamp_ms?: number;
  selected_side?: string;
  selected_model?: string;
  selected_source?: string;
  depth_reason?: string;
  depth_components?: {
    score?: number;
    confidence?: number;
    depth_classification?: DepthStatus;
    depthClassification?: DepthStatus;
    depth_reason?: string;
    depthReason?: string;
    selected_side?: string | null;
    selected_side_score?: number | null;
    alternate_side_score?: number | null;
    side_clarity?: number | null;
    hip_vs_knee_score?: number;
    knee_flexion_score?: number;
    hip_flexion_score?: number;
    parallel_score?: number;
    visibility_score?: number;
    lower_body_confidence?: number;
    min_lower_body_confidence?: number;
    hip_knee_delta?: number;
    raw_hip_knee_delta?: number;
    hip_crease_offset?: number;
    knee_top_offset?: number;
    estimated_hip_crease_y?: number;
    estimated_knee_top_y?: number;
    depth_delta_px?: number;
    depth_tolerance_px?: number;
    depth_delta_normalized?: number;
    depth_tolerance_normalized?: number;
    hip_vs_knee_ratio?: number;
    ratio_parallel_score?: number;
    absolute_parallel_score?: number;
    selected_bottom_frame_offset?: number;
    selected_bottom_frame_index?: number;
    bottom_depth_landmarks_unreliable?: boolean;
    detected_bottom_depth_landmarks_unreliable?: boolean;
    detected_bottom_occlusion_landmarks_unreliable?: boolean;
  };
  depth_evidence?: {
    selected_side?: string;
    selectedSide?: string;
    selected_model?: string;
    selectedModel?: string;
    selected_source?: string;
    selectedSource?: string;
    bottom_index?: number;
    bottomFrameIndex?: number;
    bottom_timestamp_ms?: number;
    depth_frame_index?: number;
    depth_timestamp_ms?: number;
    scored_frame_differs_from_bottom?: boolean;
    scoring_landmarks?: {
      shoulder?: VideoPoseKeypoint;
      hip?: VideoPoseKeypoint;
      knee?: VideoPoseKeypoint;
      ankle?: VideoPoseKeypoint;
    };
    hip_knee_delta?: number;
    parallel_score?: number;
    depth_confidence?: number;
    depth_status?: DepthStatus;
    depthStatus?: DepthStatus;
    hipY?: number;
    kneeY?: number;
    ankleY?: number;
    hipConfidence?: number;
    kneeConfidence?: number;
    ankleConfidence?: number;
    estimatedHipCreaseY?: number;
    estimatedKneeTopY?: number;
    depthDeltaPx?: number;
    depthTolerancePx?: number;
    depthClassification?: DepthStatus;
    depthReason?: string;
    estimated_hip_crease_y?: number;
    estimated_knee_top_y?: number;
    depth_delta_px?: number;
    depth_tolerance_px?: number;
    depth_classification?: DepthStatus;
    depth_reason?: string;
    plate_rack_occlusion_suspected?: boolean;
    depth_status_downgraded_by_occlusion?: boolean;
  };
  torso_angle?: number;
  torso_angle_change: number;
  estimated_body_velocity?: {
    avg_velocity?: number;
    peak_velocity?: number;
  };
  flags: string[];
  timestamps_ms?: {
    start: number;
    bottom: number;
    end: number;
  };
};

export type VideoPoseKeypoint = {
  name: string;
  x: number;
  y: number;
  confidence: number;
  trackingState?: 'reference' | 'guided' | 'automatic' | 'estimated';
};

export type PoseValidationLandmark = {
  frame_index: number;
  timestamp_ms?: number;
  side: string;
  joint: string;
  status: 'interpolated' | 'rejected';
  reasons: string[];
};

export type VideoPoseFrame = {
  time: number;
  keypoints: VideoPoseKeypoint[];
};

export type BarbellPathPoint = {
  time: number;
  x: number;
  y: number;
  confidence: number;
  trackingState?: 'reference' | 'guided' | 'automatic' | 'estimated';
};

export type BarbellPath = {
  available: boolean;
  target: 'near_plate_collar_center' | string;
  source: 'opencv_circle_tracker' | string;
  coverage: number;
  points: BarbellPathPoint[];
};

export type VideoAnalysisDiagnostics = {
  expected_model_version?: string;
  analysis_model_version?: string;
  analysis_stale?: boolean;
  analysis_incomplete?: boolean;
  pose_backend?: string;
  requested_pose_backend?: string;
  fallback_model?: 'rtmpose' | null;
  fallback_frame_count?: number;
  fallback_recommended?: boolean;
  fallback_attempted?: boolean;
  fallback_triggered?: boolean;
  fallback_reason?: string | null;
  fallback_unavailable_reason?: 'fallback_disabled' | 'fallback_dependency_missing' | 'fallback_no_pose_detected' | null;
  fallback_error?: string;
  fallback_candidate_quality_score?: number;
  primary_quality_score?: number;
  fallback_selection?: 'primary_retained' | string;
  pose_model_disagreement?: boolean;
  model_disagreement_reps?: number[];
  landmark_model?: string;
  quality_score?: number;
  pose_coverage?: number;
  lower_body_visibility?: number;
  subject_height?: number;
  side_view_score?: number;
  landmark_jitter?: number;
  selected_side?: string | null;
  tracking_side_confidence?: number;
  pose_validation?: {
    selected_side?: string | null;
    tracking_side_confidence?: number;
    selected_side_overridden?: boolean;
    subject_height?: number;
    corrected_landmark_count?: number;
    smoothed_landmark_count?: number;
    hysteresis_rejected_jump_count?: number;
    occluded_landmark_count?: number;
    interpolated_landmark_count?: number;
    rejected_landmark_count?: number;
    unreliable_landmarks?: PoseValidationLandmark[];
    quality_score_penalty?: number;
  };
  depth_status_counts?: {
    hit_depth_count?: number;
    insufficient_depth_count?: number;
    uncertain_depth_count?: number;
  };
  depth_summary_debug?: {
    hit_depth_reps?: number[];
    insufficient_depth_reps?: number[];
    uncertain_depth_reps?: number[];
    summary_depth_decision?: string;
    summary_depth_reason?: string;
  };
  depth_debug?: Array<{
    rep_index?: number;
    depth_status?: DepthStatus;
    selected_side?: string;
    selectedSide?: string;
    selected_model?: string;
    selectedModel?: string;
    selected_source?: string;
    selectedSource?: string;
    bottom_index?: number;
    bottomFrameIndex?: number;
    bottom_timestamp_ms?: number;
    depth_frame_index?: number;
    depth_timestamp_ms?: number;
    hipY?: number;
    kneeY?: number;
    ankleY?: number;
    hipConfidence?: number;
    kneeConfidence?: number;
    ankleConfidence?: number;
    estimatedHipCreaseY?: number;
    estimatedKneeTopY?: number;
    depthDeltaPx?: number;
    depthTolerancePx?: number;
    depthClassification?: DepthStatus;
    depthReason?: string;
    depth_reason?: string;
    hip_knee_delta?: number;
    parallel_score?: number;
    depth_confidence?: number;
    scored_frame_differs_from_bottom?: boolean;
    plate_rack_occlusion_suspected?: boolean;
    pose_model_disagreement?: boolean;
  }>;
  plate_rack_occlusion_suspected?: boolean;
  quality_flags?: string[];
  rep_detection?: {
    motion_amplitude?: number;
    minimum_signal?: number;
    maximum_signal?: number;
    low_threshold?: number | null;
    high_threshold?: number | null;
    reason?: string | null;
    rep_count?: number;
  };
  barbell_tracking?: {
    available?: boolean;
    target?: string;
    source?: string;
    coverage?: number;
    sampled_frame_count?: number;
    detected_point_count?: number;
    interpolated_point_count?: number;
    rejected_frame_count?: number;
    failure_reason?: string | null;
    error?: string;
    processing_duration_ms?: number;
    local_tracking_confidence?: number;
    accepted_local_tracking_count?: number;
    fresh_hough_correction_count?: number;
    max_point_gap_seconds?: number;
    effective_tracking_fps?: number;
    manual_seed_count?: number;
    manual_point_count?: number;
    automatic_point_count?: number;
  };
  tracking_assistance?: TrackingAssistance;
};

export type VideoAnalysisResult = {
  video_id: string;
  videoId?: string;
  exercise: string;
  view: string;
  cameraView?: string;
  duration?: number;
  videoWidth?: number | null;
  videoHeight?: number | null;
  processedVideoWidth?: number | null;
  processedVideoHeight?: number | null;
  poseFrames?: VideoPoseFrame[];
  barbellPath?: BarbellPath;
  trackingAssistance?: TrackingAssistance;
  analysis_limited?: boolean;
  rep_count: number;
  reps: VideoAnalysisRep[];
  summary_flags: string[];
  summaryFlags?: string[];
  coach_feedback: string[];
  coachingFeedback?: string[];
  videoQuality?: {
    overallQuality?: number;
    poseCoverage?: number;
    lowerBodyVisibility?: number;
    sideViewConfidence?: number;
    squatMotionSignal?: number;
    landmarkJitter?: number;
    poseValidationReliability?: number;
  };
  error?: {
    code: string;
    message: string;
  };
  diagnostics?: VideoAnalysisDiagnostics;
  model_version?: string;
  analysis_model_version?: string;
  expected_model_version?: string;
  analysis_stale?: boolean;
  analysis_incomplete?: boolean;
  pose_backend?: string;
  fallback_model?: 'rtmpose' | null;
  fallback_frame_count?: number;
  fallback_recommended?: boolean;
  fallback_attempted?: boolean;
  fallback_triggered?: boolean;
  fallback_reason?: string | null;
  fallback_unavailable_reason?: 'fallback_disabled' | 'fallback_dependency_missing' | 'fallback_no_pose_detected' | null;
  fallback_error?: string;
  landmark_model?: string;
};

export type VideoStatusResponse = {
  video_id: string;
  status: VideoAnalysisStatus;
  exercise_type: string;
  view_type: string;
  updated_at: string;
};

export type AnalysisResponse = {
  video_id: string;
  status: VideoAnalysisStatus;
  result_json: VideoAnalysisResult;
};

export type SavedVideoAnalysis = {
  id: string;
  model_version: string;
  created_at: string;
  result_json: Partial<VideoAnalysisResult>;
  summary: string[];
  coaching_feedback: string[];
  rep_data: VideoAnalysisRep[];
};

export type SavedVideo = {
  id: string;
  exercise_type: string;
  view_type: string;
  storage_path: string | null;
  thumbnail_path: string | null;
  video_url: string | null;
  thumbnail_url: string | null;
  save_state: SaveState;
  storage_state: StorageState;
  saved_at: string | null;
  created_at: string;
  analysis: SavedVideoAnalysis | null;
};
