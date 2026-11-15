from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
from fastapi import HTTPException
from postgrest import SyncPostgrestClient

from app.routes.videos import SaveVideoRequest, save_video
from app.services.video_repository import VideoRepository


VIDEO_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "33333333-3333-3333-3333-333333333333"
DISCARDED_AT = "2026-10-25T20:00:00+00:00"


class ConditionalQuery:
  def __init__(self, row, *, before_write=None, error=None):
    self.row = row
    self.before_write = before_write
    self.error = error
    self.fields = None
    self.filters = []
    self.executions = 0

  def update(self, fields):
    self.fields = dict(fields)
    return self

  def eq(self, column, value):
    self.filters.append((column, "eq", value))
    return self

  def is_(self, column, value):
    self.filters.append((column, "is", value))
    return self

  def execute(self):
    self.executions += 1
    if self.error:
      raise self.error
    if self.before_write:
      self.before_write(self.row)
    if not self.row:
      return SimpleNamespace(data=[])
    for column, operator, value in self.filters:
      if operator == "eq" and self.row.get(column) != value:
        return SimpleNamespace(data=[])
      if operator == "is" and value == "null" and self.row.get(column) is not None:
        return SimpleNamespace(data=[])
    self.row.update(self.fields)
    return SimpleNamespace(data=[dict(self.row)])


class VideoSaveStateTest(unittest.TestCase):
  def repository(self, row=None, **kwargs):
    row = {"id": VIDEO_ID, "user_id": USER_ID, "discarded_at": None} if row is None else row
    repository = VideoRepository.__new__(VideoRepository)
    query = ConditionalQuery(row, **kwargs)
    repository.client = MagicMock()
    repository.client.table.return_value = query
    return repository, query

  def save(self, repository, **kwargs):
    return repository.mark_saved(VIDEO_ID, performed_reps=5, load_value=0, load_unit="kg", **kwargs)

  def test_save_updates_active_row_once_without_clearing_tombstone(self):
    repository, query = self.repository()
    result = self.save(repository)
    self.assertEqual(query.executions, 1)
    self.assertEqual(query.filters, [("id", "eq", VIDEO_ID), ("discarded_at", "is", "null")])
    self.assertNotIn("discarded_at", query.fields)
    self.assertEqual(result["save_state"], "saved")
    self.assertIs(result["is_saved"], True)
    self.assertEqual(result["performed_reps"], 5)
    self.assertEqual(result["load_value"], 0)
    self.assertEqual(result["load_unit"], "kg")
    self.assertIsNone(result["expires_at"])
    self.assertTrue(result["saved_at"])

  def test_save_preserves_supported_metadata_and_storage_validation_boundary(self):
    repository, query = self.repository()
    metadata = {"user_notes": "Keep torso steady", "weight": 0, "weight_unit": "kg", "corrected_rep_count": 0}
    with patch.object(repository, "_validate_storage_path_update", wraps=repository._validate_storage_path_update) as validate:
      result = self.save(repository, metadata=metadata)
    for key, value in metadata.items():
      self.assertEqual(result[key], value)
    validate.assert_called_once_with(VIDEO_ID, query.fields)
    self.assertEqual(metadata, {"user_notes": "Keep torso steady", "weight": 0, "weight_unit": "kg", "corrected_rep_count": 0})

  def test_save_rejects_lifecycle_identity_and_unknown_metadata_before_write(self):
    for field in ("discarded_at", "save_state", "is_saved", "saved_at", "expires_at", "status", "storage_state", "id", "user_id", "performed_reps", "playback_path", "unknown"):
      with self.subTest(field=field):
        repository, query = self.repository()
        with self.assertRaises(HTTPException) as raised:
          self.save(repository, metadata={field: None})
        self.assertEqual(raised.exception.status_code, 400)
        repository.client.table.assert_not_called()
        self.assertEqual(query.executions, 0)

  def test_save_does_not_bypass_storage_path_validation(self):
    repository, query = self.repository()
    error = HTTPException(status_code=403, detail="Invalid storage path")
    with patch.object(repository, "_validate_storage_path_update", side_effect=error):
      with self.assertRaises(HTTPException) as raised:
        self.save(repository)
    self.assertIs(raised.exception, error)
    self.assertEqual(query.executions, 0)

  def test_save_rejects_previously_discarded_row_without_mutation(self):
    row = {"id": VIDEO_ID, "user_id": USER_ID, "discarded_at": DISCARDED_AT, "save_state": "pending", "is_saved": False}
    before = dict(row)
    repository, query = self.repository(row)
    with self.assertRaises(HTTPException) as raised:
      self.save(repository)
    self.assertEqual(raised.exception.status_code, 409)
    self.assertEqual(row, before)
    self.assertEqual(query.executions, 1)

  def test_save_rejects_empty_conditional_result(self):
    repository, query = self.repository({})
    with self.assertRaises(HTTPException) as raised:
      self.save(repository)
    self.assertEqual(raised.exception.status_code, 409)
    self.assertIn("no longer available", raised.exception.detail)
    self.assertEqual(query.executions, 1)

  def test_route_save_cannot_resurrect_discard_after_owned_video_read(self):
    def discard_at_write(row):
      row.update(discarded_at=DISCARDED_AT, save_state="pending", is_saved=False)
    repository, query = self.repository(before_write=discard_at_write)
    repository.get_video = MagicMock(side_effect=lambda _video_id: dict(query.row))
    with patch("app.routes.videos.VideoRepository", return_value=repository):
      with self.assertRaises(HTTPException) as raised:
        save_video(UUID(VIDEO_ID), SaveVideoRequest(performed_reps=5), USER_ID)
    self.assertEqual(raised.exception.status_code, 409)
    repository.get_video.assert_called_once_with(VIDEO_ID)
    self.assertEqual(query.row["discarded_at"], DISCARDED_AT)
    self.assertEqual(query.row["save_state"], "pending")
    self.assertIs(query.row["is_saved"], False)
    self.assertEqual(query.executions, 1)

  def test_save_propagates_missing_column_and_transient_errors_without_fallback(self):
    for error in (RuntimeError("column discarded_at does not exist"), httpx.ReadTimeout("synthetic database timeout")):
      with self.subTest(error=type(error).__name__):
        repository, query = self.repository(error=error)
        with self.assertRaises(type(error)) as raised:
          self.save(repository)
        self.assertIs(raised.exception, error)
        self.assertEqual(query.executions, 1)
        self.assertNotIn("discarded_at", query.fields)

  def test_discard_writes_durable_tombstone_once(self):
    repository, query = self.repository()
    result = repository.mark_discarded(VIDEO_ID)
    self.assertTrue(result["discarded_at"])
    self.assertEqual(result["save_state"], "pending")
    self.assertIs(result["is_saved"], False)
    self.assertEqual(query.executions, 1)

  def test_discard_propagates_missing_column_and_transient_errors_without_fallback(self):
    for error in (RuntimeError("column discarded_at does not exist"), httpx.ReadTimeout("synthetic database timeout")):
      with self.subTest(error=type(error).__name__):
        repository, query = self.repository(error=error)
        with self.assertRaises(type(error)) as raised:
          repository.mark_discarded(VIDEO_ID)
        self.assertIs(raised.exception, error)
        self.assertEqual(query.executions, 1)
        self.assertTrue(query.fields["discarded_at"])

  def test_real_postgrest_client_sends_one_conditional_patch_without_tombstone_reset(self):
    requests = []
    def handle(request):
      requests.append(request)
      payload = json.loads(request.content)
      return httpx.Response(200, json=[{"id": VIDEO_ID, **payload}], request=request)
    def create_session(_client, base_url, headers, *_args, **_kwargs):
      return httpx.Client(base_url=base_url, headers=headers, transport=httpx.MockTransport(handle))
    with patch.object(SyncPostgrestClient, "create_session", create_session):
      client = SyncPostgrestClient("https://database-fixture.invalid/rest/v1")
    try:
      repository = VideoRepository.__new__(VideoRepository)
      repository.client = client
      result = self.save(repository, metadata={"user_notes": "synthetic note"})
    finally:
      client.session.close()
    self.assertEqual(len(requests), 1)
    request = requests[0]
    self.assertEqual(request.method, "PATCH")
    self.assertEqual(request.url.path, "/rest/v1/videos")
    self.assertEqual(request.url.params["id"], "eq." + VIDEO_ID)
    self.assertEqual(request.url.params["discarded_at"], "is.null")
    self.assertNotIn("discarded_at", json.loads(request.content))
    self.assertIn("return=representation", request.headers.get("Prefer", ""))
    self.assertEqual(result["user_notes"], "synthetic note")


if __name__ == "__main__":
  unittest.main()
