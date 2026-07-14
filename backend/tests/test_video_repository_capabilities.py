from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.services.video_repository import VideoRepository


class Query:
  def __init__(self, error: Exception | None = None) -> None:
    self.error = error

  def select(self, *_args, **_kwargs):
    return self

  def limit(self, *_args, **_kwargs):
    return self

  def execute(self):
    if self.error:
      raise self.error
    return type("Response", (), {"data": []})()


class Client:
  def __init__(self, error: Exception | None = None) -> None:
    self.query = Query(error)

  def table(self, _name: str) -> Query:
    return self.query


class DatabaseError(RuntimeError):
  def __init__(self, message: str, code: str | None = None) -> None:
    super().__init__(message)
    self.code = code


class VideoRepositoryCapabilitiesTest(unittest.TestCase):
  def repository(self, error: Exception | None = None) -> VideoRepository:
    repository = VideoRepository.__new__(VideoRepository)
    repository.client = Client(error)
    return repository

  def test_supports_tracking_setup_when_column_can_be_selected(self) -> None:
    self.assertTrue(self.repository().supports_tracking_setup())

  def test_reports_missing_tracking_setup_for_postgres_undefined_column(self) -> None:
    error = DatabaseError("column videos.tracking_setup does not exist", code="42703")
    self.assertFalse(self.repository(error).supports_tracking_setup())

  def test_propagates_transient_database_errors(self) -> None:
    with self.assertRaises(DatabaseError):
      self.repository(DatabaseError("connection timeout", code="57014")).supports_tracking_setup()

  def test_update_video_rejects_cross_user_storage_path_fields_before_update(self) -> None:
    repository = VideoRepository.__new__(VideoRepository)
    repository.get_video = MagicMock(
      return_value={
        "id": "11111111-1111-1111-1111-111111111111",
        "user_id": "33333333-3333-3333-3333-333333333333",
      }
    )
    repository.client = MagicMock()

    with self.assertRaises(HTTPException) as raised:
      repository.update_video(
        "11111111-1111-1111-1111-111111111111",
        {"original_storage_path": "44444444-4444-4444-4444-444444444444/uploads/video.mp4"},
      )

    self.assertEqual(raised.exception.status_code, 403)
    repository.client.table.assert_not_called()

  def test_update_video_allows_owned_storage_path_fields(self) -> None:
    repository = VideoRepository.__new__(VideoRepository)
    repository.get_video = MagicMock(
      return_value={
        "id": "11111111-1111-1111-1111-111111111111",
        "user_id": "33333333-3333-3333-3333-333333333333",
      }
    )
    response = type("Response", (), {"data": [{"id": "11111111-1111-1111-1111-111111111111"}]})()
    repository.client = MagicMock()
    repository.client.table.return_value.update.return_value.eq.return_value.execute.return_value = response

    result = repository.update_video(
      "11111111-1111-1111-1111-111111111111",
      {"playback_path": "33333333-3333-3333-3333-333333333333/playback/video.mp4"},
    )

    self.assertEqual(result["id"], "11111111-1111-1111-1111-111111111111")
    repository.client.table.assert_called_once_with("videos")


if __name__ == "__main__":
  unittest.main()
