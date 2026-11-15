from __future__ import annotations

import threading
import unittest
from unittest.mock import MagicMock, patch

from app.jobs.analysis_worker import AnalysisWorker, _run_analysis_child
from app.services.analysis_job_repository import AnalysisJobRepository
from app.services.video_repository import VideoRepository

VIDEO = '11111111-1111-1111-1111-111111111111'
JOB = '55555555-5555-5555-5555-555555555555'
CLAIM = {'id': JOB, 'video_id': VIDEO, 'status': 'processing', 'attempt_count': 2}


class AnalysisPublicationTest(unittest.TestCase):
  def repository(self):
    repo = VideoRepository.__new__(VideoRepository)
    repo.client = MagicMock()
    repo.bind_analysis_lease(JOB, 'worker', 2)
    repo.client.rpc.return_value.execute.return_value.data = {'video': {'id': VIDEO,'status':'completed'}, 'analysis': {'id':'66666666-6666-6666-6666-666666666666','video_id':VIDEO,'model_version':'model-v1','result_json':{'reps':2}}}
    return repo

  def test_bound_updates_and_results_only_use_the_atomic_rpc(self):
    repo = self.repository()
    repo.update_video(VIDEO, {'status': 'completed'})
    repo.save_analysis_result(VIDEO, 'model-v1', {'reps': 2})
    repo.client.table.assert_not_called()
    first, second = repo.client.rpc.call_args_list
    self.assertEqual(first.args, ('publish_video_analysis', {'p_job_id': JOB, 'p_worker_id': 'worker', 'p_attempt_count': 2,
      'p_video_id': VIDEO, 'p_fields': {'status': 'completed'}, 'p_model_version': None, 'p_result_json': None}))
    self.assertEqual(second.args[1]['p_result_json'], {'reps': 2})
    self.assertEqual(second.args[1]['p_fields'], {})

  def test_unleased_result_write_has_no_legacy_fallback(self):
    repo = VideoRepository.__new__(VideoRepository);repo.client = MagicMock()
    with self.assertRaisesRegex(RuntimeError, 'claimed analysis attempt'):
      repo.save_analysis_result(VIDEO, 'model', {})
    repo.client.table.assert_not_called();repo.client.rpc.assert_not_called()

  def test_missing_rpc_denial_or_bad_result_cannot_fall_back(self):
    for response in (None, [], True, {'video':{}}, {'video':{'id':'other'}}, {'video':{'id':VIDEO},'analysis':{'video_id':'other'}}):
      with self.subTest(response=response):
        repo = self.repository();repo.client.rpc.return_value.execute.return_value.data = response
        with self.assertRaises(RuntimeError):repo.save_analysis_result(VIDEO,'model',{})
        repo.client.table.assert_not_called()
    repo = self.repository();repo.client.rpc.return_value.execute.side_effect=RuntimeError('missing RPC')
    with self.assertRaisesRegex(RuntimeError,'missing RPC'):repo.update_video(VIDEO,{'status':'processing'})
    repo.client.table.assert_not_called()

  def test_binding_rejects_incomplete_or_ambiguous_attempts(self):
    for job, worker, attempt in [('invalid','worker',1),('00000000-0000-0000-0000-000000000000','worker',1),
                                 (JOB,'',1),(JOB,' worker',1),(JOB,'worker',True),(JOB,'worker',0),(JOB,'worker',None)]:
      with self.subTest(job=job,worker=worker,attempt=attempt):
        with self.assertRaises((ValueError,TypeError,AttributeError)):
          self.repository().bind_analysis_lease(job,worker,attempt)

  def test_generated_write_binding_requires_a_lease_and_cannot_mutate_repository_state(self):
    repo = VideoRepository.__new__(VideoRepository)
    with self.assertRaisesRegex(RuntimeError, "claimed analysis attempt"):
      repo.analysis_write_binding()
    repo.bind_analysis_lease(JOB, 'worker', 2)
    binding = repo.analysis_write_binding()
    self.assertEqual(binding, {'p_job_id': JOB, 'p_worker_id': 'worker', 'p_attempt_count': 2})
    binding['p_attempt_count'] = 99
    self.assertEqual(repo.analysis_write_binding()['p_attempt_count'], 2)

  def test_update_acknowledgement_requires_every_requested_field(self):
    variants=[{}, {'status':'failed'}, {'playback_path':'other'}, {'thumbnail_path':None}]
    for returned in variants:
      with self.subTest(returned=returned):
        repo=self.repository();repo.client.rpc.return_value.execute.return_value.data={'video':{'id':VIDEO,**returned}}
        with self.assertRaises(RuntimeError):repo.update_video(VIDEO,{'status':'completed','playback_path':'owner/asset.mp4'})
    repo=self.repository()
    repo.client.rpc.return_value.execute.return_value.data={'video':{'id':VIDEO,'fps':29.97,'duration_ms':1200,'storage_optimized_at':'2026-10-27T12:00:00Z'}}
    repo.update_video(VIDEO,{'fps':29.97002997,'duration_ms':1200,'storage_optimized_at':'2026-10-27T08:00:00-04:00'})

  def test_result_acknowledgement_requires_canonical_identity_model_and_payload(self):
    baseline={'id':'66666666-6666-6666-6666-666666666666','video_id':VIDEO,'model_version':'model-v1','result_json':{'reps':2}}
    for change in ({'id':'result'},{'id':'00000000-0000-0000-0000-000000000000'}, {'model_version':'other'},
                   {'result_json':None},{'result_json':{'reps':1}}):
      with self.subTest(change=change):
        repo=self.repository();repo.client.rpc.return_value.execute.return_value.data={'video':{'id':VIDEO},'analysis':{**baseline,**change}}
        with self.assertRaises(RuntimeError):repo.save_analysis_result(VIDEO,'model-v1',{'reps':2})

  def test_worker_normalizes_its_identity_before_claim_and_rejects_blank_names(self):
    for invalid in ('',' ',False):
      with self.subTest(invalid=invalid):
        with self.assertRaises(ValueError):AnalysisWorker(jobs=MagicMock(),worker_id=invalid)
    jobs=MagicMock();jobs.claim.return_value=None
    worker=AnalysisWorker(jobs=jobs,worker_id=' worker ')
    self.assertEqual(worker.worker_id,'worker');self.assertFalse(worker.run_once())
    jobs.claim.assert_called_once_with('worker',lease_seconds=3600)

  def test_control_calls_send_the_exact_claim_generation(self):
    repo=AnalysisJobRepository.__new__(AnalysisJobRepository);repo.client=MagicMock()
    repo.client.rpc.return_value.execute.return_value.data=True
    repo.renew(JOB,'worker',attempt_count=2,lease_seconds=60)
    repo.progress(JOB,'worker','pose',attempt_count=2)
    repo.complete(JOB,'worker',attempt_count=2)
    repo.client.rpc.return_value.execute.return_value.data='retry_wait'
    repo.fail(JOB,'worker','error',attempt_count=2,failure_class='analysis_runtime',retryable=True)
    self.assertEqual(len(repo.client.rpc.call_args_list),4)
    for call in repo.client.rpc.call_args_list:self.assertEqual(call.args[1]['p_attempt_count'],2)

  def test_lease_control_rejects_truthy_junk(self):
    repo=AnalysisJobRepository.__new__(AnalysisJobRepository);repo.client=MagicMock()
    for value in ('false','true',1,0,None,[],[True,False],[[True]],{'unexpected':True},{'complete_video_analysis_job':True,'other':False}):
      with self.subTest(value=value):
        repo.client.rpc.return_value.execute.return_value.data=value
        with self.assertRaises(RuntimeError):repo.complete(JOB,'worker',attempt_count=2)
    for value in (True,False):
      repo.client.rpc.return_value.execute.return_value.data=value
      self.assertIs(repo.complete(JOB,'worker',attempt_count=2),value)

  def test_malformed_claim_never_starts_heartbeat_or_child(self):
    variants=[None, {}, {**CLAIM,'id':'wrong'}, {**CLAIM,'video_id':'00000000-0000-0000-0000-000000000000'},
              {**CLAIM,'attempt_count':True},{**CLAIM,'attempt_count':0},{**CLAIM,'attempt_count':None},
              {**CLAIM,'status':'queued'}]
    for row in variants[1:]:
      with self.subTest(row=row):
        jobs=MagicMock();jobs.claim.return_value=row;runner=MagicMock()
        worker=AnalysisWorker(jobs=jobs,runner=runner,worker_id='worker')
        with patch('app.jobs.analysis_worker._LeaseHeartbeat') as heartbeat:
          with self.assertRaises(RuntimeError):worker.run_once()
        heartbeat.assert_not_called();runner.run.assert_not_called();jobs.fail.assert_not_called()

  def test_child_passes_attempt_identity_to_pipeline(self):
    messages=MagicMock();startup=MagicMock();startup.wait.return_value=True
    pipeline=MagicMock()
    with patch('app.jobs.analysis_worker.os.setsid'), patch.dict('sys.modules',{'app.analysis.pipeline':pipeline}):
      _run_analysis_child(VIDEO,JOB,'worker',2,messages,startup)
    args=pipeline.analyze_video.call_args
    self.assertEqual(args.args,(VIDEO,))
    self.assertEqual({key:args.kwargs[key] for key in ['job_id','worker_id','attempt_count']},
                     {'job_id':JOB,'worker_id':'worker','attempt_count':2})


if __name__=='__main__':unittest.main()
