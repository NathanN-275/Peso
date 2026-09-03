from __future__ import annotations

import logging
import os
from dataclasses import dataclass


logger = logging.getLogger(__name__)

LEGACY_PROFILE_ID = "current_18fps_720px"
FAST_PROFILE_ID = "fast_12fps_640px"
BALANCED_PROFILE_ID = "balanced_15fps_640px"


@dataclass(frozen=True)
class AnalysisProfile:
  id: str
  target_fps: float
  max_frame_dimension: int


PROFILES = {
  FAST_PROFILE_ID: AnalysisProfile(FAST_PROFILE_ID, 12.0, 640),
  BALANCED_PROFILE_ID: AnalysisProfile(BALANCED_PROFILE_ID, 15.0, 640),
  LEGACY_PROFILE_ID: AnalysisProfile(LEGACY_PROFILE_ID, 18.0, 720),
}

PROFILE_BENCHMARK_ORDER = (
  FAST_PROFILE_ID,
  BALANCED_PROFILE_ID,
  LEGACY_PROFILE_ID,
)
SUPPORTED_ROLLOUT_MODES = {"legacy", "shadow", "candidate", "default"}


def analysis_profile_from_env() -> tuple[AnalysisProfile, str]:
  """Resolve the active compute profile while keeping a one-flag rollback."""
  rollout_mode = (os.getenv("ANALYSIS_PROFILE_MODE") or "legacy").strip().lower()
  if rollout_mode not in SUPPORTED_ROLLOUT_MODES:
    logger.warning(
      "Ignoring invalid ANALYSIS_PROFILE_MODE=%r; using legacy.",
      rollout_mode,
    )
    rollout_mode = "legacy"

  candidate_id = (os.getenv("ANALYSIS_CANDIDATE_PROFILE") or FAST_PROFILE_ID).strip().lower()
  if candidate_id not in PROFILES or candidate_id == LEGACY_PROFILE_ID:
    logger.warning(
      "Ignoring invalid ANALYSIS_CANDIDATE_PROFILE=%r; using %s.",
      candidate_id,
      FAST_PROFILE_ID,
    )
    candidate_id = FAST_PROFILE_ID

  if rollout_mode in {"candidate", "default"}:
    return PROFILES[candidate_id], rollout_mode
  return PROFILES[LEGACY_PROFILE_ID], rollout_mode


def shadow_profile_from_env() -> AnalysisProfile | None:
  active, rollout_mode = analysis_profile_from_env()
  if rollout_mode != "shadow":
    return None
  candidate_id = (os.getenv("ANALYSIS_CANDIDATE_PROFILE") or FAST_PROFILE_ID).strip().lower()
  return PROFILES.get(candidate_id) or PROFILES[FAST_PROFILE_ID]
