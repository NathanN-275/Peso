from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.analysis.versioning import annotate_analysis_freshness, analysis_is_current
from app.services.config import DEFAULT_MODEL_VERSION, get_settings


class VideoRoutesTest(unittest.TestCase):
  def tearDown(self) -> None:
    get_settings.cache_clear()

  def test_old_model_result_is_marked_stale(self) -> None:
    with patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
      },
      clear=True,
    ):
      get_settings.cache_clear()
      analysis = {
        "model_version": "mediapipe-pose-v2-depth-score",
        "result_json": {
          "model_version": "mediapipe-pose-v2-depth-score",
          "diagnostics": {},
        },
      }

      annotated = annotate_analysis_freshness(analysis["result_json"], analysis)

    self.assertFalse(analysis_is_current(analysis))
    self.assertTrue(annotated["analysis_stale"])
    self.assertEqual(annotated["expected_model_version"], DEFAULT_MODEL_VERSION)
    self.assertEqual(annotated["diagnostics"]["analysis_stale"], True)

  def test_current_model_missing_pose_payload_is_marked_incomplete(self) -> None:
    with patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
      },
      clear=True,
    ):
      get_settings.cache_clear()
      analysis = {
        "model_version": DEFAULT_MODEL_VERSION,
        "result_json": {
          "model_version": DEFAULT_MODEL_VERSION,
          "reps": [
            {
              "rep_index": 1,
              "depth_score": 0.4,
              "flags": ["insufficient_depth"],
            }
          ],
          "diagnostics": {},
        },
      }

      annotated = annotate_analysis_freshness(analysis["result_json"], analysis)

    self.assertFalse(analysis_is_current(analysis))
    self.assertTrue(annotated["analysis_stale"])
    self.assertTrue(annotated["analysis_incomplete"])
    self.assertTrue(annotated["diagnostics"]["analysis_incomplete"])

  def test_current_model_complete_pose_payload_is_current(self) -> None:
    with patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
      },
      clear=True,
    ):
      get_settings.cache_clear()
      analysis = {
        "model_version": DEFAULT_MODEL_VERSION,
        "result_json": {
          "model_version": DEFAULT_MODEL_VERSION,
          "pose_backend": "mediapipe",
          "landmark_model": "mediapipe_pose_33",
          "reps": [
            {
              "rep_index": 1,
              "depth_status": "hit_depth",
              "selected_side": "left",
              "selected_source": "mediapipe",
              "depth_evidence": {
                "hip_knee_delta": -0.02,
                "parallel_score": 1.0,
                "selected_side": "left",
                "selected_source": "mediapipe",
                "estimated_hip_crease_y": 0.61,
                "estimated_knee_top_y": 0.58,
                "depth_delta_px": 22.0,
                "depth_tolerance_px": 14.0,
                "depth_classification": "hit_depth",
                "depth_reason": "depth_met",
              },
            }
          ],
          "diagnostics": {},
        },
      }

      annotated = annotate_analysis_freshness(analysis["result_json"], analysis)

    self.assertTrue(analysis_is_current(analysis))
    self.assertFalse(annotated["analysis_stale"])
    self.assertFalse(annotated["analysis_incomplete"])

  def test_current_model_missing_new_depth_debug_fields_is_marked_incomplete(self) -> None:
    with patch.dict(
      os.environ,
      {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role",
        "SUPABASE_JWT_SECRET": "secret",
      },
      clear=True,
    ):
      get_settings.cache_clear()
      analysis = {
        "model_version": DEFAULT_MODEL_VERSION,
        "result_json": {
          "model_version": DEFAULT_MODEL_VERSION,
          "pose_backend": "mediapipe",
          "landmark_model": "mediapipe_pose_33",
          "reps": [
            {
              "rep_index": 1,
              "depth_status": "hit_depth",
              "depth_evidence": {
                "hip_knee_delta": -0.02,
                "parallel_score": 1.0,
              },
            }
          ],
          "diagnostics": {},
        },
      }

      annotated = annotate_analysis_freshness(analysis["result_json"], analysis)

    self.assertFalse(analysis_is_current(analysis))
    self.assertTrue(annotated["analysis_stale"])
    self.assertTrue(annotated["analysis_incomplete"])


if __name__ == "__main__":
  unittest.main()
