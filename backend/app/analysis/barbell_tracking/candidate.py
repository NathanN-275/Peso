from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
  x: float
  y: float
  radius: float
  confidence: float
