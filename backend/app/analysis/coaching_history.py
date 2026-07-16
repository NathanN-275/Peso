from __future__ import annotations

from typing import Any


def technique_trend_cue(
    *,
    video: dict[str, Any],
    analysis: dict[str, Any] | None,
    saved_videos: list[dict[str, Any]],
    analyses_by_video_id: dict[str, dict[str, Any]],
) -> str | None:
    """Return one explainable same-exercise trend cue when history supports it."""
    if not analysis:
        return None
    current_result = analysis.get("result_json") or {}
    current_reps = int(current_result.get("rep_count") or len(current_result.get("reps") or []))
    prior = []
    for saved in saved_videos:
        if str(saved.get("id")) == str(video.get("id")):
            continue
        if saved.get("exercise_type") != video.get("exercise_type") or saved.get("view_type") != video.get("view_type"):
            continue
        result = (analyses_by_video_id.get(str(saved.get("id"))) or {}).get("result_json") or {}
        prior.append(int(result.get("rep_count") or len(result.get("reps") or [])))
    if len(prior) < 2 or not prior or current_reps <= 0:
        return None
    baseline = sum(prior[-3:]) / len(prior[-3:])
    if baseline <= 0:
        return None
    change = round((current_reps - baseline) / baseline * 100)
    if abs(change) < 5:
        return "Your rep count is staying consistent across your recent saved videos."
    direction = "up" if change > 0 else "down"
    return f"Your detected rep count is {abs(change)}% {direction} versus your recent {video.get('exercise_type')} videos."
