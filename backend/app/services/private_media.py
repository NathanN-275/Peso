from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
from pathlib import PurePosixPath
import re
import secrets
from urllib.parse import urlsplit
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import HTTPException

from .auth import VerifiedAuthContext
from .analyzed_export_writes import read_current_export
from .archive_writes import read_published_archive
from .config import get_settings
from .private_media_stream import PrivateMediaAsset
from .storage_service import StorageService
from .supabase_client import get_supabase_admin_client
from .video_storage_paths import require_user_storage_path


VIDEO_ASSETS = frozenset({'playback', 'thumbnail', 'export:clean', 'export:pose', 'export:barbell', 'export:pose-barbell'})


@dataclass(frozen=True)
class IssuedMediaGrant:
  token: str = field(repr=False)
  expires_at: datetime


def _uuid(value: str) -> str:
  try:
    parsed = UUID(value)
    if not parsed.int or str(parsed) != value:
      raise ValueError
  except (ValueError, TypeError, AttributeError):
    raise HTTPException(400, 'Invalid media resource.') from None
  return value


def _expiry(value) -> datetime:
  try:
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00')) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
      raise ValueError
    return parsed.astimezone(timezone.utc)
  except (ValueError, TypeError, AttributeError, OverflowError):
    raise HTTPException(503, 'Private media unavailable.') from None


def _scope(kind: str, resource_id: str, asset: str | None = None) -> None:
  _uuid(resource_id)
  if kind not in {'video', 'archive', 'avatar'} or (asset is not None and asset not in (VIDEO_ASSETS if kind == 'video' else {kind})):
    raise HTTPException(400, 'Invalid media resource.')


def _token_hash(token: str) -> str:
  if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
    raise HTTPException(401, 'Private media credential required.')
  decoded = base64.urlsafe_b64decode(token + '=')
  if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).rstrip(b'=').decode() != token:
    raise HTTPException(401, 'Private media credential required.')
  return hashlib.sha256(token.encode()).hexdigest()


def _object_size(info: dict) -> int:
  metadata = info.get('metadata')
  values = [info] + ([metadata] if isinstance(metadata, dict) else [])
  for item in values:
    for key in ('size', 'contentLength', 'content_length'):
      if key not in item:
        continue
      size = item[key]
      if isinstance(size, str) and re.fullmatch(r'[0-9]{1,19}', size):
        size = int(size)
      if type(size) is int and 0 <= size < 2**63:
        return size
      raise HTTPException(503, 'Private media unavailable.')
  raise HTTPException(503, 'Private media unavailable.')


class PrivateMediaService:
  def __init__(self, *, client=None, storage_factory=StorageService):
    self.client = client or get_supabase_admin_client()
    self.storage_factory = storage_factory

  def _rpc(self, name: str, values: dict) -> list[dict]:
    try:
      data = self.client.rpc(name, values).execute().data
    except Exception as error:
      code = getattr(error, 'code', None)
      if name == 'issue_private_media_avatar_grant' and code == 'P0002':
        raise HTTPException(409, 'Re-upload your profile picture to finish the security update.') from None
      raise HTTPException(403 if code == '42501' else 503, 'Private media unavailable.') from None
    if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
      raise HTTPException(503, 'Private media unavailable.')
    return data

  def issue(self, context: VerifiedAuthContext, kind: str, resource_id: str, assets: list[str]) -> IssuedMediaGrant:
    _scope(kind, resource_id)
    _uuid(context.user_id); _uuid(context.session_id)
    if not isinstance(assets, list) or not assets or len(assets) > 6 or any(not isinstance(asset, str) for asset in assets) or len(set(assets)) != len(assets):
      raise HTTPException(400, 'Invalid media assets.')
    for asset in assets:
      _scope(kind, resource_id, asset)
    if type(context.expires_at) is not int or context.expires_at <= datetime.now(timezone.utc).timestamp():
      raise HTTPException(401, 'Private media credential expired.')
    try:
      jwt_expiry = datetime.fromtimestamp(context.expires_at, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
      raise HTTPException(401, 'Private media credential expired.') from None
    token = secrets.token_urlsafe(32)
    values = {'p_user_id': context.user_id, 'p_session_id': context.session_id,
              'p_token_hash': _token_hash(token), 'p_resource_id': resource_id, 'p_jwt_expires_at': jwt_expiry}
    if kind != 'avatar':
      values.update(p_resource_kind=kind, p_asset_kinds=assets)
    rows = self._rpc('issue_private_media_avatar_grant' if kind == 'avatar' else 'issue_private_media_grant', values)
    if (len(rows) != 1 or rows[0].get('resource_kind') != kind or rows[0].get('resource_id') != resource_id
        or (kind == 'avatar' and set(rows[0]) != {'resource_kind', 'resource_id', 'expires_at'})):
      raise HTTPException(503, 'Private media unavailable.')
    expiry = _expiry(rows[0].get('expires_at'))
    remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
    if not 0 < remaining <= 300 or expiry.timestamp() > context.expires_at:
      raise HTTPException(503, 'Private media unavailable.')
    return IssuedMediaGrant(token, expiry)

  def revoke_global_session(self, context: VerifiedAuthContext) -> dict:
    _uuid(context.user_id); _uuid(context.session_id)
    # Global logout can commit once per provider session. Its verified UUID is
    # the stable operation key across refreshes, retries and client reloads.
    rows = self._rpc('revoke_private_media_session_once', {
      'p_user_id': context.user_id, 'p_session_id': context.session_id,
      'p_scope': 'global', 'p_request_id': context.session_id,
    })
    if len(rows) != 1 or type(rows[0].get('replayed')) is not bool:
      raise HTTPException(503, 'Private media unavailable.')
    completed_at = _expiry(rows[0].get('completed_at'))
    return {'scope': 'global', 'completed_at': completed_at.isoformat(), 'replayed': rows[0]['replayed']}

  def accept_session(self, context: VerifiedAuthContext) -> dict:
    owner = _uuid(context.user_id); session = _uuid(context.session_id)
    try:
      live = self.client.rpc('private_media_app_session_is_live', {
        'p_user_id': owner, 'p_session_id': session,
      }).execute().data
    except Exception:
      raise HTTPException(503, 'Private media unavailable.') from None
    if live is not True:
      raise HTTPException(403, 'Private media unavailable.')
    return {'owner_id': owner, 'session_id': session, 'accepted': True}

  def revoke_local_session(self, context: VerifiedAuthContext) -> dict:
    owner = _uuid(context.user_id); session = _uuid(context.session_id)
    # Keep replacement distinct from the session-UUID operation reserved for global logout.
    operation = str(uuid5(NAMESPACE_URL,
      f'https://usepeso.com/private-media/session-replacement/v1/{owner}/{session}'))
    rows = self._rpc('revoke_private_media_session_once', {
      'p_user_id': owner, 'p_session_id': session, 'p_scope': 'local', 'p_request_id': operation,
    })
    if len(rows) != 1 or set(rows[0]) != {'completed_at', 'replayed'} or type(rows[0]['replayed']) is not bool:
      raise HTTPException(503, 'Private media unavailable.')
    completed_at = _expiry(rows[0]['completed_at'])
    return {'scope': 'local', 'owner_id': owner, 'session_id': session,
            'completed_at': completed_at.isoformat(), 'replayed': rows[0]['replayed']}

  def session_cookie_paths(self, context: VerifiedAuthContext, cursor: str | None, *, all_sessions: bool = False) -> tuple[list[str], str | None]:
    owner = _uuid(context.user_id); session = _uuid(context.session_id)
    after = None
    if cursor is not None:
      if not isinstance(cursor, str) or cursor.count(':') != 1:
        raise HTTPException(400, 'Invalid media cursor.')
      kind, resource = cursor.split(':')
      _scope(kind, resource)
      after = (kind, resource)
    rows = self._rpc('private_media_session_cookie_paths', {
      'p_user_id': owner, 'p_session_id': None if all_sessions else session,
      'p_after_kind': after[0] if after else None, 'p_after_id': after[1] if after else None,
    })
    if len(rows) > 33:
      raise HTTPException(503, 'Private media unavailable.')
    resources = []
    for row in rows:
      if set(row) != {'resource_kind', 'resource_id'}:
        raise HTTPException(503, 'Private media unavailable.')
      kind, resource = row['resource_kind'], row['resource_id']
      if not isinstance(kind, str) or not isinstance(resource, str):
        raise HTTPException(503, 'Private media unavailable.')
      try:
        _scope(kind, resource)
      except HTTPException:
        raise HTTPException(503, 'Private media unavailable.') from None
      item = (kind, resource)
      if (after is not None and item <= after) or (resources and item <= resources[-1]):
        raise HTTPException(503, 'Private media unavailable.')
      resources.append(item)
    page = resources[:32]
    next_cursor = ':'.join(page[-1]) if len(resources) == 33 else None
    return [f'/private-media/{kind}/{resource}/' for kind, resource in page], next_cursor

  def session_cookie_paths_v2(self, context: VerifiedAuthContext, cursor: str | None, *, all_sessions: bool = False) -> tuple[list[str], str | None]:
    owner = _uuid(context.user_id); session = _uuid(context.session_id)
    after = None
    if cursor is not None:
      if not isinstance(cursor, str) or len(cursor) > 81 or cursor.count(':') != 2:
        raise HTTPException(400, 'Invalid media cursor.')
      kind, resource, cookie_session = cursor.split(':')
      _scope(kind, resource)
      try:
        if str(UUID(cookie_session)) != cookie_session:
          raise ValueError
      except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, 'Invalid media cursor.') from None
      after = (kind, resource, cookie_session)
    rows = self._rpc('private_media_session_cookie_paths_v2', {
      'p_user_id': owner, 'p_session_id': None if all_sessions else session,
      'p_after_kind': after[0] if after else None, 'p_after_id': after[1] if after else None,
      'p_after_session_id': after[2] if after else None,
    })
    if len(rows) > 17:
      raise HTTPException(503, 'Private media unavailable.')
    resources = []
    for row in rows:
      if set(row) != {'resource_kind', 'resource_id', 'cookie_session_id'}:
        raise HTTPException(503, 'Private media unavailable.')
      kind, resource, cookie_session = row['resource_kind'], row['resource_id'], row['cookie_session_id']
      try:
        if not all(isinstance(value, str) for value in (kind, resource, cookie_session)):
          raise ValueError
        _scope(kind, resource)
        if str(UUID(cookie_session)) != cookie_session:
          raise ValueError
        if not all_sessions and cookie_session not in {'00000000-0000-0000-0000-000000000000', session}:
          raise ValueError
      except (ValueError, TypeError, AttributeError, HTTPException):
        raise HTTPException(503, 'Private media unavailable.') from None
      item = (kind, resource, cookie_session)
      if (after is not None and item <= after) or (resources and item <= resources[-1]):
        raise HTTPException(503, 'Private media unavailable.')
      resources.append(item)
    page = resources[:16]
    next_cursor = ':'.join(page[-1]) if len(resources) == 17 else None
    paths = [f'/private-media/{kind}/{resource}/' if UUID(cookie_session).int == 0 else
             f'/private-media/session/{cookie_session}/{kind}/{resource}/'
             for kind, resource, cookie_session in page]
    return paths, next_cursor

  def _owned_row(self, table: str, resource_id: str, owner: str, columns: str) -> dict:
    try:
      data = self.client.table(table).select(columns).eq('id', resource_id).eq('user_id', owner).limit(1).execute().data
    except Exception:
      raise HTTPException(503, 'Private media unavailable.') from None
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
      raise HTTPException(404, 'Private media unavailable.')
    row = data[0]
    if row.get('id') != resource_id or row.get('user_id') != owner:
      raise HTTPException(404, 'Private media unavailable.')
    return row

  def authorize_asset(self, token: str, kind: str, resource_id: str, asset_kind: str, *, is_cancelled=lambda: False, expected_session_id: str | None = None) -> PrivateMediaAsset:
    def check_cancelled():
      if is_cancelled():
        raise HTTPException(503, 'Private media unavailable.')
    check_cancelled()
    _scope(kind, resource_id, asset_kind)
    if expected_session_id is not None:
      _uuid(expected_session_id)
    values = {'p_token_hash': _token_hash(token), 'p_resource_id': resource_id}
    if kind != 'avatar':
      values.update(p_resource_kind=kind, p_asset_kind=asset_kind)
    rows = self._rpc('authorize_private_media_avatar_grant' if kind == 'avatar' else 'authorize_private_media_grant', values)
    check_cancelled()
    if len(rows) != 1:
      raise HTTPException(403, 'Private media unavailable.')
    grant = rows[0]
    owner = _uuid(grant.get('user_id'))
    grant_session = _uuid(grant.get('session_id'))
    if expected_session_id is not None and grant_session != expected_session_id:
      raise HTTPException(403, 'Private media unavailable.')
    if grant.get('resource_kind') != kind or grant.get('resource_id') != resource_id or _expiry(grant.get('expires_at')) <= datetime.now(timezone.utc):
      raise HTTPException(403, 'Private media unavailable.')
    download = None
    expected_size = None
    check_cancelled()
    if kind == 'avatar':
      fields = {'user_id', 'session_id', 'resource_kind', 'resource_id', 'expires_at', 'attempt_id',
                'provider', 'bucket', 'storage_path', 'content_type', 'size_bytes', 'content_sha256', 'published_at'}
      if (set(grant) != fields or grant.get('provider') != 'supabase' or grant.get('bucket') != 'profile-avatars'
          or grant.get('content_type') != 'image/jpeg' or type(grant.get('size_bytes')) is not int
          or not 1 <= grant['size_bytes'] <= 524288 or not isinstance(grant.get('content_sha256'), str)
          or not re.fullmatch(r'[0-9a-f]{64}', grant['content_sha256'])
          or _expiry(grant.get('published_at')) > datetime.now(timezone.utc)):
        raise HTTPException(503, 'Private media unavailable.')
      attempt = _uuid(grant.get('attempt_id'))
      path = f'{owner}/avatar-{attempt}.jpg'
      if grant.get('storage_path') != path:
        raise HTTPException(503, 'Private media unavailable.')
      bucket = 'profile-avatars'; content_type = 'image/jpeg'; expected_size = grant['size_bytes']
    elif kind == 'archive':
      row = self._owned_row('saved_lift_export_jobs', resource_id, owner, 'id,user_id,archive_path,status,expires_at')
      if row.get('status') != 'completed' or _expiry(row.get('expires_at')) <= datetime.now(timezone.utc):
        raise HTTPException(404, 'Private media unavailable.')
      path = require_user_storage_path(row.get('archive_path'), owner, 'archive_path')
      published = read_published_archive(self.client, user_id=owner, job_id=resource_id, storage_path=path)
      expected_size = published['size_bytes']
      bucket = 'saved-lift-exports'; content_type = 'application/zip'; download = f'Saved-Lifts-{resource_id}.zip'
    else:
      row = self._owned_row('videos', resource_id, owner, 'id,user_id,discarded_at,storage_state,storage_path,original_storage_path,playback_path,thumbnail_path,save_state,is_saved')
      if row.get('discarded_at') or row.get('storage_state') == 'pruned':
        raise HTTPException(404, 'Private media unavailable.')
      bucket = get_settings().video_bucket
      if asset_kind == 'thumbnail':
        path = require_user_storage_path(row.get('thumbnail_path'), owner, 'thumbnail_path')
      elif asset_kind.startswith('export:'):
        if row.get('save_state') != 'saved' or row.get('is_saved') is not True:
          raise HTTPException(404, 'Private media unavailable.')
        if asset_kind == 'export:clean':
          path = require_user_storage_path(row.get('playback_path') or row.get('storage_path') or row.get('original_storage_path'), owner)
        else:
          check_cancelled()
          published = read_current_export(self.client, user_id=owner, video_id=resource_id,
                                           variant=asset_kind[7:], bucket=bucket)
          if published is None:
            raise HTTPException(404, 'Private media unavailable.')
          path = published['storage_path']
          expected_size = published['size_bytes']
      else:
        # An assigned derivative that cannot be opened never falls back to source bytes.
        path = require_user_storage_path(row.get('playback_path') or row.get('storage_path') or row.get('original_storage_path'), owner)
      suffix = PurePosixPath(path).suffix.lower()
      content_type = {'.mp4': 'video/mp4', '.mov': 'video/quicktime', '.m4v': 'video/x-m4v',
                      '.webm': 'video/webm', '.mkv': 'video/x-matroska', '.jpg': 'image/jpeg',
                      '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}.get(suffix, 'application/octet-stream')
      if asset_kind.startswith('export:'):
        extension = suffix if content_type.startswith('video/') else ''
        download = f'Saved-Lift-{resource_id}{extension}'
    check_cancelled()
    try:
      storage = self.storage_factory(bucket=bucket)
      info = storage.get_object_info(path)
    except Exception:
      raise HTTPException(503, 'Private media unavailable.') from None
    if not isinstance(info, dict):
      raise HTTPException(503, 'Private media unavailable.')
    size = _object_size(info)
    if expected_size is not None and size != expected_size:
      raise HTTPException(503, 'Private media unavailable.')
    check_cancelled()
    try:
      url = storage.create_signed_url(path, expires_in=60)
      expected = urlsplit(get_settings().supabase_url)
      actual = urlsplit(url)
    except Exception:
      raise HTTPException(503, 'Private media unavailable.') from None
    if actual.scheme != 'https' or actual.netloc != expected.netloc or not actual.path.startswith(f'/storage/v1/object/sign/{bucket}/') or actual.username or actual.password:
      raise HTTPException(503, 'Private media unavailable.')
    if kind == 'avatar' and (actual.path != f'/storage/v1/object/sign/{bucket}/{path}' or actual.fragment):
      raise HTTPException(503, 'Private media unavailable.')
    check_cancelled()
    return PrivateMediaAsset(url=url, owner_id=owner, size_bytes=size, content_type=content_type, download_name=download)
