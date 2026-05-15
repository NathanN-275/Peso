export type VideoAnalysisStatus = 'uploaded' | 'queued' | 'processing' | 'completed' | 'failed';

export type SaveState = 'pending' | 'saved';

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
  torsoAngleChangeDeg?: number;
  depth_score: number;
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
};

export type VideoPoseFrame = {
  time: number;
  keypoints: VideoPoseKeypoint[];
};

export type VideoAnalysisDiagnostics = {
  quality_score?: number;
  pose_coverage?: number;
  lower_body_visibility?: number;
  subject_height?: number;
  side_view_score?: number;
  selected_side?: string | null;
  tracking_side_confidence?: number;
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
  poseFrames?: VideoPoseFrame[];
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
  };
  error?: {
    code: string;
    message: string;
  };
  diagnostics?: VideoAnalysisDiagnostics;
  model_version?: string;
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
  result_json: VideoAnalysisResult;
  summary: string[];
  coaching_feedback: string[];
  rep_data: VideoAnalysisRep[];
};

export type SavedVideo = {
  id: string;
  exercise_type: string;
  view_type: string;
  storage_path: string;
  thumbnail_path: string | null;
  video_url: string;
  thumbnail_url: string | null;
  save_state: SaveState;
  saved_at: string | null;
  created_at: string;
  analysis: SavedVideoAnalysis | null;
};
