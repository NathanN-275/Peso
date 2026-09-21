from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


PROC_ROOT = Path("/proc")


@dataclass
class ProcessMemoryPeaks:
  peak_rss_bytes: int = 0
  stage_peak_rss_bytes: dict[str, int] = field(default_factory=dict)

  def record(self, stage: str, rss_bytes: int) -> None:
    normalized_rss = max(0, int(rss_bytes))
    self.peak_rss_bytes = max(self.peak_rss_bytes, normalized_rss)
    self.stage_peak_rss_bytes[stage] = max(
      self.stage_peak_rss_bytes.get(stage, 0),
      normalized_rss,
    )

  def as_megabytes(self) -> tuple[float, dict[str, float]]:
    # Render reports memory in decimal MB, and the Starter acceptance gate is
    # strictly below 400,000,000 bytes.
    divisor = 1_000_000
    return (
      round(self.peak_rss_bytes / divisor, 2),
      {
        stage: round(value / divisor, 2)
        for stage, value in self.stage_peak_rss_bytes.items()
      },
    )


def _child_pids(pid: int, *, proc_root: Path) -> list[int]:
  children_path = proc_root / str(pid) / "task" / str(pid) / "children"
  try:
    contents = children_path.read_text(encoding="utf-8").strip()
  except (FileNotFoundError, OSError, PermissionError):
    return []
  if not contents:
    return []
  children: list[int] = []
  for value in contents.split():
    try:
      children.append(int(value))
    except ValueError:
      continue
  return children


def _rss_bytes(pid: int, *, proc_root: Path) -> int:
  status_path = proc_root / str(pid) / "status"
  try:
    lines = status_path.read_text(encoding="utf-8").splitlines()
  except (FileNotFoundError, OSError, PermissionError):
    return 0
  for line in lines:
    if not line.startswith("VmRSS:"):
      continue
    fields = line.split()
    if len(fields) < 2:
      return 0
    try:
      return int(fields[1]) * 1024
    except ValueError:
      return 0
  return 0


def process_tree_rss_bytes(root_pid: int, *, proc_root: Path = PROC_ROOT) -> int:
  """Return current Linux RSS for a process and all observable descendants."""
  if root_pid <= 0:
    return 0

  pending = [root_pid]
  seen: set[int] = set()
  total = 0
  while pending:
    pid = pending.pop()
    if pid in seen:
      continue
    seen.add(pid)
    total += _rss_bytes(pid, proc_root=proc_root)
    pending.extend(_child_pids(pid, proc_root=proc_root))
  return total
