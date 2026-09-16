from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.jobs.process_memory import ProcessMemoryPeaks, process_tree_rss_bytes


class ProcessTreeMemoryTest(unittest.TestCase):
  def test_sums_root_and_recursive_child_rss(self) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
      proc_root = Path(temporary_directory)
      for pid, rss_kib, children in (
        (10, 100, "11 12"),
        (11, 200, "13"),
        (12, 300, ""),
        (13, 400, ""),
      ):
        process_root = proc_root / str(pid)
        task_root = process_root / "task" / str(pid)
        task_root.mkdir(parents=True)
        (process_root / "status").write_text(
          f"Name:\ttest\nVmRSS:\t{rss_kib} kB\n",
          encoding="utf-8",
        )
        (task_root / "children").write_text(children, encoding="utf-8")

      self.assertEqual(
        process_tree_rss_bytes(10, proc_root=proc_root),
        1000 * 1024,
      )

  def test_records_overall_and_per_stage_peaks(self) -> None:
    peaks = ProcessMemoryPeaks()
    peaks.record("pose", 120_000_000)
    peaks.record("pose", 110_000_000)
    peaks.record("barbell_tracking", 145_000_000)

    overall, stages = peaks.as_megabytes()

    self.assertEqual(overall, 145.0)
    self.assertEqual(stages, {"pose": 120.0, "barbell_tracking": 145.0})


if __name__ == "__main__":
  unittest.main()
