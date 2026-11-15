from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID
import unittest

from fastapi import HTTPException
from app.routes.videos import DeleteSavedLiftsRequest, delete_saved_lifts
from app.services.video_repository import VideoRepository

USER='33333333-3333-3333-3333-333333333333'
VIDEO='11111111-1111-1111-1111-111111111111'
SECOND='22222222-2222-2222-2222-222222222222'
OTHER='44444444-4444-4444-4444-444444444444'


def row(video=VIDEO, completed=False):
  return {'video_id':video,'user_id':USER,'completed':completed,'task':None if completed else {
    'video_id':video,'user_id':USER,'delete_metadata':True,'storage_paths':[f'{USER}/source/{video}.mp4'],
    'archive_paths':[],'export_prefixes':[f'{USER}/exports/{video}-']}}


class SavedDeletionReceiptsTest(unittest.TestCase):
  def setUp(self):
    self.repo=VideoRepository.__new__(VideoRepository);self.repo.client=MagicMock()
    self.responses=[[row()],[row(completed=True)]];self.events=[]
    def execute():
      self.events.append(self.repo.client.rpc.call_args.args[0])
      response=self.responses.pop(0)
      if isinstance(response,Exception):raise response
      return SimpleNamespace(data=deepcopy(response))
    self.repo.client.rpc.return_value.execute.side_effect=execute
    self.cleanup=MagicMock();self.cleanup.process_deletions.return_value=SimpleNamespace(deleted_count=1,errors=[])
    self.factory=MagicMock(return_value=self.cleanup)

  def run_route(self, ids=None):
    with patch('app.routes.videos.VideoRepository',return_value=self.repo),patch('app.routes.videos.StorageCleanupService',self.factory),patch('app.routes.videos.StorageService') as legacy:
      try:return delete_saved_lifts(DeleteSavedLiftsRequest(lift_ids=[UUID(v) for v in (ids or [VIDEO])]),USER)
      finally:legacy.assert_not_called();self.repo.client.table.assert_not_called()

  def test_revocation_commit_precedes_targeted_cleanup_and_completion_readback(self):
    def clean(tasks):
      self.events.append('cleanup');self.assertEqual(tasks,[row()['task']]);return SimpleNamespace(deleted_count=1,errors=[])
    self.cleanup.process_deletions.side_effect=clean
    result=self.run_route()
    self.assertEqual(result.deleted_count,1);self.assertEqual(str(result.deleted_lift_ids[0]),VIDEO)
    self.assertEqual(self.events,['revoke_saved_lifts','cleanup','read_saved_lift_deletion_receipts'])

  def test_deduplicates_preserves_request_order_and_uses_full_set_proofs(self):
    self.responses=[[row(),row(SECOND)],[row(completed=True),row(SECOND,True)]]
    self.cleanup.process_deletions.return_value.deleted_count=2
    result=self.run_route([SECOND,VIDEO,SECOND]);self.assertEqual([str(v) for v in result.deleted_lift_ids],[SECOND,VIDEO])
    for call in self.repo.client.rpc.call_args_list:self.assertEqual(call.args[1],{'p_user_id':USER,'p_video_ids':[SECOND,VIDEO]})

  def test_all_completed_retry_does_not_construct_storage_or_cleanup(self):
    self.responses=[[row(completed=True)],[row(completed=True)]]
    self.assertEqual(self.run_route().deleted_count,1);self.factory.assert_not_called()

  def test_partial_batch_original_retry_skips_already_completed_member(self):
    self.responses=[[row(),row(SECOND)],[row(completed=True),row(SECOND)],[row(completed=True),row(SECOND,True)]]
    self.cleanup.process_deletions.side_effect=[SimpleNamespace(deleted_count=1,errors=['second failed']),SimpleNamespace(deleted_count=1,errors=[])]
    with self.assertRaises(HTTPException) as error:self.run_route([VIDEO,SECOND])
    self.assertEqual(error.exception.status_code,503)
    result=self.run_route([VIDEO,SECOND]);self.assertEqual(result.deleted_count,2)
    self.assertEqual(self.cleanup.process_deletions.call_args_list[1].args[0],[row(SECOND)['task']])

  def test_rejects_missing_foreign_unsaved_and_unavailable_rpc_before_storage(self):
    for code,expected in [('42501',404),('55000',409),('22023',400),('',503),('PGRST202',503)]:
      with self.subTest(code=code):
        error=RuntimeError('provider error');error.code=code;self.responses=[error]
        with self.assertRaises(HTTPException) as raised:self.run_route()
        self.assertEqual(raised.exception.status_code,expected);self.factory.assert_not_called()

  def test_malformed_revocation_partition_never_reaches_storage(self):
    bad=[None,[],True,[row(),row()],[{**row(),'video_id':OTHER}],[{**row(),'user_id':OTHER}],
         [{**row(),'completed':'false'}],[{**row(),'task':None}],[{**row(completed=True),'task':row()['task']}],
         [{**row(),'extra':True}],[{**row(),'task':{**row()['task'],'delete_metadata':False}}],
         [{**row(),'task':{**row()['task'],'storage_paths':[f'{OTHER}/secret.mp4']}}],
         [{**row(),'task':{**row()['task'],'export_prefixes':[]}}]]
    for data in bad:
      with self.subTest(data=data):
        self.responses=[data]
        with self.assertRaises(HTTPException) as error:self.run_route()
        self.assertEqual(error.exception.status_code,503);self.factory.assert_not_called()

  def test_cleanup_failures_or_unproved_counts_do_not_return_success(self):
    for report in [SimpleNamespace(errors=['retry'],deleted_count=1),SimpleNamespace(errors=[],deleted_count=0),SimpleNamespace(errors=[],deleted_count=True),RuntimeError('bucket unavailable')]:
      self.responses=[[row()]]
      self.cleanup.process_deletions.side_effect=report if isinstance(report,Exception) else None
      self.cleanup.process_deletions.return_value=report
      with self.subTest(report=report),self.assertRaises(HTTPException) as error:self.run_route()
      self.assertEqual(error.exception.status_code,503)
      self.assertEqual(self.events[-1],'revoke_saved_lifts')

  def test_completion_requires_full_owned_proof_and_absent_tasks(self):
    for proof in [None,[],[row(OTHER,True)],[{**row(completed=True),'user_id':OTHER}],
                  [{**row(completed=True),'completed':'true'}],[row()], [{**row(completed=True),'completed':False}]]:
      with self.subTest(proof=proof):
        self.responses=[[row()],proof]
        with self.assertRaises(HTTPException) as error:self.run_route()
        self.assertEqual(error.exception.status_code,503)

  def test_exact_rpc_contract_has_no_legacy_delete_fallback(self):
    self.run_route()
    self.repo.client.rpc.assert_any_call('revoke_saved_lifts',{'p_user_id':USER,'p_video_ids':[VIDEO]})
    self.repo.client.rpc.assert_any_call('read_saved_lift_deletion_receipts',{'p_user_id':USER,'p_video_ids':[VIDEO]})
