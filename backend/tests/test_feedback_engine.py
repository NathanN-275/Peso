from __future__ import annotations

import unittest

from app.analysis.feedback_engine import build_feedback


def rep(
  *,
  depth_score: float,
  depth_status: str,
  depth_reason: str | None = None,
  depth_delta_px: float | None = None,
  depth_tolerance_px: float | None = None,
  rep_index: int = 1,
  flags: list[str] | None = None,
) -> dict[str, object]:
  result: dict[str, object] = {
    "rep_index": rep_index,
    "depth_score": depth_score,
    "depth_status": depth_status,
    "depth_reason": depth_reason,
    "torso_angle_change": 0.0,
    "flags": flags or [],
  }
  if depth_delta_px is not None or depth_tolerance_px is not None:
    result["depth_evidence"] = {
      "depthDeltaPx": depth_delta_px,
      "depthTolerancePx": depth_tolerance_px,
    }
  return result


class FeedbackEngineTest(unittest.TestCase):
  def test_low_composite_score_does_not_create_insufficient_depth_by_itself(self) -> None:
    summary_flags, _feedback = build_feedback(
      [
        rep(depth_score=0.48, depth_status="hit_depth"),
      ]
    )

    self.assertNotIn("Insufficient depth", summary_flags)

  def test_insufficient_depth_status_creates_summary_flag(self) -> None:
    summary_flags, _feedback = build_feedback(
      [
        rep(
          depth_score=0.52,
          depth_status="insufficient_depth",
          flags=["insufficient_depth"],
        ),
      ]
    )

    self.assertIn("Insufficient depth", summary_flags)

  def test_hit_depth_ignores_stale_insufficient_flag(self) -> None:
    summary_flags, _feedback = build_feedback(
      [
        rep(
          depth_score=0.54,
          depth_status="hit_depth",
          depth_reason="depth_met",
          flags=["insufficient_depth"],
        ),
      ]
    )

    self.assertNotIn("Insufficient depth", summary_flags)

  def test_uncertain_depth_reports_confidence_not_insufficient_depth(self) -> None:
    summary_flags, _feedback = build_feedback(
      [
        rep(
          depth_score=0.42,
          depth_status="uncertain_depth",
          flags=["low_depth_confidence"],
        ),
      ]
    )

    self.assertIn("Depth confidence was limited", summary_flags)
    self.assertNotIn("Insufficient depth", summary_flags)

  def test_borderline_depth_gets_close_feedback(self) -> None:
    summary_flags, feedback = build_feedback(
      [
        rep(
          depth_score=0.55,
          depth_status="uncertain_depth",
          depth_reason="borderline_depth",
          flags=["low_depth_confidence"],
        ),
      ]
    )

    self.assertIn("Depth looked close", summary_flags)
    self.assertIn("The rep looked close to depth; try getting the hip crease slightly lower.", feedback)

  def test_screenshot_depth_numbers_do_not_create_insufficient_summary(self) -> None:
    summary_flags, _feedback = build_feedback(
      [
        rep(
          depth_score=0.54,
          depth_status="hit_depth",
          depth_reason="depth_met",
          depth_delta_px=-7.85,
          depth_tolerance_px=15.73,
          flags=["insufficient_depth"],
        ),
      ]
    )

    self.assertNotIn("Insufficient depth", summary_flags)

  def test_hit_and_uncertain_do_not_create_insufficient_summary(self) -> None:
    summary_flags, _feedback = build_feedback(
      [
        rep(depth_score=0.74, depth_status="hit_depth", rep_index=1),
        rep(depth_score=0.51, depth_status="uncertain_depth", rep_index=2),
      ]
    )

    self.assertIn("Depth confidence was limited", summary_flags)
    self.assertNotIn("Insufficient depth", summary_flags)

  def test_mixed_hit_and_insufficient_reports_inconsistent_depth(self) -> None:
    summary_flags, feedback = build_feedback(
      [
        rep(depth_score=0.74, depth_status="hit_depth", rep_index=1),
        rep(depth_score=0.20, depth_status="insufficient_depth", rep_index=2),
      ]
    )

    self.assertIn("Inconsistent depth", summary_flags)
    self.assertNotIn("Insufficient depth", summary_flags)
    self.assertIn("Some reps were above depth: rep 2. Try to match your deepest reps.", feedback)


if __name__ == "__main__":
  unittest.main()
