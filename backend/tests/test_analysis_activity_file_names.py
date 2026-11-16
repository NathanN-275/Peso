import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.video_repository import VideoRepository


class AnalysisActivityFileNamesTest(unittest.TestCase):
  def fixture(self):
    repository = VideoRepository.__new__(VideoRepository)
    repository.client = MagicMock()
    query = repository.client.table.return_value
    for method in ("select", "eq", "in_"):
      getattr(query, method).return_value = query
    query.execute.return_value = SimpleNamespace(data=[])
    return repository, query

  def test_names_are_batched_and_bound_to_owner_and_owned_videos(self):
    repository, query = self.fixture()
    query.execute.return_value.data = [
      {"video_id": "one", "file_name": "C:\\private\\IMG_0013.MOV"},
      {"video_id": "two", "file_name": "../IMG_0013.MOV\n"},
      {"video_id": "other", "file_name": "other-owner.mov"},
    ]
    self.assertEqual(repository.analysis_source_file_names("owner", ["one", "two", "legacy"]),
                     {"one": "IMG_0013.MOV", "two": "IMG_0013.MOV"})
    query.eq.assert_called_once_with("user_id", "owner")
    query.in_.assert_any_call("video_id", ["one", "two", "legacy"])
    query.in_.assert_any_call("state", ["verified", "consumed"])
    query.execute.assert_called_once()

  def test_empty_list_never_queries_reservations(self):
    repository, _ = self.fixture()
    self.assertEqual(repository.analysis_source_file_names("owner", []), {})
    repository.client.table.assert_not_called()

  def test_only_known_missing_schema_errors_use_legacy_fallback(self):
    for code in ("42P01", "PGRST205", "42501", "network"):
      repository, query = self.fixture()
      error = RuntimeError("fixture")
      error.code = code
      query.execute.side_effect = error
      if code in {"42P01", "PGRST205"}:
        self.assertEqual(repository.analysis_source_file_names("owner", ["one"]), {})
      else:
        with self.assertRaises(RuntimeError):
          repository.analysis_source_file_names("owner", ["one"])
