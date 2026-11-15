from __future__ import annotations

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from ..services.auth import VerifiedAuthContext, get_current_auth_context
from ..services.avatar_writes import MAX_AVATAR_BYTES, normalize_avatar, profile_revision, publish_avatar, read_profile, save_profile, write_avatar
from ..services.config import get_settings
from ..services.storage_service import StorageService
from ..services.supabase_client import get_supabase_admin_client


router = APIRouter(prefix='/profile', tags=['profile'])


def _enabled_settings(request: Request):
  settings = get_settings()
  if not settings.private_media_enabled or settings.upload_storage_provider != 'supabase':
    raise HTTPException(503, 'Profile service is temporarily unavailable.')
  if request.query_params:
    raise HTTPException(400, 'Profile query parameters are unsupported.')
  return settings


class ProfileFields(BaseModel):
  model_config = ConfigDict(extra='forbid', strict=True)
  username: str | None
  display_name: str | None


class SaveProfileRequest(ProfileFields):
  profile_revision: str | None


@router.get('')
def get_profile(settings=Depends(_enabled_settings), context: VerifiedAuthContext = Depends(get_current_auth_context)):
  return {'profile': read_profile(get_supabase_admin_client(), context)}


@router.put('')
def put_profile(payload: SaveProfileRequest, settings=Depends(_enabled_settings),
                context: VerifiedAuthContext = Depends(get_current_auth_context)):
  return save_profile(get_supabase_admin_client(), context, payload.profile_revision, payload.username, payload.display_name)


@router.post('/avatar')
async def post_avatar(request: Request, settings=Depends(_enabled_settings),
                      context: VerifiedAuthContext = Depends(get_current_auth_context),
                      revision_header: str | None = Header(default=None, alias='X-Peso-Profile-Revision')):
  if not settings.upload_reservations_enabled:
    raise HTTPException(503, 'New uploads are temporarily paused by the beta budget guardrail.')
  if len(request.headers.getlist('x-peso-profile-revision')) != 1 or revision_header is None:
    raise HTTPException(400, 'A profile revision is required.')
  revision = None if revision_header == 'absent' else profile_revision(revision_header)
  content_type = request.headers.get('content-type', '')
  if len(request.headers.getlist('content-type')) != 1 or content_type not in {'image/jpeg', 'image/png', 'image/webp'}:
    raise HTTPException(400, 'Upload a JPEG, PNG, or WebP image.')
  lengths = request.headers.getlist('content-length')
  if len(lengths) > 1 or lengths and (len(lengths[0]) > 20 or not lengths[0].isascii() or not lengths[0].isdigit() or int(lengths[0]) > MAX_AVATAR_BYTES):
    raise HTTPException(413, 'Avatar exceeds the 512 KiB limit.')
  body = bytearray()
  async for chunk in request.stream():
    if len(body) + len(chunk) > MAX_AVATAR_BYTES:
      raise HTTPException(413, 'Avatar exceeds the 512 KiB limit.')
    body.extend(chunk)
  if not body:
    raise HTTPException(400, 'Avatar upload body is empty.')
  def process():
    normalized = normalize_avatar(bytes(body), content_type)
    return write_avatar(normalized, revision=revision, context=context, storage=StorageService(bucket='profile-avatars'), settings=settings)
  # Cancellation must not abandon a child or release its normalization slot.
  return await anyio.to_thread.run_sync(process)


@router.post('/avatar/{attempt_id}/publish')
def post_avatar_publication(attempt_id: str, payload: ProfileFields, settings=Depends(_enabled_settings),
                            context: VerifiedAuthContext = Depends(get_current_auth_context)):
  return publish_avatar(attempt_id, context=context, username=payload.username, display_name=payload.display_name,
                        storage=StorageService(bucket='profile-avatars'))
