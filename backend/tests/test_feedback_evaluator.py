import unittest

from app.analysis.feedback_evaluator import aggregate_feedback_results, evaluate_feedback


class FeedbackEvaluatorTests(unittest.TestCase):
  def test_measures_pose_and_barbell_corrections_in_pixels(self) -> None:
    trace = {
      "run_id": "fixture",
      "events": [
        {"type": "snapshot", "payload": {"name": "pose_repair", "pose_repair": {"selected_side": "right"}, "frames": [{
          "source_frame_index": 60, "timestamp_ms": 1000, "frame_width": 100, "frame_height": 200,
          "landmarks": {"right_knee": {"x": 0.5, "y": 0.5, "visibility": 1}, "right_upper_back": {"x": 0.4, "y": 0.3}}
        }]}},
        {"type": "snapshot", "payload": {"name": "barbell_tracking", "barbell_path": {
          "points": [{"time": 1, "x": 0.6, "y": 0.4, "markerX": 0.6, "markerY": 0.4, "manual_assisted": True}]
        }}},
      ],
    }
    feedback = {"run_id": "fixture", "annotations": [{"issue_types": ["wrong_point", "drift"], "corrections": [
      {"target": "right_knee", "source_frame_index": 60, "timestamp_ms": 9999, "x": 0.6, "y": 0.5},
      {"target": "upper_back", "source_frame_index": 60, "timestamp_ms": 1000, "x": 0.4, "y": 0.35},
      {"target": "barbell_center", "source_frame_index": 60, "timestamp_ms": 1000, "x": 0.6, "y": 0.45},
    ]}]}
    result = evaluate_feedback(trace, feedback)
    self.assertEqual(result["evaluated_corrections"], 3)
    self.assertEqual(result["metrics"]["right_knee"]["median_px"], 10.0)
    self.assertEqual(result["metrics"]["barbell_center"]["median_px"], 10.0)
    self.assertEqual(result["metrics"]["upper_back"]["median_px"], 10.0)
    self.assertEqual(result["matched_correction_coverage"], 1.0)
    self.assertEqual(result["mode_metrics"]["pin_assisted"]["count"], 1)
    self.assertEqual(result["issue_counts"]["identity_switch"], 1)
    self.assertEqual(result["issue_counts"]["drift"], 1)

  def test_missing_output_is_not_scored_as_zero_error(self) -> None:
    result = evaluate_feedback({"events": []}, {"annotations": [{"corrections": [
      {"target": "barbell_center", "source_frame_index": 60, "timestamp_ms": 1000, "x": 0.5, "y": 0.5}
    ]}]})
    self.assertEqual(result["evaluated_corrections"], 0)
    self.assertEqual(result["metrics"], {})
    self.assertEqual(result["matched_correction_coverage"], 0.0)
    self.assertEqual(result["unmatched_corrections"][0]["reason"], "source_frame_not_in_trace")

  def test_aggregate_preserves_unmatched_coverage_and_mode_separation(self) -> None:
    aggregate = aggregate_feedback_results([
      {"correction_count": 2, "evaluated_corrections": 2, "mode_error_samples_px": {"automatic": [4, 12]}, "issue_counts": {"drift": 1}},
      {"correction_count": 2, "evaluated_corrections": 1, "mode_error_samples_px": {"pin_assisted": [8]}, "issue_counts": {"gaps": 1}},
    ])
    self.assertEqual(aggregate["matched_correction_coverage"], 0.75)
    self.assertEqual(aggregate["unmatched_correction_count"], 1)
    self.assertEqual(aggregate["mode_metrics"]["automatic"]["p95_px"], 12.0)
    self.assertEqual(aggregate["mode_metrics"]["pin_assisted"]["max_px"], 8.0)
    self.assertEqual(aggregate["issue_counts"]["drift"], 1)
    self.assertEqual(aggregate["issue_counts"]["gaps"], 1)
