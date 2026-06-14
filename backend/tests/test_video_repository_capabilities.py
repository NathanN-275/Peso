from __future__ import annotations

import unittest

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


if __name__ == "__main__":
  unittest.main()
