from __future__ import annotations

from datetime import datetime, timezone
from threading import BoundedSemaphore, Event
from typing import Literal
from urllib.parse import quote, urlsplit
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.datastructures import MutableHeaders
from starlette.middleware.gzip import GZipMiddleware

from ..services.auth import VerifiedAuthContext, get_current_auth_context
from ..services.config import get_settings
from ..services.private_media import PrivateMediaService, VIDEO_ASSETS
from ..services.private_media_stream import PrivateMediaStreamError, private_media_response


PREFIX = '/private-media'
COOKIE = '__Secure-peso-media'
GRANT_HEADER = 'X-Peso-Media-Grant'
NO_STORE = {'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff'}
router = APIRouter(prefix=PREFIX, tags=['private-media'])
# Keep abandoned SDK threads bounded until they actually finish.
_authorization_slots = BoundedSemaphore(16)


def _is_media(path: str) -> bool:
  return path == PREFIX or path.startswith(PREFIX + '/')


class PrivateMediaHeadersMiddleware:
  def __init__(self, app):
    self.app = app

  async def __call__(self, scope, receive, send):
    if scope['type'] != 'http' or not _is_media(scope.get('path', '')):
      await self.app(scope, receive, send)
      return
    started = False
    async def send_private(message):
      nonlocal started
      if message['type'] == 'http.response.start':
        started = True
        headers = MutableHeaders(scope=message)
        for key, value in NO_STORE.items():
          headers[key] = value
      await send(message)
    # Media credentials are never accepted through any query parameter.
    if scope.get('query_string'):
      await JSONResponse({'detail': 'Media query parameters are unsupported.'}, status_code=400, headers=NO_STORE)(scope, receive, send_private)
      return
    try:
      await self.app(scope, receive, send_private)
    except Exception:
      if started:
        raise PrivateMediaStreamError('Private media stream interrupted.') from None
      await JSONResponse({'detail': 'Private media unavailable.'}, status_code=503, headers=NO_STORE)(scope, receive, send_private)


class MediaAwareGZipMiddleware:
  def __init__(self, app, minimum_size=1024):
    self.app = app
    self.gzip = GZipMiddleware(app, minimum_size=minimum_size)

  async def __call__(self, scope, receive, send):
    target = self.app if scope['type'] == 'http' and _is_media(scope.get('path', '')) else self.gzip
    await target(scope, receive, send)


def _enabled_settings():
  settings = get_settings()
  if not settings.private_media_enabled:
    raise HTTPException(503, 'Private media unavailable.')
  public = settings.private_media_public_origin
  allowed = settings.private_media_browser_origins
  def valid_origin(origin):
    try:
      value = urlsplit(origin)
    except ValueError:
      return False
    return (value.scheme == 'https' and value.netloc == value.hostname and not value.path and not value.query and not value.fragment
            and (value.hostname == 'usepeso.com' or (value.hostname or '').endswith('.usepeso.com')))
  if not valid_origin(public) or not allowed or any(not valid_origin(origin) or origin not in settings.cors_origins for origin in allowed):
    raise HTTPException(503, 'Private media unavailable.')
  if settings.upload_storage_provider != 'supabase':
    raise HTTPException(503, 'Private media unavailable.')
  return settings


def _browser_origin(request: Request, settings) -> None:
  if request.headers.get('origin') not in settings.private_media_browser_origins:
    raise HTTPException(403, 'Private media origin denied.')


def _browser_host(request: Request, settings) -> None:
  _browser_origin(request, settings)
  _media_host(request, settings)


def _media_host(request: Request, settings) -> None:
  # TLS terminates upstream; forwarded headers are not an identity source.
  if request.url.netloc != urlsplit(settings.private_media_public_origin).netloc:
    raise HTTPException(503, 'Private media unavailable.')


def _browser_session(value: str) -> str:
  try:
    parsed = UUID(value)
    if not parsed.int or str(parsed) != value:
      raise ValueError
  except (ValueError, TypeError, AttributeError):
    raise HTTPException(400, 'Invalid media session.') from None
  return value


def _native_request(request: Request) -> None:
  if request.headers.get('origin') is not None or any(key.startswith('sec-fetch-') for key in request.headers):
    raise HTTPException(403, 'Native media transport is unavailable to browser requests.')


class MediaSessionRequest(BaseModel):
  model_config = ConfigDict(extra='forbid')
  transport: Literal['browser', 'native']
  asset_kinds: list[str] = Field(min_length=1, max_length=6)


class MediaAcceptanceRequest(BaseModel):
  model_config = ConfigDict(extra='forbid')
  transport: Literal['browser', 'native']


class MediaLogoutRequest(BaseModel):
  model_config = ConfigDict(extra='forbid')
  transport: Literal['browser', 'native']
  cursor: str | None = Field(default=None, max_length=44, pattern=r'^(archive|avatar|video):[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


  @field_validator('cursor')
  @classmethod
  def nonzero_cursor(cls, value):
    if value is not None and not UUID(value.split(':')[1]).int:
      raise ValueError('Invalid media cursor.')
    return value


class BrowserMediaLogoutRequest(BaseModel):
  model_config = ConfigDict(extra='forbid')
  transport: Literal['browser']
  cursor: str | None = Field(default=None, max_length=81, pattern=r'^(archive|avatar|video):[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

  @field_validator('cursor')
  @classmethod
  def nonzero_resource_cursor(cls, value):
    if value is not None and not UUID(value.split(':')[1]).int:
      raise ValueError('Invalid media cursor.')
    return value


def _revocation_transport(payload: MediaLogoutRequest, request: Request, settings) -> None:
  if payload.transport == 'browser':
    _browser_origin(request, settings)
    if request.url.netloc != urlsplit(settings.private_media_public_origin).netloc:
      raise HTTPException(503, 'Private media unavailable.')
  else:
    _native_request(request)
    if payload.cursor is not None:
      raise HTTPException(400, 'Native media cursor is unsupported.')


def _revocation_response(payload: MediaLogoutRequest, context: VerifiedAuthContext, service, receipt: dict, *, all_sessions=False):
  paths, next_cursor = service.session_cookie_paths(context, payload.cursor, all_sessions=all_sessions) if payload.transport == 'browser' else ([], None)
  response = JSONResponse({**receipt, 'owner_id': context.user_id, 'session_id': context.session_id,
                           'next_cursor': next_cursor, 'cookie_cleanup_complete': next_cursor is None}, headers=NO_STORE)
  for path in paths:
    response.delete_cookie(COOKIE, path=path, secure=True, httponly=True, samesite='strict')
  return response


@router.post('/session-acceptance')
def accept_incoming_media(payload: MediaAcceptanceRequest, request: Request, settings=Depends(_enabled_settings),
                          context: VerifiedAuthContext = Depends(get_current_auth_context)):
  _revocation_transport(MediaLogoutRequest(transport=payload.transport), request, settings)
  return JSONResponse(PrivateMediaService().accept_session(context), headers=NO_STORE)


@router.post('/session-replacement')
def revoke_replaced_media(payload: MediaLogoutRequest, request: Request, settings=Depends(_enabled_settings),
                          context: VerifiedAuthContext = Depends(get_current_auth_context)):
  _revocation_transport(payload, request, settings)
  service = PrivateMediaService()
  receipt = service.revoke_local_session(context)
  return _revocation_response(payload, context, service, receipt)


@router.post('/logout')
def revoke_global_media(payload: MediaLogoutRequest, request: Request, settings=Depends(_enabled_settings),
                        context: VerifiedAuthContext = Depends(get_current_auth_context)):
  _revocation_transport(payload, request, settings)
  service = PrivateMediaService()
  receipt = service.revoke_global_session(context)
  return _revocation_response(payload, context, service, receipt, all_sessions=True)


def _v2_revocation_response(payload: BrowserMediaLogoutRequest, context: VerifiedAuthContext, service, receipt: dict, *, all_sessions=False):
  paths, next_cursor = service.session_cookie_paths_v2(context, payload.cursor, all_sessions=all_sessions)
  response = JSONResponse({**receipt, 'owner_id': context.user_id, 'session_id': context.session_id,
                           'next_cursor': next_cursor, 'cookie_cleanup_complete': next_cursor is None,
                           'cookie_inventory_version': 2}, headers=NO_STORE)
  for path in paths:
    response.delete_cookie(COOKIE, path=path, secure=True, httponly=True, samesite='strict')
  return response


@router.post('/v2/session-replacement')
def revoke_replaced_browser_media(payload: BrowserMediaLogoutRequest, request: Request, settings=Depends(_enabled_settings),
                                  context: VerifiedAuthContext = Depends(get_current_auth_context)):
  _browser_host(request, settings)
  service = PrivateMediaService()
  return _v2_revocation_response(payload, context, service, service.revoke_local_session(context))


@router.post('/v2/logout')
def revoke_global_browser_media(payload: BrowserMediaLogoutRequest, request: Request, settings=Depends(_enabled_settings),
                                context: VerifiedAuthContext = Depends(get_current_auth_context)):
  _browser_host(request, settings)
  service = PrivateMediaService()
  return _v2_revocation_response(payload, context, service, service.revoke_global_session(context), all_sessions=True)


def _issued_response(context, kind, resource, assets, settings, *, browser_session=None):
  grant = PrivateMediaService().issue(context, kind, resource, assets)
  path = (f'{PREFIX}/session/{browser_session}/{kind}/{resource}/' if browser_session is not None
          else f'{PREFIX}/{kind}/{resource}/')
  ttl = int((grant.expires_at - datetime.now(timezone.utc)).total_seconds())
  if ttl < 1:
    raise HTTPException(503, 'Private media unavailable.')
  body = {'resource_kind': kind, 'resource_id': resource,
          'urls': {asset: settings.private_media_public_origin + path + quote(asset, safe='') for asset in assets},
          'expires_in': ttl, 'expires_at': grant.expires_at.isoformat()}
  if browser_session is None:
    body['media_grant'] = grant.token
  response = JSONResponse(body, headers=NO_STORE)
  if browser_session is not None:
    response.set_cookie(COOKIE, grant.token, max_age=ttl, path=path, secure=True, httponly=True, samesite='strict')
  return response


@router.post('/{kind}/{resource_id}/session')
def issue_media_session(kind: Literal['video', 'archive', 'avatar'], resource_id: UUID, payload: MediaSessionRequest,
                        request: Request, settings=Depends(_enabled_settings),
                        context: VerifiedAuthContext = Depends(get_current_auth_context)):
  if payload.transport == 'browser':
    _browser_host(request, settings)
    raise HTTPException(409, 'Update the app to load private media.')
  _native_request(request)
  return _issued_response(context, kind, str(resource_id), payload.asset_kinds, settings)


@router.post('/session/{session_id}/{kind}/{resource_id}/session')
def issue_browser_media_session(session_id: str, kind: Literal['video', 'archive', 'avatar'], resource_id: UUID,
                                payload: MediaSessionRequest, request: Request, settings=Depends(_enabled_settings),
                                context: VerifiedAuthContext = Depends(get_current_auth_context)):
  _browser_host(request, settings)
  session_id = _browser_session(session_id)
  if payload.transport != 'browser' or session_id != context.session_id:
    raise HTTPException(403, 'Private media session denied.')
  assets = payload.asset_kinds
  if kind == 'video':
    if len(set(assets)) != len(assets) or not set(assets) <= VIDEO_ASSETS:
      raise HTTPException(400, 'Invalid media assets.')
    # Every browser video cookie carries the same existing domain, so a later
    # thumbnail/export reply cannot replace playback with a narrower capability.
    assets = sorted(VIDEO_ASSETS)
  return _issued_response(context, kind, str(resource_id), assets, settings, browser_session=session_id)


async def _read_response(token: str, kind: str, resource_id: UUID, asset_kind: str, request: Request, *, expected_session_id=None):
  service = PrivateMediaService()
  async def authorize():
    cancelled = Event()
    def authorize_sync():
      if not _authorization_slots.acquire(blocking=False):
        raise HTTPException(429, 'Private media busy.')
      try:
        options = {'is_cancelled': cancelled.is_set}
        if expected_session_id is not None:
          options['expected_session_id'] = expected_session_id
        return service.authorize_asset(token, kind, str(resource_id), asset_kind, **options)
      finally:
        _authorization_slots.release()
    try:
      return await anyio.to_thread.run_sync(authorize_sync, abandon_on_cancel=True)
    finally:
      # An already-running SDK call can finish; later metadata/signing work stops.
      cancelled.set()
  return private_media_response(authorize, method=request.method, range_header=request.headers.get('range'))


@router.api_route('/{kind}/{resource_id}/{asset_kind}', methods=['GET', 'HEAD'])
async def read_media(kind: Literal['video', 'archive', 'avatar'], resource_id: UUID, asset_kind: str, request: Request,
                     settings=Depends(_enabled_settings)):
  header = request.headers.get(GRANT_HEADER)
  cookie = request.cookies.get(COOKIE)
  if header is None:
    _browser_host(request, settings)
    raise HTTPException(409, 'Update the app to load private media.')
  _native_request(request)
  if cookie is not None:
    raise HTTPException(400, 'Ambiguous media credential.')
  if not header or request.headers.get('authorization') is not None:
    raise HTTPException(401, 'Private media credential required.')
  return await _read_response(header, kind, resource_id, asset_kind, request)


@router.api_route('/session/{session_id}/{kind}/{resource_id}/{asset_kind}', methods=['GET', 'HEAD'])
async def read_browser_media(session_id: str, kind: Literal['video', 'archive', 'avatar'], resource_id: UUID,
                             asset_kind: str, request: Request, settings=Depends(_enabled_settings)):
  _browser_host(request, settings)
  session_id = _browser_session(session_id)
  if request.headers.get(GRANT_HEADER) is not None:
    raise HTTPException(400, 'Ambiguous media credential.')
  token = request.cookies.get(COOKIE)
  if not token or request.headers.get('authorization') is not None:
    raise HTTPException(401, 'Private media credential required.')
  return await _read_response(token, kind, resource_id, asset_kind, request, expected_session_id=session_id)


@router.get('/session/{session_id}/{kind}/{resource_id}/download/{asset_kind}')
async def download_browser_media(session_id: str, kind: Literal['video', 'archive'], resource_id: UUID,
                                 asset_kind: str, request: Request, settings=Depends(_enabled_settings)):
  # Browser navigation has no Origin. Keep the stricter fetch route separate.
  _media_host(request, settings)
  if len(request.headers.getlist('host')) != 1:
    raise HTTPException(503, 'Private media unavailable.')
  session_id = _browser_session(session_id)
  allowed_asset = asset_kind == 'archive' if kind == 'archive' else (
    asset_kind in VIDEO_ASSETS and asset_kind.startswith('export:'))
  if not allowed_asset:
    raise HTTPException(404, 'Private download unavailable.')
  referrers = request.headers.getlist('referer')
  origin = next((value for value in settings.private_media_browser_origins if referrers == [value + '/']), None)
  expected_site = 'same-origin' if origin == settings.private_media_public_origin else 'same-site'
  if (origin is None or request.headers.getlist('origin')
      or any(request.headers.getlist(name) != [value] for name, value in (
        ('sec-fetch-mode', 'navigate'), ('sec-fetch-dest', 'document'),
        ('sec-fetch-site', expected_site), ('sec-fetch-user', '?1')))):
    raise HTTPException(403, 'Private download navigation denied.')
  if request.headers.get(GRANT_HEADER) is not None:
    raise HTTPException(400, 'Ambiguous media credential.')
  token = request.cookies.get(COOKIE)
  if not token or request.headers.get('authorization') is not None:
    raise HTTPException(401, 'Private media credential required.')
  return await _read_response(token, kind, resource_id, asset_kind, request, expected_session_id=session_id)
