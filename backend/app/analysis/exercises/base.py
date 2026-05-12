from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseExerciseAnalyzer(ABC):
  @abstractmethod
  def analyze(self, *, video_id: str, exercise_type: str, view_type: str, frames: list[dict[str, Any]]) -> dict[str, Any]:
    raise NotImplementedError
