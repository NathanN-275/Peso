from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from .config import get_settings
from .generated_media_writes import _canonical_id, _require_receipt
from .storage_service import IMMUTABLE_CACHE_CONTROL_SECONDS, StorageService, _metadata_value, _parse_size_bytes
from .video_storage_paths import require_user_storage_path


IDENTITY = ('attempt_id', 'user_id', 'video_id', 'purpose', 'bucket', 'storage_path', 'source_path',
            'content_type', 'size_bytes', 'job_id', 'worker_id', 'attempt_count',
            'analysis_id', 'analysis_model_version', 'analysis_snapshot_hash', 'variant')
RETURNED = (*IDENTITY, 'state', 'published_at', 'cache_expires_at')


def _unavailable() -> HTTPException:
  return HTTPException(503, 'Analyzed video export is temporarily unavailable.')


def _rpc(client: Any, name: str, fields: dict[str, Any]) -> Any:
  try:
    return client.rpc(name, fields).execute().data
  except Exception:
    raise _unavailable() from None


def _timestamp(value: Any) -> datetime:
  try:
    timestamp = datetime.fromisoformat(value) if isinstance(value, str) else None
    if timestamp is None or timestamp.tzinfo is None or timestamp.utcoffset() is None:
      raise ValueError
    return timestamp.astimezone(timezone.utc)
  except (ValueError, TypeError, OverflowError):
    raise _unavailable() from None


def _published_row(data: Any, user_id: str, video_id: str, variant: str, bucket: str,
                   analysis_id: str | None = None) -> dict[str, Any] | None:
  if data == []:
    return None
  if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
    raise _unavailable()
  row = data[0]
  if row.keys() != set(RETURNED):
    raise _unavailable()
  try:
    attempt = _canonical_id(row['attempt_id'])
    analysis = _canonical_id(row['analysis_id'])
    path = f'{user_id}/exports/{video_id}-{analysis}-{variant}-{attempt}-h264-v1.mp4'
    if (row['user_id'] != user_id or row['video_id'] != video_id or row['variant'] != variant
        or row['bucket'] != bucket or row['purpose'] != 'analyzed_export'
        or row['content_type'] != 'video/mp4' or row['storage_path'] != path
        or not isinstance(row['source_path'], str)
        or row['state'] != 'succeeded' or any(row[key] is not None for key in ('job_id','worker_id','attempt_count'))
        or (analysis_id is not None and analysis != analysis_id)
        or type(row['size_bytes']) is not int or not 0 < row['size_bytes'] < 2**63
        or not isinstance(row['analysis_model_version'], str) or not row['analysis_model_version'].strip()
        or not isinstance(row['analysis_snapshot_hash'], str)
        or re.fullmatch('[0-9a-f]{64}', row['analysis_snapshot_hash']) is None):
      raise ValueError
    require_user_storage_path(row['source_path'], user_id, 'export source')
    published, expiry = _timestamp(row['published_at']), _timestamp(row['cache_expires_at'])
    if published > datetime.now(timezone.utc) or expiry <= max(published, datetime.now(timezone.utc)):
      raise ValueError
  except (ValueError, TypeError, KeyError, HTTPException):
    raise _unavailable() from None
  return row


def read_current_export(client: Any, *, user_id: str, video_id: str, variant: str, bucket: str,
                        analysis_id: str | None = None) -> dict[str, Any] | None:
  _canonical_id(user_id); _canonical_id(video_id)
  if analysis_id is not None:
    _canonical_id(analysis_id)
  if variant not in {'pose', 'barbell', 'pose-barbell'}:
    raise ValueError('Unsupported analyzed export variant.')
  data = _rpc(client, 'read_private_media_export', {
    'p_user_id': user_id, 'p_video_id': video_id, 'p_variant': variant,
    'p_bucket': bucket, 'p_analysis_id': analysis_id,
  })
  return _published_row(data, user_id, video_id, variant, bucket, analysis_id)


def require_cached_export_object(storage: StorageService, row: dict[str, Any]) -> None:
  # A missing-object response can hide permission errors; no read error is a cache miss.
  try:
    info = storage.get_object_info(row['storage_path'])
    if not isinstance(info, dict):
      raise ValueError
    size = _parse_size_bytes(_metadata_value(info, 'size', 'contentLength', 'content_length'))
    if type(size) is not int or size != row['size_bytes']:
      raise ValueError
  except Exception:
    raise _unavailable() from None


def write_analyzed_export(*, video: dict[str, Any], analysis: dict[str, Any], user_id: str,
                          variant: str, output_path: Path, storage: StorageService) -> str:
  owner, video_id, analysis_id = _canonical_id(user_id), _canonical_id(video.get('id')), _canonical_id(analysis.get('id'))
  if video.get('user_id') != owner or variant not in {'pose', 'barbell', 'pose-barbell'}:
    raise ValueError('An owned analyzed export is required.')
  source = require_user_storage_path(video.get('playback_path') or video.get('storage_path'), owner, 'export source')
  model, result = analysis.get('model_version'), analysis.get('result_json')
  if not isinstance(model, str) or not model.strip() or not isinstance(result, dict):
    raise ValueError('An exact analysis snapshot is required.')
  size = output_path.stat().st_size
  settings = get_settings()
  ttl = settings.export_cache_ttl_hours * 3600
  if size <= 0 or type(ttl) is not int or not 0 < ttl < 2**31:
    raise ValueError('Generated export bytes and a configured cache lifetime are required.')
  attempt = str(uuid4())
  path = f'{owner}/exports/{video_id}-{analysis_id}-{variant}-{attempt}-h264-v1.mp4'
  common = dict(attempt_id=attempt, user_id=owner, video_id=video_id, purpose='analyzed_export',
                bucket=storage.bucket, storage_path=path, source_path=source, content_type='video/mp4',
                size_bytes=size, job_id=None, worker_id=None, attempt_count=None)
  admitted = _rpc(storage.client, 'admit_private_media_export_write', {
    'p_attempt_id': attempt, 'p_user_id': owner, 'p_video_id': video_id, 'p_bucket': storage.bucket,
    'p_storage_path': path, 'p_source_path': source, 'p_analysis_id': analysis_id,
    'p_analysis_model_version': model, 'p_analysis_result': result, 'p_variant': variant, 'p_size_bytes': size,
    'p_max_user_bytes': settings.max_user_reserved_bytes, 'p_max_global_bytes': settings.object_storage_limit_bytes,
  })
  if not isinstance(admitted, list) or len(admitted) != 1 or not isinstance(admitted[0], dict):
    raise _unavailable()
  digest = admitted[0].get('analysis_snapshot_hash')
  if not isinstance(digest, str) or re.fullmatch('[0-9a-f]{64}', digest) is None:
    raise _unavailable()
  expected = {**common, 'analysis_id': analysis_id, 'analysis_model_version': model,
              'analysis_snapshot_hash': digest, 'variant': variant, 'state': 'dispatching',
              'published_at': None, 'cache_expires_at': None}
  try:
    _require_receipt(admitted, expected)
    persisted = (storage.client.table('private_media_generated_writes').select(','.join(RETURNED))
                 .eq('attempt_id', attempt).limit(2).execute()).data
    _require_receipt(persisted, expected)
  except Exception:
    raise _unavailable() from None
  try:
    storage.create_file(path, output_path, 'video/mp4', cache_control=IMMUTABLE_CACHE_CONTROL_SECONDS)
  except Exception:
    raise _unavailable() from None
  observed = _rpc(storage.client, 'observe_private_media_generated_write_success',
                  {'p_' + key: value for key, value in common.items()})
  if observed is not True:
    raise _unavailable()
  published = _rpc(storage.client, 'publish_private_media_export', {
    'p_attempt_id': attempt, 'p_user_id': owner, 'p_cache_ttl_seconds': ttl,
  })
  row = _published_row(published, owner, video_id, variant, storage.bucket, analysis_id)
  if row is None or any(type(row[key]) is not type(expected[key]) or row[key] != expected[key] for key in IDENTITY):
    raise _unavailable()
  try:
    persisted = (storage.client.table('private_media_generated_writes').select(','.join(RETURNED))
                 .eq('attempt_id', attempt).limit(2).execute()).data
    _require_receipt(persisted, row)
  except Exception:
    raise _unavailable() from None
  return path
