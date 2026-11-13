from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from app.jobs.analysis_worker import (
  AnalysisRunOutcome, AnalysisWorker, InlineAnalysisRunner,
  InterruptibleAnalysisRunner, _LeaseHeartbeat, _run_analysis_child,
)

JOB = {'id': '55555555-5555-5555-5555-555555555555', 'video_id': '11111111-1111-1111-1111-111111111111', 'status':'processing', 'attempt_count': 1}


def synthetic_analysis_child(directory, mode, worker_id, attempt_count, messages, startup):
  # Match the production child's isolated POSIX group without importing models.
  if os.name == 'posix':
    os.setsid()
  messages.put({'type':'ready','pid':os.getpid() if mode!='bad-pid' else -1,
                'pgid':os.getpgrp() if mode!='bad-group' else -1})
  if not startup.wait(10):return
  root = Path(directory)
  if mode == 'ignore-term':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
  descendant = None
  if mode == 'descendant':
    descendant = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    (root / 'descendant').write_text(str(descendant.pid))
  (root / 'pid').write_text(str(os.getpid()))
  messages.put({'type': 'stage', 'stage': 'pose'})
  if mode == 'success':
    messages.put({'type': 'completed'})
    return
  if mode == 'failure':
    messages.put({'type': 'failed', 'error_type': 'RuntimeError', 'error': 'pose failed'})
    return
  if mode == 'exit':
    return
  try:
    time.sleep(30)
    (root / 'late-publication').write_text('should not finish')
  finally:
    if descendant:
      descendant.terminate()
      descendant.wait(timeout=2)


class SyntheticSpawnContext:
  def __init__(self, *, await_ready=False):
    self.await_ready = await_ready
    self.messages = None
    self.context = multiprocessing.get_context('spawn')
    self.process = None

  def Queue(self):
    self.messages = self.context.Queue()
    return self.messages

  def Event(self):
    return self.context.Event()

  def Process(self, **kwargs):
    kwargs['target'] = synthetic_analysis_child
    self.process = self.context.Process(**kwargs)
    if self.await_ready:
      actual_start = self.process.start
      def start_after_ready():
        # Spawn pickles the process; keep this parent-only hook off that object.
        del self.process.start
        actual_start()
        # This test asserts malformed readiness, not interpreter startup latency.
        # Preserve the real child's packet for the supervisor's actual validation.
        read = self.messages.get
        try:
          packet = read(timeout=10)
        except BaseException:
          self.process.terminate(); self.process.join(timeout=2)
          if self.process.is_alive(): self.process.kill(); self.process.join(timeout=2)
          raise
        pending = [packet]
        def get(*args, **kwargs):
          return pending.pop() if pending else read(*args, **kwargs)
        self.messages.get = get
      self.process.start = start_after_ready
    return self.process


class ChildGroupStartupTest(unittest.TestCase):
  @unittest.skipUnless(os.name == 'posix', 'Production group startup is POSIX.')
  def test_actual_child_waits_for_group_ack_before_loading_analysis(self):
    messages=MagicMock();startup=MagicMock();startup.wait.return_value=False
    order=MagicMock();order.attach_mock(messages.put,'ready');order.attach_mock(startup.wait,'wait')
    with patch('app.jobs.analysis_worker.os.setsid') as setsid, \
         patch('app.jobs.analysis_worker.os.getpid',return_value=123), \
         patch('app.jobs.analysis_worker.os.getpgrp',return_value=123):
      order.attach_mock(setsid,'setsid')
      _run_analysis_child('video','job','worker',1,messages,startup)
    self.assertEqual([call[0] for call in order.mock_calls],['setsid','ready','wait'])
    messages.put.assert_called_once_with({'type':'ready','pid':123,'pgid':123})
    startup.wait.assert_called_once_with(10)

  @unittest.skipUnless(os.name == 'posix', 'Production group startup is POSIX.')
  def test_group_creation_failure_never_reports_ready_or_starts_work(self):
    messages=MagicMock();startup=MagicMock()
    with patch('app.jobs.analysis_worker.os.setsid',side_effect=OSError('synthetic setsid error')):
      with self.assertRaises(OSError):_run_analysis_child('video','job','worker',1,messages,startup)
    messages.put.assert_not_called();startup.wait.assert_not_called()


class LeaseHeartbeatTest(unittest.TestCase):
  def heartbeat(self, jobs):
    heartbeat = _LeaseHeartbeat(jobs=jobs, job_id='job', worker_id='worker', attempt_count=1, lease_seconds=60)
    heartbeat.interval_seconds = 0.01
    return heartbeat

  def test_denial_or_error_permanently_cancels_and_stops_renewing(self):
    for result in (False, RuntimeError('database unavailable')):
      with self.subTest(result=result):
        jobs = MagicMock()
        if isinstance(result, Exception):
          jobs.renew.side_effect = result
        else:
          jobs.renew.return_value = result
        heartbeat = self.heartbeat(jobs)
        heartbeat.start()
        try:
          self.assertTrue(heartbeat.cancel_event.wait(2))
          heartbeat.thread.join(timeout=1)
          self.assertFalse(heartbeat.thread.is_alive())
          jobs.renew.assert_called_once_with('job', 'worker', attempt_count=1, lease_seconds=60)
        finally:
          heartbeat.stop()

  def test_success_and_normal_shutdown_do_not_cancel(self):
    jobs = MagicMock(); renewed = threading.Event()
    jobs.renew.side_effect = lambda *args, **kwargs: renewed.set() or True
    heartbeat = self.heartbeat(jobs)
    heartbeat.start()
    try:
      self.assertTrue(renewed.wait(2))
    finally:
      heartbeat.stop()
    self.assertFalse(heartbeat.cancel_event.is_set())
    self.assertFalse(heartbeat.thread.is_alive())


class LeaseWorkerTest(unittest.TestCase):
  def worker(self, runner=None):
    jobs = MagicMock(); jobs.claim.return_value = dict(JOB); jobs.progress.return_value = True
    return AnalysisWorker(jobs=jobs, runner=runner or MagicMock(), worker_id='worker-fixture'), jobs

  def test_initial_progress_denial_or_error_never_starts_runner_or_updates_job(self):
    for error in (False, RuntimeError('database unavailable')):
      with self.subTest(error=error):
        worker, jobs = self.worker()
        if isinstance(error, Exception):jobs.progress.side_effect = error
        else:jobs.progress.return_value = error
        self.assertTrue(worker.run_once())
        worker.runner.run.assert_not_called()
        jobs.complete.assert_not_called(); jobs.fail.assert_not_called()

  def test_stage_denial_or_error_discards_late_success_and_failure(self):
    for denied in (False, RuntimeError('database unavailable')):
      for outcome in (AnalysisRunOutcome(True), AnalysisRunOutcome(False, 'late error', 'analysis_runtime', True)):
        with self.subTest(denied=denied, outcome=outcome):
          worker, jobs = self.worker()
          jobs.progress.side_effect = [True, denied]
          def run(*args, on_stage, cancel_event, **kwargs):
            on_stage('pose')
            self.assertTrue(cancel_event.is_set())
            on_stage('saving')
            return outcome
          worker.runner.run.side_effect = run
          self.assertTrue(worker.run_once())
          self.assertEqual(jobs.progress.call_count, 2)
          jobs.complete.assert_not_called(); jobs.fail.assert_not_called()

  def test_cancelled_runner_exception_never_publishes_failure(self):
    worker, jobs = self.worker()
    def run(*args, cancel_event, **kwargs):
      cancel_event.set()
      raise RuntimeError('runner stopped')
    worker.runner.run.side_effect = run
    self.assertTrue(worker.run_once())
    jobs.complete.assert_not_called(); jobs.fail.assert_not_called()

  def test_heartbeat_denial_or_error_reaches_active_runner(self):
    original = _LeaseHeartbeat.__init__
    def fast_heartbeat(heartbeat, **kwargs):
      original(heartbeat, **kwargs); heartbeat.interval_seconds = 0.01
    for result in (False, RuntimeError('renewal unavailable')):
      with self.subTest(result=result):
        worker, jobs = self.worker()
        if isinstance(result, Exception):jobs.renew.side_effect = result
        else:jobs.renew.return_value = result
        def run(*args, cancel_event, **kwargs):
          self.assertTrue(cancel_event.wait(2))
          return AnalysisRunOutcome(True)
        worker.runner.run.side_effect = run
        with patch.object(_LeaseHeartbeat, '__init__', fast_heartbeat):
          self.assertTrue(worker.run_once())
        jobs.complete.assert_not_called(); jobs.fail.assert_not_called()

  def test_inline_test_seam_checks_before_and_after_callback(self):
    event = threading.Event(); event.set(); analyzer = MagicMock()
    runner = InlineAnalysisRunner(analyzer)
    kwargs = dict(job_id='job', worker_id='worker', attempt_count=1, timeout_seconds=1, on_stage=lambda stage:None, cancel_event=event)
    self.assertEqual(runner.run('video', **kwargs).failure_class, 'analysis_lease_lost')
    analyzer.assert_not_called()
    event.clear(); analyzer.side_effect = lambda video:event.set()
    self.assertEqual(runner.run('video', **kwargs).failure_class, 'analysis_lease_lost')
    analyzer.assert_called_once_with('video')


@unittest.skipUnless(os.name == 'posix', 'Production process groups require POSIX.')
class LeaseRealChildTest(unittest.TestCase):
  def run_child(self, mode, *, on_stage=None, timeout=10, cancel_on_ready=False):
    event = threading.Event(); context = SyntheticSpawnContext()
    runner = InterruptibleAnalysisRunner(poll_seconds=0.05, memory_sample_seconds=0.01, rss_reader=lambda pid: 1234567)
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      observed_pid = []
      ready_at = []
      def stage(value):
        ready_at.append(time.monotonic())
        observed_pid.append(int((root/'pid').read_text()))
        if cancel_on_ready:event.set()
        if on_stage:on_stage(value,event,root)
      started = time.monotonic()
      with patch('app.jobs.analysis_worker.multiprocessing.get_context', return_value=context):
        result = runner.run(directory, job_id=mode, worker_id="worker", attempt_count=1, timeout_seconds=timeout, on_stage=stage, cancel_event=event)
      # Cancellation latency starts when the running child is observed;
      # interpreter startup under emulation is outside that contract.
      timing_start = ready_at[0] if ready_at and (cancel_on_ready or on_stage) else started
      elapsed = time.monotonic() - timing_start
      self.assertFalse(context.process.is_alive())
      self.assertFalse(any(t.name == f'cancel-{mode}' for t in threading.enumerate()))
      self.assertFalse((root/'late-publication').exists())
      if (root/'descendant').exists():
        pid = int((root/'descendant').read_text())
        deadline = time.monotonic()+2
        while time.monotonic()<deadline and self.process_alive(pid):time.sleep(0.02)
        self.assertFalse(self.process_alive(pid), f'descendant {pid} survived cleanup')
      return result,elapsed,observed_pid

  @staticmethod
  def process_alive(pid):
    try:
      stat = Path(f'/proc/{pid}/stat')
      if stat.exists() and stat.read_text().split()[2]=='Z':return False
      os.kill(pid,0)
      return True
    except ProcessLookupError:return False

  def test_cancelled_before_start_never_creates_process(self):
    event=threading.Event();event.set()
    with patch('app.jobs.analysis_worker.multiprocessing.get_context') as context:
      result=InterruptibleAnalysisRunner().run('unused',job_id='unused',worker_id='worker',attempt_count=1,timeout_seconds=10,on_stage=lambda stage:None,cancel_event=event)
    context.assert_not_called()
    self.assertEqual(result.failure_class,'analysis_lease_lost')

  def test_cancellation_stops_real_child_and_preserves_memory_measurements(self):
    result,elapsed,pids=self.run_child('sleep',cancel_on_ready=True)
    self.assertTrue(pids)
    self.assertLess(elapsed,4)
    self.assertEqual(result.failure_class,'analysis_lease_lost')
    self.assertFalse(result.retryable)
    self.assertEqual(result.peak_rss_bytes,1234567)
    self.assertEqual(result.peak_rss_mb,1.23)
    self.assertIn('starting',result.stage_peak_rss_bytes)

  def test_completion_message_cannot_win_over_cancellation(self):
    result,_,_=self.run_child('success',cancel_on_ready=True)
    self.assertFalse(result.succeeded)
    self.assertEqual(result.failure_class,'analysis_lease_lost')

  def test_watcher_stops_child_while_stage_rpc_is_still_blocked(self):
    def blocked_stage(stage,event,root):
      pid=int((root/'pid').read_text());event.set()
      deadline=time.monotonic()+1
      while self.process_alive(pid) and time.monotonic()<deadline:time.sleep(0.01)
      self.assertFalse(self.process_alive(pid),'child kept running while callback blocked')
    result,_,_=self.run_child('sleep',on_stage=blocked_stage)
    self.assertEqual(result.failure_class,'analysis_lease_lost')

  def test_watcher_escalates_even_while_stage_callback_is_blocked(self):
    def blocked_stage(stage,event,root):
      pid=int((root/'pid').read_text());event.set()
      deadline=time.monotonic()+3.5
      while self.process_alive(pid) and time.monotonic()<deadline:time.sleep(0.01)
      self.assertFalse(self.process_alive(pid),'SIGTERM-ignoring child survived blocked callback')
    result,elapsed,_=self.run_child('ignore-term',on_stage=blocked_stage)
    self.assertEqual(result.failure_class,'analysis_lease_lost')
    self.assertLess(elapsed,5)

  def test_unproven_readiness_never_signals_a_process_group(self):
    for mode in ('bad-pid','bad-group'):
      with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
        event=threading.Event();context=SyntheticSpawnContext(await_ready=True)
        with patch('app.jobs.analysis_worker.multiprocessing.get_context',return_value=context), \
             patch('app.jobs.analysis_worker.os.killpg') as killgroup:
          with self.assertRaises(RuntimeError):
            InterruptibleAnalysisRunner().run(directory,job_id=mode,worker_id="worker",attempt_count=1,timeout_seconds=5,on_stage=lambda stage:None,cancel_event=event)
        killgroup.assert_not_called()
        self.assertFalse(context.process.is_alive())

  def test_termination_escalates_for_child_ignoring_sigterm(self):
    result,elapsed,_=self.run_child('ignore-term',cancel_on_ready=True)
    self.assertEqual(result.failure_class,'analysis_lease_lost')
    self.assertLess(elapsed,5)

  def test_cancellation_also_stops_owned_subprocess_group(self):
    result,elapsed,_=self.run_child('descendant',cancel_on_ready=True)
    self.assertEqual(result.failure_class,'analysis_lease_lost')
    self.assertLess(elapsed,4)

  def test_deadline_still_terminates_real_child(self):
    result,elapsed,_=self.run_child('sleep',timeout=1)
    self.assertEqual(result.failure_class,'analysis_timeout')
    self.assertFalse(result.retryable)
    self.assertLess(elapsed,4)

  def test_success_failure_and_missing_completion_keep_original_classification(self):
    for mode,expected in [('success',None),('failure','analysis_runtime'),('exit','worker_process_exit')]:
      with self.subTest(mode=mode):
        result,_,_=self.run_child(mode)
        self.assertEqual(result.failure_class,expected)
        self.assertEqual(result.succeeded,mode=='success')
        self.assertEqual(result.peak_rss_bytes,1234567)


if __name__=='__main__':unittest.main()
