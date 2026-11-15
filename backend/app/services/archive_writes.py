from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any

from fastapi import HTTPException

from .analyzed_export_writes import _timestamp, require_cached_export_object
from .config import Settings
from .generated_media_writes import _canonical_id, _require_receipt
from .storage_service import IMMUTABLE_CACHE_CONTROL_SECONDS, StorageService
from .video_storage_paths import require_user_storage_path


PLAN = ('user_id', 'archive_job_id', 'archive_attempt_count', 'archive_started_at', 'video_ids', 'member_snapshots')
MEMBER = {'video_id', 'source_path', 'analysis_id', 'analysis_model_version', 'analysis_snapshot_hash', 'variant', 'entry_name'}
ARTIFACT = {'artifact_bucket', 'artifact_path', 'artifact_size_bytes', 'artifact_sha256'}
RETURNED = ('attempt_id', 'user_id', 'purpose', 'bucket', 'storage_path', 'content_type', 'size_bytes',
            'archive_job_id', 'archive_attempt_count', 'archive_started_at', 'video_ids', 'member_snapshots',
            'content_sha256', 'state', 'created_at', 'published_at', 'cache_expires_at')


def unavailable() -> HTTPException:
  return HTTPException(503, 'Saved Lift archive is temporarily unavailable.')


def _rpc(client: Any, name: str, fields: dict[str, Any]) -> Any:
  try:
    return client.rpc(name, fields).execute().data
  except Exception:
    raise unavailable() from None


def _hash(value: Any) -> bool:
  return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def _positive(value: Any) -> bool:
  return type(value) is int and 0 < value < 2**63


def _plan(value: Any, owner: str, job_id: str, *, artifacts: bool = False) -> dict[str, Any]:
  try:
    if not isinstance(value, dict) or value.keys() != set(PLAN):
      raise ValueError
    _canonical_id(owner); _canonical_id(job_id)
    ids, members = value['video_ids'], value['member_snapshots']
    if (value['user_id'] != owner or value['archive_job_id'] != job_id
        or not _positive(value['archive_attempt_count'])
        or _timestamp(value['archive_started_at']) > datetime.now(timezone.utc)
        or not isinstance(ids, list) or not 1 <= len(ids) <= 50 or len(set(ids)) != len(ids)
        or not isinstance(members, list) or len(members) != len(ids)):
      raise ValueError
    for index, (video_id, member) in enumerate(zip(ids, members), start=1):
      _canonical_id(video_id)
      if not isinstance(member, dict) or member.keys() != MEMBER | (ARTIFACT if artifacts else set()):
        raise ValueError
      source = require_user_storage_path(member['source_path'], owner, 'archive source')
      _canonical_id(member['analysis_id'])
      if (member['video_id'] != video_id or not isinstance(member['analysis_model_version'], str)
          or not member['analysis_model_version'].strip() or not _hash(member['analysis_snapshot_hash'])
          or member['variant'] not in {'clean', 'pose', 'barbell', 'pose-barbell'}):
        raise ValueError
      suffix = PurePosixPath(source).suffix.lower() if member['variant'] == 'clean' else '.mp4'
      if (suffix not in {'.mp4', '.mov', '.m4v', '.webm'} or not isinstance(member['entry_name'], str)
          or re.fullmatch(rf'{index:02d}-[a-z0-9]+(?:-[a-z0-9]+)*-{re.escape(video_id)}{re.escape(suffix)}', member['entry_name']) is None):
        raise ValueError
      if artifacts:
        require_user_storage_path(member['artifact_path'], owner, 'archive member')
        if (not isinstance(member['artifact_bucket'], str)
            or re.fullmatch('[a-z0-9][a-z0-9._-]{0,99}', member['artifact_bucket']) is None
            or not _positive(member['artifact_size_bytes']) or not _hash(member['artifact_sha256'])
            or (member['variant'] == 'clean' and member['artifact_path'] != source)):
          raise ValueError
  except (ValueError, TypeError, KeyError, HTTPException):
    raise unavailable() from None
  return value


def _receipt(data: Any, expected: dict[str, Any]) -> None:
  _require_receipt(data, expected)
  if json.dumps(data[0], sort_keys=True, allow_nan=False) != json.dumps(expected, sort_keys=True, allow_nan=False):
    raise RuntimeError('Archive receipt does not match its complete typed manifest.')


def plan_archive(storage: StorageService, job: dict[str, Any]) -> dict[str, Any]:
  owner, job_id = _canonical_id(job.get('user_id')), _canonical_id(job.get('id'))
  plan = _plan(_rpc(storage.client, 'plan_private_media_archive',
                    {'p_user_id': owner, 'p_archive_job_id': job_id}), owner, job_id)
  if (job.get('status') != 'processing' or plan['video_ids'] != job.get('video_ids')
      or type(job.get('attempts')) is not int or plan['archive_attempt_count'] != job['attempts']
      or _timestamp(plan['archive_started_at']) != _timestamp(job.get('started_at'))):
    raise unavailable()
  return plan


def file_sha256(path: Path) -> str:
  with path.open('rb') as source:
    return hashlib.file_digest(source, 'sha256').hexdigest()


def _published(value: Any, owner: str, job_id: str) -> dict[str, Any]:
  try:
    if not isinstance(value, dict) or value.keys() != set(RETURNED):
      raise ValueError
    _plan({key: value[key] for key in PLAN}, owner, job_id, artifacts=True)
    attempt = _canonical_id(value['attempt_id'])
    if (value['purpose'] != 'archive' or value['bucket'] != 'saved-lift-exports'
        or value['storage_path'] != f'{owner}/{job_id}-{attempt}.zip'
        or value['content_type'] != 'application/zip' or not _positive(value['size_bytes'])
        or not _hash(value['content_sha256']) or value['state'] != 'succeeded'):
      raise ValueError
    created, published, expiry = (_timestamp(value[key]) for key in ('created_at', 'published_at', 'cache_expires_at'))
    if not created <= published <= datetime.now(timezone.utc) < expiry:
      raise ValueError
  except (ValueError, TypeError, KeyError, HTTPException):
    raise unavailable() from None
  return value


def read_published_archive(client: Any, *, user_id: str, job_id: str, storage_path: str) -> dict[str, Any]:
  row = _published(_rpc(client, 'read_private_media_archive',
                        {'p_user_id': user_id, 'p_archive_job_id': job_id}), user_id, job_id)
  if row['storage_path'] != storage_path:
    raise unavailable()
  return row


def write_archive(*, plan: dict[str, Any], members: list[dict[str, Any]], attempt_id: str,
                  output_path: Path, storage: StorageService, settings: Settings) -> str:
  owner, job_id, attempt = _canonical_id(plan.get('user_id')), _canonical_id(plan.get('archive_job_id')), _canonical_id(attempt_id)
  enriched = _plan({**plan, 'member_snapshots': members}, owner, job_id, artifacts=True)
  if [{key: member[key] for key in MEMBER} for member in members] != plan['member_snapshots']:
    raise unavailable()
  size, ttl = output_path.stat().st_size, settings.export_cache_ttl_hours * 3600
  if (storage.bucket != 'saved-lift-exports' or not _positive(size)
      or size > settings.max_saved_lift_export_bytes or type(ttl) is not int or not 0 < ttl < 2**31):
    raise unavailable()
  path = f'{owner}/{job_id}-{attempt}.zip'
  identity = dict(attempt_id=attempt, **enriched, purpose='archive', bucket=storage.bucket,
                  storage_path=path, content_type='application/zip', size_bytes=size, content_sha256=file_sha256(output_path))
  parameters = {'p_' + key: value for key, value in identity.items() if key not in {'purpose', 'content_type'}}
  parameters.update(p_max_user_bytes=settings.max_user_reserved_bytes, p_max_global_bytes=settings.object_storage_limit_bytes)
  admitted = _rpc(storage.client, 'admit_private_media_archive_write', parameters)
  if not isinstance(admitted, dict) or admitted.keys() != set(RETURNED):
    raise unavailable()
  created = admitted['created_at']
  if _timestamp(created) > datetime.now(timezone.utc):
    raise unavailable()
  expected = {**identity, 'created_at': created, 'state': 'dispatching', 'published_at': None, 'cache_expires_at': None}
  try:
    _receipt([admitted], expected)
    persisted = (storage.client.table('private_media_generated_writes').select(','.join(RETURNED))
                 .eq('attempt_id', attempt).limit(2).execute()).data
    _receipt(persisted, expected)
    storage.create_file(path, output_path, 'application/zip', cache_control=IMMUTABLE_CACHE_CONTROL_SECONDS)
  except Exception:
    raise unavailable() from None
  common = dict(attempt_id=attempt, user_id=owner, video_id=None, purpose='archive', bucket=storage.bucket,
                storage_path=path, source_path=None, content_type='application/zip', size_bytes=size,
                job_id=None, worker_id=None, attempt_count=None)
  if _rpc(storage.client, 'observe_private_media_generated_write_success',
          {'p_' + key: value for key, value in common.items()}) is not True:
    raise unavailable()
  try:
    require_cached_export_object(storage, expected)
  except Exception:
    raise unavailable() from None
  published = _published(_rpc(storage.client, 'publish_private_media_archive',
                              {'p_attempt_id': attempt, 'p_user_id': owner, 'p_cache_ttl_seconds': ttl}), owner, job_id)
  try:
    if _timestamp(published['cache_expires_at']) != _timestamp(created) + timedelta(seconds=ttl):
      raise ValueError('Archive publication lifetime does not match its admission.')
    _receipt([published], {**expected, 'state': 'succeeded',
                                  'published_at': published['published_at'], 'cache_expires_at': published['cache_expires_at']})
    persisted = (storage.client.table('private_media_generated_writes').select(','.join(RETURNED))
                 .eq('attempt_id', attempt).limit(2).execute()).data
    _receipt(persisted, published)
  except Exception:
    raise unavailable() from None
  return path
