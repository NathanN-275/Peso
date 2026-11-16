import unittest
from unittest.mock import patch
from app.services.phase_timing import record_queue_wait, video_phase_timing
from datetime import datetime, timezone


class VideoPhaseTimingTest(unittest.TestCase):
  def test_queue_wait_uses_server_creation_time_and_ignores_unknown_time(self):
    with patch('app.services.phase_timing.datetime') as clock, \
         patch('app.services.phase_timing.logger.info') as log:
      clock.fromisoformat.side_effect = datetime.fromisoformat
      clock.now.return_value = datetime(2026, 11, 16, 1, 0, 5, tzinfo=timezone.utc)
      record_queue_wait('2026-11-16T01:00:00Z', 'video')
      self.assertEqual(log.call_args.args[1:], ('queue_wait', 'video', 5000))
      log.reset_mock()
      for value in (None, 'invalid', '2026-11-16T01:00:00'):
        record_queue_wait(value, 'video')
      log.assert_not_called()

  def test_timing_is_recorded_on_both_success_and_failure(self):
    for fails in (False, True):
      with patch('app.services.phase_timing.time.perf_counter', side_effect=[1.0, 1.125]), \
           patch('app.services.phase_timing.logger.info') as log:
        if fails:
          with self.assertRaisesRegex(ValueError, 'fixture'):
            with video_phase_timing('verification_probe', 'reservation'):
              raise ValueError('fixture')
        else:
          with video_phase_timing('verification_probe', 'reservation'):
            pass
        self.assertEqual(log.call_args.args[1:], ('verification_probe', 'reservation', 125))
