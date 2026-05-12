export type VideoAnalysisStatus = 'uploaded' | 'queued' | 'processing' | 'completed' | 'failed';

export type VideoAnalysisRep = {
  rep_index: number;
  depth_score: number;
  torso_angle?: number;
  torso_angle_change: number;
  flags: string[];
  timestamps_ms?: {
    start: number;
    bottom: number;
    end: number;
  };
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
  exercise: string;
  view: string;
  analysis_limited?: boolean;
  rep_count: number;
  reps: VideoAnalysisRep[];
  summary_flags: string[];
  coach_feedback: string[];
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
