from __future__ import annotations

import unittest

from app.analysis.feedback_engine import build_feedback


def rep(
  *,
  depth_score: float,
  depth_status: str,
  flags: list[str] | None = None,
) -> dict[str, object]:
  return {
    "depth_score": depth_score,
    "depth_status": depth_status,
    "torso_angle_change": 0.0,
    "flags": flags or [],
  }


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


if __name__ == "__main__":
  unittest.main()
